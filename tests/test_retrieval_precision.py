"""R02 false-positive regressions plus fresh wording, not semantic-model tests."""

import json
from pathlib import Path

import pytest

from decision_memory.models import Record
from decision_memory.store import digest


@pytest.fixture
def expanded_store(store):
    root = Path(__file__).resolve().parents[1]
    records = []
    for name in ('testing/fixed_retrieval/corpus.json', 'testing/retrieval_round2/extra-corpus.json'):
        records += json.loads((root / name).read_text(encoding='utf-8'))['records']
    for data in records:
        relative = store.stage(Record.model_validate(data))
        store.publish(relative, digest(store.draft(relative)[1]))
    return store


@pytest.mark.parametrize('query', [
    '这个内部办公室不会开会，准备调整桌椅摆放位置。',
    '员工接手内部园艺工作以后，需要调整盆栽摆放方向。',
    '公司内部准备调整办公区的座椅位置。',
    '接手庭院以后，准备调整盆栽位置。',
    '调整 Photoshop 中某张照片的亮度，用鼠标拖动滑块。',
])
def test_context_overlap_does_not_admit_unrelated_records(expanded_store, query):
    assert expanded_store.search(query, 'SYN-team-tools', ['windows'])['results'] == []


@pytest.mark.parametrize('query', [
    '导出的 CSV 用 Excel 打开后中文显示乱码，应该先核查什么？',
    '用 Excel 查看这个 CSV，中文出现乱码，该怎样检查？',
    'CSV 在 Excel 中显示中文异常，要从哪里检查编码？',
])
def test_mixed_script_query_has_no_single_character_admission(expanded_store, query):
    result = expanded_store.search(query, 'SYN-team-tools', ['windows'])
    assert result['results'][0]['record']['id'] == 'SYN-R02-CSV'
    assert [h['record']['id'] for h in result['results']] == ['SYN-R02-CSV']
    assert all(len(term) >= 2 for h in result['results'] for term in h['matched_terms'])


def test_scope_rejection_does_not_fill_results_with_single_character_matches(expanded_store):
    query = '导出的 CSV 用 Excel 打开后中文显示乱码，应该先核查什么？'
    assert expanded_store.search(query, 'SYN-team-tools', ['linux'])['results'] == []


def test_real_printing_topic_still_recalls_external_material(expanded_store):
    query = '办公室打印设备发生卡纸，应该检查什么？'
    result = expanded_store.search(query, 'SYN-team-tools', ['windows'])
    assert result['results'][0]['record']['id'] == 'SYN-R02-DEVICE'
    assert result['results'][0]['record']['kind'] == 'external_note'


def test_source_boilerplate_does_not_supply_a_second_topic(expanded_store):
    query = '定期复制个人资料以后，怎么确认这些副本真的能恢复，而不是只看文件在不在？'
    result = expanded_store.search(query, 'SYN-team-tools', ['windows'])
    assert result['results'][0]['record']['id'] == 'SYN-R02-BACKUP'
    assert 'SYN-X01' not in [h['record']['id'] for h in result['results']]


@pytest.mark.parametrize('query', ['维护', '设置', '图形入口', 'SYN-M01'])
def test_intentional_keywords_remain_supported(expanded_store, query):
    assert expanded_store.search(query, 'SYN-team-tools', ['windows'])['results']


@pytest.mark.parametrize('query', [
    '不做数据库迁移，只核查备份副本是否能恢复。',
    '无需做结构变更；只检查副本恢复能力。',
    '不考虑命令行配置，而是核对打印设备的纸张尺寸。',
])
def test_explicit_task_exclusion_does_not_dominate_ranking(expanded_store, query):
    expected = 'SYN-R02-DEVICE' if '打印设备' in query else 'SYN-R02-BACKUP'
    result = expanded_store.search(query, 'SYN-team-tools', ['windows'])
    assert result['results'][0]['record']['id'] == expected
