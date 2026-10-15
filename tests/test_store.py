import json
from pathlib import Path
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest

from decision_memory.models import Record, parse_record, render_record
from decision_memory.store import MemoryError, Store, digest, restore


def approve(store, record):
    relative = store.stage(record)
    return store.publish(relative, digest(store.draft(relative)[1]))


def test_draft_not_retrieved(store, record):
    store.stage(record)
    assert store.search("维护")['results'] == []
    assert store.doctor()['active_count'] == 0


def test_publish_is_hash_bound_and_idempotent(store, record):
    relative = store.stage(record)
    sha = digest(store.draft(relative)[1])
    changed = record.model_copy(update={"rationale": "修订后需要重新审核"})
    (store.root / relative).write_bytes(render_record(changed))
    with pytest.raises(MemoryError, match="候选已经变化"):
        store.publish(relative, sha)
    assert store.doctor()['active_count'] == 0
    new_sha = digest(store.draft(relative)[1])
    assert store.publish(relative, new_sha)['version'] == 1
    assert store.publish(relative, new_sha)['unchanged']


def test_get_has_original_conditions_and_evidence(store, record):
    approve(store, record)
    result = store.get(record.id)
    assert result['record']['exceptions'] == record.exceptions
    assert result['record']['sources'] == record.sources
    assert result['record']['verification'] == 'unverified'
    assert result['authority'] == 'user-approved'


@pytest.mark.parametrize('query', ['维护', '维护成本', '长期维护', '备份', 'DEMO-maintenance'])
def test_chinese_and_short_query(store, record, query):
    approve(store, record)
    assert store.search(query)['results'][0]['record']['id'] == record.id


@pytest.mark.parametrize('query', ['" OR *', ') OR secret', '不存在的完全不同考量'])
def test_query_is_data_and_misses_are_honest(store, record, query):
    approve(store, record)
    assert store.search(query)['results'] == []


def test_hard_scope_filters_search_and_get(store, record):
    scoped = record.model_copy(update={'project_scope': ['项目甲'], 'environments': ['windows']})
    approve(store, scoped)
    assert not store.search('维护')['results']
    assert not store.search('维护', '项目乙', ['windows'])['results']
    assert not store.search('维护', '项目甲', ['linux'])['results']
    assert store.search('维护', '项目甲', ['windows'])['results']
    with pytest.raises(MemoryError, match='范围'):
        store.get(record.id, '项目甲', ['linux'])


def test_external_source_never_becomes_preference(store, record):
    approve(store, record.model_copy(update={'kind': 'external_note'}))
    assert store.context('维护')['memories'][0]['kind'] == 'external_note'


def test_revision_supersedes_and_stale_draft_fails(store, record):
    relative = store.stage(record)
    store.publish(relative, digest(store.draft(relative)[1]))
    revised = record.model_copy(update={'base_version': 1, 'action': '新的适用动作'})
    (store.root / relative).write_bytes(render_record(revised))
    store.publish(relative, digest(store.draft(relative)[1]))
    assert store.get(record.id)['version'] == 2
    assert len(list((store.root / 'memory/records').glob('**/*.md'))) == 2
    (store.root / relative).write_bytes(render_record(record.model_copy(update={'action': '过时修订'})))
    with pytest.raises(MemoryError, match='正式版本已经变化'):
        store.publish(relative, digest(store.draft(relative)[1]))


def test_revoke_blocks_old_index_and_get(store, record):
    approve(store, record)
    old = store.search('维护')['results'][0]
    store.revoke(record.id, old['sha256'])
    assert not store.search('维护')['results']
    with pytest.raises(MemoryError, match='停用'):
        store.get(record.id)
    assert store.doctor()['revoked_count'] == 1


def test_direct_edit_invalidates_approval(store, record):
    approve(store, record)
    hit = store.get(record.id)
    Path(hit['source_path']).write_bytes(render_record(record.model_copy(update={'action': '未经审核的动作'})))
    with pytest.raises(MemoryError, match='指纹失效'):
        store.get(record.id)
    result = store.search('维护')
    assert result['results'] == [] and result['warnings']


def test_context_omits_whole_oversized_record(store, record):
    approve(store, record.model_copy(update={'rationale': '完整重要条件' * 500}))
    result = store.context('维护', max_chars=1000)
    assert result['memories'] == []
    assert result['omitted'][0]['id'] == record.id
    assert result['content_chars'] == 0


def test_invalid_yaml_and_forged_approval(record):
    raw = render_record(record)
    with pytest.raises(ValueError):
        parse_record(raw.replace(b'schema_version: 1', b'schema_version: 1\napproved: true'))
    with pytest.raises(ValueError, match='唯一'):
        parse_record(raw.replace(b'schema_version: 1', b'schema_version: 1\nschema_version: 1'))
    with pytest.raises(Exception):
        parse_record(b'---\nid: !!python/object/apply:os.system [whoami]\n---\n')


