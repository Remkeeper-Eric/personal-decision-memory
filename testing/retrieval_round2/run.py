"""One frozen, expanded retrieval round through an isolated real MCP server."""

import argparse
import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from decision_memory.models import Record
from decision_memory.store import Store, digest
from testing.fixed_retrieval.run import checks_for, changes, sha, snapshot, timestamp, write_json


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
RUNS = (PROJECT / 'testing/runs').resolve()
PRODUCTION = (PROJECT / 'vault').resolve()
BACKEND = 'sqlite-fts5-trigram+field-bigrams-v1'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def boundary(path):
    path = path.resolve()
    if path == RUNS or not path.is_relative_to(RUNS) or path.is_relative_to(PRODUCTION):
        raise ValueError('Run must be an independent child of testing/runs')
    return path


def prepare(root, expected_backend=BACKEND, fresh_server_only=False):
    root = boundary(root)
    if root.exists():
        raise ValueError('Refusing to overwrite an existing round')
    base = PROJECT / 'testing/fixed_retrieval/corpus.json'
    extra = read(HERE / 'extra-corpus.json')
    if extra.get('synthetic_only') is not True:
        raise ValueError('Synthetic corpus only')
    records = [Record.model_validate(row).model_dump()
               for row in read(base)['records'] + extra['records']]
    cases = read(HERE / 'cases.json')['cases']
    if len(records) != 8 or len(cases) != 12 or len({r['id'] for r in records}) != 8:
        raise ValueError('Unexpected corpus/case structure')
    inputs = root / 'inputs'
    inputs.mkdir(parents=True)
    write_json(inputs / 'corpus.json', {'synthetic_only': True, 'records': records})
    shutil.copyfile(HERE / 'cases.json', inputs / 'cases.json')
    sources = sorted((PROJECT / 'src/decision_memory').glob('*.py'))
    sources += [HERE / 'run.py', PROJECT / 'testing/fixed_retrieval/run.py', PROJECT / 'AGENTS.md']
    hashes = {}
    for source in sources:
        name = source.relative_to(PROJECT).as_posix()
        target = inputs / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[name] = sha(source)
    write_json(inputs / 'source-hashes.json', hashes)
    write_json(root / 'freeze.json', {'frozen_at': timestamp(),
        'files': {p.relative_to(inputs).as_posix(): sha(p) for p in inputs.rglob('*') if p.is_file()}})
    write_json(root / 'run.json', {'status': 'prepared', 'created_at': timestamp(),
        'human_review': 'pending', 'next_round_authorized': False, 'synthetic_only': True,
        'records': 8, 'cases': 12, 'model_calls': 0,
        'expected_backend': expected_backend, 'fresh_server_only': fresh_server_only,
        'note': 'Same assistant authored cases; not an independent blind evaluation.'})
    print(json.dumps({'status': 'prepared', 'run_dir': str(root)}, ensure_ascii=False))


def report(root, outcomes, audit):
    passed = sum(c['status'] == 'pass' for c in outcomes)
    connection_note = ('本次只验证新启动的隔离服务，不声称当前聊天连接已经重新加载。'
                       if read(root / 'run.json').get('fresh_server_only') else
                       '当前正式连接已通过实际只读查询返回修复版 backend，证据见 connection-check.json。')
    lines = ['# R02 扩展检索测试结果', '', f'执行完成：{timestamp()}；待用户复核。', '',
        connection_note, '',
        f'本轮 8 条合成记录；Windows / SYN-team-tools 范围下 7 条候选，默认最多返回 5 条。12 项中 {passed} 项符合预期。', '',
        '使用新启动的只读 MCP 服务连接独立临时库；没有模型决策会话，没有更改正式 MCP 配置。', '',
        '题目、语料和标准先冻结；无关题要求结果为空，候选召回题要求目标进入指定排位。条件成立与否仍由后续决策测试判断。', '']
    for case in outcomes:
        lines += [f"## {case['id']} {case['title']}：{'符合预期' if case['status'] == 'pass' else '未达到预期'}", '',
                  f"类别：{case['category']}。", '']
        for call in case['calls']:
            params = call['input']['params']
            lines += [f"- 调用：{call['tool']}；{params.get('query', params.get('record_id'))}"]
            value = call['result'] or {}
            rows = value.get('results', value.get('memories', [value] if 'record' in value else []))
            ids = [(row.get('record', row)['id'], row.get('version')) for row in rows]
            lines += [f'- 实际返回：{json.dumps(ids, ensure_ascii=False)}。']
            for check in call['checks']:
                if not check['passed']:
                    lines += [f"- 未满足：{check['name']}；实际 {json.dumps(check.get('actual'), ensure_ascii=False)}。"]
            lines += ['']
        output = (root / 'cases' / case['id'] / 'output.json').as_posix()
        lines += [f'[完整输入、输出及检查]({output})', '']
    lines += ['## 核验与解释边界', '', json.dumps(audit, ensure_ascii=False), '',
        '本轮不把测试中模拟的 user-approved 状态解释为用户认可合成经验；正式记忆未写入。', '',
        'source_type 仅验证外部资料类型保留，negation_boundary 仅验证排序；都不能证明 Codex 会理解来源权威或否定条件。', '',
        'semantic_boundary 未召回应计为未达到自然语言检索目标，不能因为已知没有语义向量就改判通过。', '',
        '本轮结束，保留所有失败，不增加别名或修改评分，不自动进入下一轮。', '']
    (root / 'report.md').write_text('\n'.join(lines), encoding='utf-8')


