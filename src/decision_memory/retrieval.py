"""Local lexical ranking; no model calls or claim of semantic understanding."""

from collections import Counter
import math
import re

from .models import Record
from .synonyms import expansion_evidence, independent_evidence, match_concepts


_PARTS = re.compile(r"[\u4e00-\u9fff]+|[a-z0-9_]+(?:[-.][a-z0-9_]+)*")
_ASCII = re.compile(r"[a-z0-9_]+(?:[-.][a-z0-9_]+)*")
_FILLER = set("应该 怎样 怎么 如何 一个 这个 那个 需要 可以 是否 什么 哪些 我们 你们 这次 现在 进行 不是".split())
_BROAD = set("维护 设置 工具 内部 调整 配置 操作 使用 项目 问题 方案 工作 资料 同事 交接 接手 接管 移交".split())
_BOUNDARIES = re.compile('|'.join(map(re.escape, sorted(_FILLER | _BROAD, key=lambda s: (-len(s), s)))))
_TASK_EXCLUSION = re.compile(r"(?:不做|不需要|不考虑|不涉及|无需|排除)[^，,；;。！？!?]+[，,；;]\s*(?=只|仅|而是|重点)")
_FIELDS = (("title", 3), ("tags", 2.5), ("aliases", 2.5),
           ("considerations", 2), ("applies_when", 2), ("action", 2),
           ("rationale", 1), ("exceptions", 1), ("body", .5), ("sources", .5))


def _parts(text):
    return list(dict.fromkeys(_PARTS.findall(text.casefold())))


def _features(parts):
    units = set()
    for part in parts:
        if part.isascii():
            if len(part) >= 2:
                units.add(part)
        else:
            # A broad verb must not create evidence at its character boundary:
            # 准备调整 and 设备调整 must not corroborate each other through 备调.
            for chunk in _BOUNDARIES.split(part):
                units.update(chunk[i:i + 2] for i in range(len(chunk) - 1))
            units.update(word for word in _BROAD if word in part)
    return units - _FILLER


def _independent_spans(query, features):
    """Count disjoint evidence, not each overlapping bigram as a new clue."""
    return independent_evidence(query, features, [])


def rank_records(query: str, records: list[Record], phrase_scores: dict) -> dict:
    """Require corroborating fragments for long queries, then rank by field/IDF.

    Bigram overlap is only lexical evidence. Long questions require disjoint
    evidence or an explicit meaningful phrase/label; short keywords still work.
    Version/status/scope checks remain the Store's responsibility.
    """
    # Only explicit task exclusions followed by a positive focus clause. This
    # does not attempt general negation or decide a memory's applicability.
    focus = _TASK_EXCLUSION.sub(' ', query.casefold())
    parts = _parts(focus)
    features = _features(parts)
    keyword_query = sum(map(len, parts)) <= 8
    documents = {}
    frequency = Counter()
    for record in records:
        fields = []
        for name, weight in _FIELDS:
            value = getattr(record, name)
            text = ("\n".join(value) if isinstance(value, list) else value).casefold()
            fields.append((name, weight, text, _BOUNDARIES.sub(' ', text), set(_ASCII.findall(text))))
        # IDs are searchable deliberately; schema keys, kind, scope and approval
        # metadata do not become accidental evidence for a topic query.
        fields.append(('id', 4, record.id.casefold(), record.id.casefold(), {record.id.casefold()}))
        hits, exact = {}, {}
        for _, weight, text, content, words in fields:
            for feature in features:
                present = feature in words if feature.isascii() else feature in (text if feature in _BROAD else content)
                if present:
                    hits[feature] = max(hits.get(feature, 0), weight)
            for part in parts:
                present = part in words if part.isascii() else part in text
                if present and part not in _FILLER and (keyword_query or len(part) >= 2):
                    exact[part] = max(exact.get(part, 0), weight)
        # A genuine tag/alias inside a question is an explicit topic clue.
        # Generic tags and singleton characters cannot use this path.
        for label in record.tags + record.aliases:
            label = label.casefold()
            if len(label) >= 2 and label not in _FILLER | _BROAD and label in focus:
                exact[label] = max(exact.get(label, 0), 2.5)
        concepts = match_concepts(focus, fields)
        documents[record.id] = (hits, exact, concepts)
        frequency.update(hits.keys())
        frequency.update('concept:' + c['concept'] for c in concepts)
    ranked = {}
    for record in records:
        hits, exact, concepts = documents[record.id]
        strong = set(hits) - _BROAD
        explicit = bool(exact) and (keyword_query or any(p not in _BROAD for p in exact))
        evidence_count = independent_evidence(focus, strong, concepts)
        if not (explicit or evidence_count >= 2 or keyword_query and concepts):
            continue
        score = sum(weight * (1 + math.log((1 + len(records)) / (1 + frequency[feature])))
                    * (.2 if feature in _BROAD else 1)
                    for feature, weight in hits.items())
        score += sum(weight * (.2 if part in _BROAD else 1) for part, weight in exact.items())
        # Discount expansion and cap it at one contribution per concept. Never
        # append synonym text to the query: that would invent independent spans.
        score += sum(.75 * c['_weight'] * (1 + math.log(
            (1 + len(records)) / (1 + frequency['concept:' + c['concept']]))) for c in concepts)
        # FTS exact-phrase evidence is a small tie-breaker, never an admission
        # rule: its underlying JSON index also contains non-topic metadata.
        score += .05 * phrase_scores.get(record.id, 0)
        if record.id.casefold() in parts:
            score += 100
        matched = sorted(set(hits) | set(exact), key=lambda term: (query.casefold().find(term), -len(term)))
        ranked[record.id] = (score, matched, expansion_evidence(concepts))
    return ranked