def test_bom_crlf(record):
    raw = b'\xef\xbb\xbf' + render_record(record).replace(b'\n', b'\r\n')
    assert parse_record(raw) == record


@pytest.mark.parametrize('path', ['../escape.md', '/escape.md', 'memory/records/x.md'])
def test_draft_path_boundary(store, path):
    with pytest.raises(MemoryError):
        store.draft(path)


def test_uncommitted_transaction_does_not_activate(store, record, monkeypatch):
    import decision_memory.store as module
    relative = store.stage(record)
    original = module.atomic_write
    def crash(path, raw):
        if path == store.manifest_path:
            raise OSError('模拟清单提交前终止')
        return original(path, raw)
    monkeypatch.setattr(module, 'atomic_write', crash)
    with pytest.raises(OSError):
        store.publish(relative, digest(store.draft(relative)[1]))
    assert store.search('维护')['results'] == []
    assert store.doctor()['transactions'][0]['state'] == 'uncommitted-candidate-not-active'
    monkeypatch.setattr(module, 'atomic_write', original)
    assert store.publish(relative, digest(store.draft(relative)[1]))['version'] == 1


def test_crash_after_commit_is_detectable(store, record, monkeypatch):
    import decision_memory.store as module
    original = module.atomic_write
    def crash(path, raw):
        if path.parent.name == 'transactions' and b'"committed"' in raw:
            raise OSError('模拟提交之后日志更新失败')
        return original(path, raw)
    monkeypatch.setattr(module, 'atomic_write', crash)
    approve(store, record)
    assert store.get(record.id)['version'] == 1
    assert store.doctor()['transactions'][0]['state'] == 'commit-completed'


def test_candidate_changed_during_publish_preserves_previous(store, record, monkeypatch):
    import decision_memory.store as module
    relative = store.stage(record)
    original = module.atomic_write
    def edit(path, raw):
        result = original(path, raw)
        if path.suffix == '.md' and path.parent.name == record.id:
            (store.root / relative).write_bytes(render_record(record.model_copy(update={'action': '并发编辑'})))
        return result
    monkeypatch.setattr(module, 'atomic_write', edit)
    with pytest.raises(MemoryError, match='发布过程中'):
        store.publish(relative, digest(store.draft(relative)[1]))
    assert store.doctor()['active_count'] == 0


def test_export_restore_exact_active_versions(store, record, tmp_path):
    approve(store, record)
    before = store.get(record.id)
    archive = tmp_path / 'backup.zip'
    store.export(archive)
    destination = tmp_path / '恢复后的中文库'
    result = restore(archive, destination)
    assert result['ok'] and result['active_count'] == 1
    assert Store(destination).get(record.id)['sha256'] == before['sha256']
    assert not list((destination / 'drafts').glob('*.md'))


def test_restore_rejects_traversal_without_extracting(tmp_path):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('.decision-memory/manifest.json', '{}')
        z.writestr('../escape.md', 'malicious')
    with pytest.raises(MemoryError, match='越界'):
        restore(archive, tmp_path / 'restore')
    assert not (tmp_path / 'escape.md').exists()


def test_index_corruption_reports_and_rebuilds(store, record):
    approve(store, record)
    index = store.state / 'index.sqlite3'
    index.write_bytes(b'damaged')
    with pytest.raises(MemoryError, match='索引不可用'):
        store.search('维护')
    assert store.doctor(rebuild=True)['ok']
    assert store.search('维护')['results']


def test_missing_manifest_fails_instead_of_claiming_empty(tmp_path):
    with pytest.raises(MemoryError, match='正式清单不可用'):
        Store(tmp_path / 'missing').search('维护')


def test_draft_overwrite_is_not_implicit(store, record):
    store.stage(record)
    with pytest.raises(MemoryError, match='候选已存在'):
        store.stage(record)


def test_two_publishers_are_serialized_without_duplicate_version(store, record):
    relative = store.stage(record)
    sha = digest(store.draft(relative)[1])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: store.publish(relative, sha), range(2)))
    assert sorted(x['unchanged'] for x in results) == [False, True]
    assert store.get(record.id)['version'] == 1
    assert len(list((store.root / 'memory/records').glob('**/*.md'))) == 1


def test_revoked_current_version_is_still_revoked_after_restore(store, record, tmp_path):
    approve(store, record)
    store.revoke(record.id, store.get(record.id)['sha256'])
    archive = tmp_path / 'revoked.zip'
    store.export(archive)
    result = restore(archive, tmp_path / 'restored')
    assert result['revoked_count'] == 1
    assert not Store(tmp_path / 'restored').search('维护')['results']