async def execute(root):
    root = boundary(root)
    meta = read(root / 'run.json')
    if meta['status'] != 'prepared':
        raise ValueError('Round already executed; results cannot be overwritten')
    inputs = root / 'inputs'
    for name, expected in read(root / 'freeze.json')['files'].items():
        if sha(inputs / name) != expected:
            raise ValueError('Frozen input changed: ' + name)
    for name, expected in read(inputs / 'source-hashes.json').items():
        if sha(PROJECT / name) != expected:
            raise ValueError('Source changed: ' + name)
    expected_backend = meta.get('expected_backend', BACKEND)
    if not meta.get('fresh_server_only', False):
        connection = read(root / 'connection-check.json')
        if connection['structuredContent']['backend'] != expected_backend:
            raise ValueError('Current connection has not loaded the repair')
    for name in ('tmp', 'backups'):
        (root / name).mkdir()
    os.environ['TMP'] = os.environ['TEMP'] = str(root / 'tmp')
    meta.update(status='running', started_at=timestamp(), python=sys.version,
                test_vault=str(root / 'vault'), backup_root=str(root / 'backups'), backup_used=False)
    write_json(root / 'run.json', meta)
    before = snapshot(PRODUCTION)
    write_json(root / 'production-before.json', before)
    records = {row['id']: row for row in read(inputs / 'corpus.json')['records']}
    store = Store(root / 'vault')
    store.init()
    setup = []
    for data in records.values():
        record = Record.model_validate(data)
        relative = store.stage(record)
        setup.append({'operation': 'activate_synthetic_fixture_only',
                      'result': store.publish(relative, digest(store.draft(relative)[1]))})
    write_json(root / 'setup.json', setup)
    write_json(root / 'state-before.json', {'manifest': read(store.manifest_path), 'doctor': store.doctor()})
    parameters = StdioServerParameters(command=sys.executable,
        args=['-B', '-m', 'decision_memory', '--vault', str(store.root), 'mcp'], cwd=str(PROJECT),
        env={**os.environ, 'PYTHONUTF8': '1'})
    outcomes = []
    tools_map = {'search': 'search_memory', 'context': 'build_context', 'get': 'get_memory'}
    async with Client(parameters, mode='auto', read_timeout_seconds=15) as client:
        tools = (await client.list_tools()).tools
        write_json(root / 'tools.json', {'names': [t.name for t in tools],
            'read_only': [bool(t.annotations.read_only_hint) for t in tools]})
        if {t.name for t in tools} != set(tools_map.values()) or not all(t.annotations.read_only_hint for t in tools):
            raise ValueError('Unexpected test MCP tool set')
        for case in read(inputs / 'cases.json')['cases']:
            calls = []
            for op in case['operations']:
                started = time.perf_counter()
                tool = tools_map[op['method']]
                response = await client.call_tool(tool, op['params'])
                result = response.structured_content
                error = {'type': 'MCPError', 'message': str(response.content)} if response.is_error else None
                checks = checks_for(op, result, error, records)
                if op['expect'].get('empty'):
                    checks.append({'name': '不返回无关记录', 'passed': result is not None and result.get('results') == [],
                                   'actual': [h['record']['id'] for h in (result or {}).get('results', [])]})
                if op['method'] == 'search':
                    checks.append({'name': '修复版 backend', 'passed': result is not None and result.get('backend') == expected_backend,
                                   'actual': (result or {}).get('backend')})
                if result:
                    rows = result.get('results', result.get('memories', [result] if 'record' in result else []))
                    checks.append({'name': '返回来源位于本轮测试库', 'passed': all(
                        Path(row['source_path']).resolve().is_relative_to(store.root) for row in rows)})
                calls.append({'input': op, 'tool': tool, 'result': result, 'error': error,
                    'elapsed_ms': round((time.perf_counter() - started) * 1000, 3), 'checks': checks})
            outcome = {**case, 'calls': calls, 'status': 'pass' if all(
                check['passed'] for call in calls for check in call['checks']) else 'fail'}
            write_json(root / 'cases' / case['id'] / 'output.json', outcome)
            outcomes.append(outcome)
            if changes(before, snapshot(PRODUCTION)) != {'root_existence_changed': False, 'added': [], 'removed': [], 'changed': []}:
                raise ValueError('Production files changed during isolated test')
    after = snapshot(PRODUCTION)
    write_json(root / 'production-after.json', after)
    write_json(root / 'state-after.json', {'manifest': read(store.manifest_path), 'doctor': store.doctor()})
    audit = {'production_unchanged': before == after,
             'frozen_inputs_unchanged': all(sha(inputs / name) == expected for name, expected in read(root / 'freeze.json')['files'].items()),
             'source_unchanged': all(sha(PROJECT / name) == expected for name, expected in read(inputs / 'source-hashes.json').items())}
    write_json(root / 'audit.json', audit)
    counts = dict(Counter(c['status'] for c in outcomes))
    write_json(root / 'results.json', {'counts': counts, 'cases': outcomes, 'audit': audit})
    report(root, outcomes, audit)
    meta.update(status='awaiting_user_review', finished_at=timestamp(), counts=counts,
                mcp_calls=sum(len(c['calls']) for c in outcomes))
    write_json(root / 'run.json', meta)
    print(json.dumps({'run_dir': str(root), 'counts': counts, 'audit': audit,
                      'mcp_calls': meta['mcp_calls']}, ensure_ascii=False))
    return 0 if counts.get('fail', 0) == 0 and all(audit.values()) else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'execute'])
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--expected-backend', default=BACKEND)
    parser.add_argument('--fresh-server-only', action='store_true')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.run_dir, args.expected_backend, args.fresh_server_only)
        return 0
    return asyncio.run(execute(args.run_dir))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
