"""Frozen before the R03 fix: recall, negative controls, and evidence integrity.

Synthetic stores only. The fresh wording here is not an independent blind set:
the implementing assistant authored it before editing production code.
"""
import json
from pathlib import Path

import pytest

from decision_memory.models import Record
from decision_memory.store import digest


R03_QUERY = ('本地 Excel 合并工具 行政非程序员交接 调整目录列名 配置文件 '
             '设置窗口 Web后台 低频维护 可用性验证')


@pytest.fixture
def synonym_store(store):
    root = Path(__file__).resolve().parents[1]
    for name in ('testing/fixed_retrieval/corpus.json', 'testing/retrieval_round2/extra-corpus.json'):
        for row in json.loads((root / name).read_text(encoding='utf-8'))['records']:
            relative = store.stage(Record.model_validate(row))
            store.publish(relative, digest(store.draft(relative)[1]))
    return store


@pytest.mark.parametrize('query', [
    R03_QUERY,
    '行政助理没有编程经验，接手报表软件后要自己改参数，该怎么交付？',
    '配置窗口交给不会写代码的同事自行管理，如何减少后续支持？',
    '为不懂编程的运营同事准备配置界面，要比较哪些交付成本？',
    '移交这个 Excel 助手给非程序员后，能否让她自己改选项？',
])
def test_r03_and_prepared_paraphrases_recall_target_first(synonym_store, query):
    result = synonym_store.search(query, 'SYN-team-tools', ['windows'])
    assert result['warnings'] == []
    assert result['results'] and result['results'][0]['record']['id'] == 'SYN-M01'


@pytest.mark.parametrize('query', [
    '让没有编程经验的同事接手园艺，明天怎样给盆栽浇水？',
    '请安排非程序员接手办公室家具搬运和花盆养护。',
    '交接 移交 接手 接手，明天办公室怎样安排轮班？',
    '设置窗口 配置窗口 设置界面，办公室明天放假吗？',
    '非程序员 不写代码 不懂编程，今天软件行业天气怎样？',
    '内部软件准备调整默认选项，用什么方式工作？',
    '不做非程序员的软件交接，只检查打印设备卡纸和纸张尺寸。',
])
def test_expansion_does_not_turn_generic_or_repeated_evidence_into_topic(synonym_store, query):
    result = synonym_store.search(query, 'SYN-team-tools', ['windows'])
    ids = [hit['record']['id'] for hit in result['results']]
    assert 'SYN-M01' not in ids
    if '打印设备' in query:
        assert ids and ids[0] == 'SYN-R02-DEVICE'


def test_synonym_evidence_keeps_both_actual_phrases_and_field(synonym_store):
    hit = synonym_store.search(R03_QUERY, 'SYN-team-tools', ['windows'])['results'][0]
    evidence = hit['synonym_matches']
    pair = next(row for row in evidence if row['query_term'] == '非程序员')
    assert pair['record_term'] == '非技术'
    value = hit['record'][pair['field']]
    text = '\n'.join(value) if isinstance(value, list) else value
    assert pair['record_term'] in text
    assert pair['query_term'] in R03_QUERY
    assert all(term.casefold() in R03_QUERY.casefold() for term in hit['matched_terms'])
    assert hit['version'] == 1 and hit['record']['verification'] == 'unverified'


def test_context_keeps_conditions_and_expansion_evidence(synonym_store):
    context = synonym_store.context(R03_QUERY, 'SYN-team-tools', ['windows'], max_chars=5000)
    target = next(row for row in context['memories'] if row['id'] == 'SYN-M01')
    original = synonym_store.get('SYN-M01', 'SYN-team-tools', ['windows'])['record']
    for name in ('sources', 'applies_when', 'exceptions', 'verification', 'action'):
        assert target[name] == original[name]
    assert target['synonym_matches']
    assert context['content_chars'] <= 5000


def test_expansion_cannot_cross_scope_or_revocation(synonym_store):
    assert synonym_store.search(R03_QUERY, 'other-project', ['windows'])['results'] == []
    current = synonym_store.get('SYN-M01', 'SYN-team-tools', ['windows'])
    synonym_store.revoke('SYN-M01', current['sha256'])
    assert 'SYN-M01' not in [r['record']['id'] for r in synonym_store.search(
        R03_QUERY, 'SYN-team-tools', ['windows'])['results']]


def test_new_record_id_and_reverse_expression_are_supported(store):
    record = Record(id='SYN-new-archive', title='合成：归档软件的配置窗口', kind='decision_case',
        tags=['归档软件'], sources=['独立临时库测试，不代表用户观点'],
        considerations=['接手人员不写代码'], rationale='比较交接成本和维护次数。',
        applies_when=['同事需要修改归档软件参数'], exceptions=['开发者统一维护时另评估'],
        action='提供配置窗口用于常见参数修改。', body='仅合成测试。')
    relative = store.stage(record)
    store.publish(relative, digest(store.draft(relative)[1]))
    query = '非技术同事想通过图形入口修改归档软件参数，怎样交付？'
    hit = store.search(query)['results'][0]
    assert hit['record']['id'] == record.id
    assert any(row['query_term'] == '非技术' and row['record_term'] == '不写代码'
               for row in hit['synonym_matches'])


def test_sources_and_body_cannot_supply_synonym_admission(store):
    record = Record(id='SYN-source-noise', title='合成：室内花卉浇水计划', kind='external_note',
        sources=['模板：交接软件给非技术同事，使用图形入口'],
        considerations=['土壤湿度'], rationale='减少过度浇水。',
        applies_when=['室内绿植'], exceptions=['休眠期减少浇水'], action='按土壤湿度检查。',
        body='附带模板：交接软件给非技术同事，使用图形入口。')
    relative = store.stage(record)
    store.publish(relative, digest(store.draft(relative)[1]))
    assert store.search('移交应用给非程序员后，怎样准备设置窗口？')['results'] == []
