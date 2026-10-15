import json
import os
import subprocess
import sys

import pytest

from decision_memory.conversation import approve, preview, revoke
from decision_memory.models import parse_record, render_record
from decision_memory.store import MemoryError, Store, restore


def snapshot(store):
    return {p.relative_to(store.root).as_posix(): p.read_bytes()
            for p in store.root.rglob('*') if p.is_file()}


def cli(store, *args, stdin=None):
    return subprocess.run([sys.executable, '-B', '-m', 'decision_memory',
                           '--vault', str(store.root), *args], input=stdin, capture_output=True,
                          env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'})


def approve_args(review, message='审核通过，按刚才这版记录。'):
    return ('--sha256', review['sha256'], '--vault-id', review['vault_id'],
            '--confirmed', '--approval-message', message)


def test_stdin_preview_is_complete_and_writes_nothing(store, record):
    before = snapshot(store)
    result = cli(store, 'preview', '-', stdin=render_record(record))
    assert result.returncode == 0, result.stderr
    review = json.loads(result.stdout)
    assert parse_record(review['content'].encode('utf-8')) == record
    assert review['content'].encode('utf-8') == render_record(record)
    assert review['id'] == record.id and review['version'] == 1
    assert not review['already_active']
    assert snapshot(store) == before


def test_draft_preview_writes_nothing(store, record):
    relative = store.stage(record)
    before = snapshot(store)
    review = preview(store, relative)
    assert review['content'].encode('utf-8') == (store.root / relative).read_bytes()
    assert snapshot(store) == before


@pytest.mark.parametrize('newlines', ['lf', 'crlf'])
def test_cli_conversation_round_trip_and_duplicate_approval(store, record, tmp_path, newlines):
    # The simulated user sees this exact content before the test stages it.
    raw = render_record(record)
    if newlines == 'crlf':
        raw = raw.replace(b'\n', b'\r\n')
    reviewed = json.loads(cli(store, 'preview', '-', stdin=raw).stdout)
    source = tmp_path / 'user-approved-content.md'
    source.write_bytes(reviewed['content'].encode('utf-8'))
    staged = cli(store, 'stage', str(source))
    assert staged.returncode == 0, staged.stderr
    relative = json.loads(staged.stdout)['draft']
    approved = cli(store, 'approve', relative, *approve_args(reviewed))
    assert approved.returncode == 0, approved.stderr
    assert json.loads(approved.stdout)['version'] == 1
    stored = store.get(record.id)
    assert stored['record'] == record.model_dump()
    evidence = store._manifest()['entries'][record.id]['approval']
    assert evidence['channel'] == 'conversation'
    assert evidence['user_confirmation'] == '审核通过，按刚才这版记录。'
    assert 'not independently authenticated' in evidence['evidence']
    repeated = cli(store, 'approve', relative, *approve_args(reviewed))
    assert repeated.returncode == 0 and json.loads(repeated.stdout)['unchanged']
    assert store.get(record.id)['version'] == 1
    assert preview(store, relative)['already_active']
    assert store.doctor()['active_count'] == 1


@pytest.mark.parametrize('missing', ['--confirmed', '--sha256', '--vault-id', '--approval-message'])
def test_cli_missing_confirmation_requirements_cannot_publish(store, record, missing):
    relative = store.stage(record)
    reviewed = preview(store, relative)
    args = list(approve_args(reviewed))
    index = args.index(missing)
    del args[index:index + (1 if missing == '--confirmed' else 2)]
    before = snapshot(store)
    failed = cli(store, 'approve', relative, *args)
    assert failed.returncode != 0
    assert snapshot(store) == before


@pytest.mark.parametrize('confirmed,message', [(False, '分析不错'), (False, '审核通过并记录'), (True, '  ')])
def test_no_explicit_confirmation_marker_or_empty_message_cannot_publish(store, record, confirmed, message):
    relative = store.stage(record)
    reviewed = preview(store, relative)
    before = snapshot(store)
    with pytest.raises(MemoryError):
        approve(store, relative, reviewed['sha256'], reviewed['vault_id'], confirmed, message)
    assert snapshot(store) == before


def test_changed_candidate_rejects_previously_reviewed_hash(store, record):
    relative = store.stage(record)
    reviewed = preview(store, relative)
    (store.root / relative).write_bytes(render_record(record.model_copy(update={'exceptions': ['新增例外，尚未审阅']})))
    with pytest.raises(MemoryError, match='候选已经变化'):
        approve(store, relative, reviewed['sha256'], reviewed['vault_id'], True, '记录已展示版本')
    assert store.doctor()['active_count'] == 0


def test_same_content_in_another_vault_is_not_approved(store, record, tmp_path):
    relative = store.stage(record)
    reviewed = preview(store, relative)
    other = Store(tmp_path / 'another-isolated-vault')
    other.init()
    other_relative = other.stage(record)
    with pytest.raises(MemoryError, match='库不一致'):
        approve(other, other_relative, reviewed['sha256'], reviewed['vault_id'], True, '批准已展示版本')
    assert other.doctor()['active_count'] == store.doctor()['active_count'] == 0


def test_concurrent_publication_invalidates_old_base_version(store, record):
    relative = store.stage(record)
    reviewed = preview(store, relative)
    competitor = record.model_copy(update={'action': '另一份经模拟批准的内容'})
    other_relative = 'drafts/competing-version.md'
    (store.root / other_relative).write_bytes(render_record(competitor))
    other_review = preview(store, other_relative)
    approve(store, other_relative, other_review['sha256'], other_review['vault_id'], True, '合成批准')
    with pytest.raises(MemoryError, match='正式版本已经变化'):
        approve(store, relative, reviewed['sha256'], reviewed['vault_id'], True, '批准原展示版本')
    with pytest.raises(MemoryError, match='正式版本已经变化'):
        preview(store, relative)
    assert store.get(record.id)['record']['action'] == competitor.action


def test_approval_evidence_survives_export_restore(store, record, tmp_path):
    relative = store.stage(record)
    reviewed = preview(store, relative)
    approve(store, relative, reviewed['sha256'], reviewed['vault_id'], True, '只批准这个合成版本')
    archive = tmp_path / 'conversation-backup.zip'
    store.export(archive)
    target = tmp_path / 'restored'
    restore(archive, target)
    recovered = Store(target)
    assert recovered.get(record.id)['record'] == record.model_dump()
    assert recovered._manifest()['entries'][record.id]['approval'] == store._manifest()['entries'][record.id]['approval']


def test_cli_revoke_requires_confirmation_and_retains_history(store, record):
    relative = store.stage(record)
    reviewed = preview(store, relative)
    approve(store, relative, reviewed['sha256'], reviewed['vault_id'], True, '合成批准')
    args = list(approve_args(reviewed, '停用这条合成记录'))
    args.remove('--confirmed')
    assert cli(store, 'revoke', record.id, *args).returncode != 0
    assert store.get(record.id)['version'] == 1
    result = cli(store, 'revoke', record.id, *approve_args(reviewed, '停用这条合成记录'))
    assert result.returncode == 0, result.stderr
    assert store.search('维护')['results'] == []
    entry = store._manifest()['entries'][record.id]
    assert entry['revocation_approval']['user_confirmation'] == '停用这条合成记录'
    assert (store.root / entry['path']).is_file()


@pytest.mark.parametrize('change', ['vault', 'hash'])
def test_revoke_rejects_wrong_vault_or_content_version(store, record, change):
    relative = store.stage(record)
    reviewed = preview(store, relative)
    approve(store, relative, reviewed['sha256'], reviewed['vault_id'], True, '合成批准')
    vault_id = 'another-vault' if change == 'vault' else reviewed['vault_id']
    sha256 = '0' * 64 if change == 'hash' else reviewed['sha256']
    with pytest.raises(MemoryError):
        revoke(store, record.id, sha256, vault_id, True, '停用已展示版本')
    assert store.get(record.id)['version'] == 1


def test_stdin_preview_does_not_initialize_missing_vault(record, tmp_path):
    missing = Store(tmp_path / 'missing-vault')
    result = cli(missing, 'preview', '-', stdin=render_record(record))
    assert result.returncode != 0 and not missing.root.exists()
