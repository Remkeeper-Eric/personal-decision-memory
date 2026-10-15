"""Objective post-run evidence audit, separate from semantic assessment."""
import argparse
import json
from pathlib import Path
import re
from decision_memory.models import Record, in_scope
from testing.fixed_retrieval.run import snapshot, changes, sha, timestamp, write_json

PROJECT = Path(__file__).resolve().parents[2]
read = lambda p: json.loads(p.read_text(encoding='utf-8'))

def main(root):
    root = root.resolve()
    assert root.is_relative_to(PROJECT / 'testing/runs')
    case = read(root / 'inputs/case.json')
    corpus = {r.id: r for r in map(Record.model_validate, read(root / 'inputs/corpus.json')['records'])}
    freeze = read(root / 'freeze.json')['files']
    thread = read(root / 'thread-visible.json')
    items = [item for turn in thread['turns'] for item in turn['items']]
    final = next(i['text'] for i in reversed(items) if i['type'] == 'agentMessage' and i.get('phase') == 'final_answer')
    answer = (root / 'outputs/answer.md').read_text(encoding='utf-8')
    calls = [read(p) for p in sorted((root / 'calls').glob('*.json'))]
    success = [c for c in calls if c['status'] == 'completed' and not c.get('is_error')]
    memories = [m for c in success for m in c.get('result', {}).get('memories', [])]
    manifest = read(root / 'bank/.decision-memory/manifest.json')
    verified = []
    fields = ('kind', 'title', 'project_scope', 'environments', 'considerations', 'rationale', 'applies_when', 'exceptions', 'action', 'sources', 'verification')
    for m in memories:
        expected = corpus[m['id']].model_dump()
        entry = manifest['entries'][m['id']]
        source = Path(m['source_path']).resolve()
        verified.append({'id': m['id'], 'version': m['version'],
            'fields_equal': all(m[f] == expected[f] for f in fields),
            'source_valid': source == (root / 'bank' / entry['path']).resolve() and source.is_relative_to(root / 'bank'),
            'version_and_hash_valid': m['version'] == entry['version'] and sha(source) == entry['sha256'] and entry['status'] == 'active',
            'scope_valid': in_scope(corpus[m['id']], 'SYN-team-tools', ['windows'])})
    def immutable(files):
        return {n: v for n, v in files.items() if not n.startswith('.decision-memory/index.sqlite3')}
    production = snapshot(PROJECT / 'vault')
    write_json(root / 'production-after.json', production)
    audit = {'checked_at': timestamp(), 'case': case['id'], 'thread_id': thread['thread']['id'],
        'thread_title': thread['thread']['title'], 'turn_completed': thread['turns'][0]['status'] == 'completed',
        'frozen_mismatches': [n for n, h in freeze.items() if sha(root / n) != h],
        'source_mismatches': [p.relative_to(root / 'inputs/source').as_posix() for p in (root / 'inputs/source').rglob('*.py') if sha(p) != sha(PROJECT / p.relative_to(root / 'inputs/source'))],
        'prompt_matches_dispatch': read(root / 'dispatch.json')['prompt'] == (root / 'prompt.md').read_text(encoding='utf-8'),
        'production_changes': changes(read(root / 'production-before.json'), production),
        'manifest_unchanged': manifest == read(root / 'inputs/bank-before.json')['manifest'],
        'test_immutable_files_unchanged': immutable(read(root / 'bank-snapshot-before.json')['files']) == immutable(snapshot(root / 'bank')['files']),
        'target_retrieved': any(m['id'] == case['target'] and m['version'] == 1 for m in memories),
        'records_verified': verified, 'call_log_count': len(calls), 'successful_calls': len(success),
        'queries': [c['params'].get('query') for c in calls],
        'query_call_limit_observed': len([c for c in calls if c['tool'] in ('search_memory', 'build_context')]) <= 2,
        'answer_han_chars': len(re.findall(r'[\u4e00-\u9fff]', answer)),
        'answer_exact_ignoring_outer_whitespace': answer.strip() == final.strip(),
        'answer_body_matches_ignoring_whitespace': ''.join(answer.split()) == ''.join(final.split()),
        'trace_complete': not thread['page']['hasMore'] and not any(i.get('output', {}).get('truncated') for i in items),
        'visible_file_changes': [c['path'] for i in items if i['type'] == 'fileChange' for c in i['changes']],
        'hidden_reasoning_saved': False, 'model_id': None, 'token_usage': None}
    audit['objective_checks_passed'] = all([audit['turn_completed'], not audit['frozen_mismatches'], not audit['source_mismatches'],
        audit['prompt_matches_dispatch'], not any(audit['production_changes'].values()), audit['manifest_unchanged'],
        audit['test_immutable_files_unchanged'], audit['target_retrieved'], audit['answer_body_matches_ignoring_whitespace'],
        audit['answer_han_chars'] <= 900, audit['trace_complete'], audit['query_call_limit_observed'],
        all(all(row[k] for k in ('fields_equal', 'source_valid', 'version_and_hash_valid', 'scope_valid')) for row in verified)])
    write_json(root / 'audit.json', audit)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit['objective_checks_passed'] else 1

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    raise SystemExit(main(parser.parse_args().root))
