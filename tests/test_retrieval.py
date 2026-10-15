"""Behavior checks for natural-language recall and broad-word false positives."""

import json
from pathlib import Path

import pytest

from decision_memory.models import Record
from decision_memory.store import digest


@pytest.fixture
def retrieval_store(store):
    corpus = Path(__file__).resolve().parents[1] / 'testing/fixed_retrieval/corpus.json'
    for data in json.loads(corpus.read_text(encoding='utf-8'))['records']:
        relative = store.stage(Record.model_validate(data))
        store.publish(relative, digest(store.draft(relative)[1]))
    return store


ORIGINAL_FAILURES = [
    '给不懂代码的同事使用并负责后续维护的内部工具应该怎样提供日常设置入口？',
    '接手的人不会编程，只想点按钮来调整选项，这类内部助手该怎么交付？',
]

ADDITIONAL_REPHRASINGS = [
    '以后由不写代码的行政同事接手这个小程序，改设置时希望直接点击完成。',
    '交给运营同事长期打理的内部小程序，能不能让她直接在界面改参数？',
    '接手人员只能操作界面，常用选项还会经常调整，该采用怎样的交付方式？',
    '不会编程的同事接管后，要经常变更选项；怎样避免每次找开发人员？',
]


@pytest.mark.parametrize('query', ORIGINAL_FAILURES + ADDITIONAL_REPHRASINGS)
def test_rephrased_handover_recalls_target_first(retrieval_store, query):
    result = retrieval_store.search(query, 'SYN-team-tools', ['windows'])
    assert result['warnings'] == []
    assert result['results'], result
    assert result['results'][0]['record']['id'] == 'SYN-M01', result


@pytest.mark.parametrize('query', [
    '如何维护家里的空调设备？',
    '这个工具如何设置视频字幕字体？',
    '怎样给照片调整亮度？',
    '公司内部明天放假吗？',
    '厨房按钮坏了怎样修理？',
    '内部办公桌椅怎样调整高度？',
])
def test_broad_word_overlap_is_not_enough(retrieval_store, query):
    assert retrieval_store.search(query, 'SYN-team-tools', ['windows'])['results'] == []


@pytest.mark.parametrize('query', ['schema_version', 'external_note', 'SYN-team-tools'])
def test_schema_and_scope_metadata_are_not_search_content(retrieval_store, query):
    assert retrieval_store.search(query, 'SYN-team-tools', ['windows'])['results'] == []


def test_match_evidence_names_actual_fragments(retrieval_store):
    query = ORIGINAL_FAILURES[0]
    result = retrieval_store.search(query, 'SYN-team-tools', ['windows'])
    target = next(h for h in result['results'] if h['record']['id'] == 'SYN-M01')
    assert target['matched_terms']
    assert query.rstrip('？') not in target['matched_terms']
    assert all(term in query for term in target['matched_terms'])
    assert result['score_is_not_confidence'] is True


def test_explicit_id_ranks_its_own_record_first(retrieval_store):
    result = retrieval_store.search('SYN-M01', 'SYN-team-tools', ['windows'])
    assert result['results'][0]['record']['id'] == 'SYN-M01'


@pytest.mark.parametrize('query', ['维护', '设置', '图形入口'])
def test_explicit_short_keyword_still_works(retrieval_store, query):
    assert retrieval_store.search(query, 'SYN-team-tools', ['windows'])['results']


def test_unrelated_semantic_paraphrase_is_not_claimed_as_supported(retrieval_store):
    # This deliberately has no useful lexical anchors in the fixture. A local
    # character matcher must not claim it understands arbitrary synonyms.
    query = '文员仅会鼠标点选，盼接班后自主改参数。'
    assert retrieval_store.search(query, 'SYN-team-tools', ['windows'])['results'] == []
