"""Bounded software-handover vocabulary, evaluated at search time only.

These are retrieval hints, not personal preferences or applicability decisions.
No recursive expansion, fuzzy matching, model calls, or note-derived rules.
"""
import re


GROUPS = {
    'non_coding': ('非技术', '非程序员', '不写代码', '不会写代码', '不懂代码',
                   '不会编程', '不懂编程', '没有编程经验', '不具备编程经验'),
    'handover': ('交接', '移交', '接手', '接管'),
    'settings_ui': ('图形入口', '可视化配置', '设置窗口', '配置窗口', '设置界面', '配置界面'),
}
_PATTERNS = {name: re.compile('|'.join(map(re.escape, sorted(terms, key=lambda t: (-len(t), t)))))
             for name, terms in GROUPS.items()}
_TOPIC_FIELDS = {'title', 'tags', 'aliases', 'considerations', 'applies_when', 'action'}
_SOFTWARE = re.compile(r'软件|程序|脚本|代码|编程|开发|配置|参数|界面|小工具|报表|\bexcel\b|\bcsv\b')


def _occurrences(text):
    return {name: list(pattern.finditer(text)) for name, pattern in _PATTERNS.items()}


def _software_topic(text, occurrences):
    if occurrences['settings_ui']:
        return True
    # "非程序员" describes a person's skill, not the subject of the task.
    # Do not let that phrase turn an unrelated gardening handover into software.
    remaining = list(text)
    for matches in occurrences.values():
        for match in matches:
            remaining[match.start():match.end()] = ' ' * (match.end() - match.start())
    return bool(_SOFTWARE.search(''.join(remaining)))


def match_concepts(query, fields):
    """One matched concept per group, with original query positions and source.

    Only substantive fields provide synonym evidence. Sources/body often hold
    boilerplate; they must not introduce a second topic through expansion.
    """
    query_matches = _occurrences(query)
    topic_fields = [(name, weight, text) for name, weight, text, *_ in fields if name in _TOPIC_FIELDS]
    topic_text = '\n'.join(text for _, _, text in topic_fields)
    expand = (_software_topic(query, query_matches)
              and _software_topic(topic_text, _occurrences(topic_text)))
    matched = []
    for concept, occurrences in query_matches.items():
        if not occurrences:
            continue
        query_terms = {m.group() for m in occurrences}
        candidates = [(weight, name, match.group()) for name, weight, text in topic_fields
                      for match in _PATTERNS[concept].finditer(text)
                      if expand or match.group() in query_terms]
        if not candidates:
            continue
        weight, field, record_term = max(candidates, key=lambda row: (row[0], len(row[2])))
        # Prefer a literal occurrence if this field contains the same phrase.
        query_match = next((m for m in occurrences if m.group() == record_term), occurrences[0])
        spans = [(m.start(), m.end()) for m in occurrences
                 if expand or m.group() in {row[2] for row in candidates}]
        matched.append({'concept': concept, 'query_term': query_match.group(),
                        'record_term': record_term, 'field': field, '_weight': weight,
                        '_spans': spans})
    return matched


def independent_evidence(query, features, concepts):
    """Count each concept once and do not count its native fragments again."""
    covered = [span for concept in concepts for span in concept['_spans']]
    spans = {concept['_spans'][0] for concept in concepts}
    for feature in features:
        start = query.find(feature)
        end = start + len(feature)
        if start >= 0 and not any(start < right and left < end for left, right in covered):
            spans.add((start, end))
    merged = []
    for start, end in sorted(spans):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return len(merged)


def expansion_evidence(concepts):
    """Separate equivalence hints from actual literal matched_terms."""
    return [{key: value for key, value in concept.items() if not key.startswith('_')}
            for concept in concepts if concept['query_term'] != concept['record_term']]
