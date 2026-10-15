"""Read-only MCP bridge for one arm of a synthetic decision experiment."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

from mcp import Client
from mcp.client.stdio import StdioServerParameters


PROJECT = Path(__file__).resolve().parents[2]


async def main(args):
    root = args.run_dir.resolve()
    allowed = (PROJECT / 'testing/runs').resolve()
    if root == allowed or not root.is_relative_to(allowed):
        raise ValueError('Run directory outside testing/runs')
    meta = json.loads((root / 'run.json').read_text(encoding='utf-8'))
    if meta.get('round_id') != 'R03-behavior' or not meta.get('synthetic_only'):
        raise ValueError('Not a prepared synthetic R03 run')
    bank = (root / 'banks' / args.arm).resolve()
    if not bank.is_relative_to(root) or not (bank / '.decision-memory/manifest.json').exists():
        raise ValueError('Invalid isolated bank')
    temporary = root / 'tmp' / args.arm
    temporary.mkdir(parents=True, exist_ok=True)
    params = {'project': 'SYN-team-tools', 'environments': ['windows']}
    if args.tool == 'get_memory':
        if not args.record_id:
            raise ValueError('get_memory requires --record-id')
        params['record_id'] = args.record_id
    else:
        if not args.query:
            raise ValueError('Search/context requires --query')
        params['query'] = args.query
        if args.tool == 'build_context':
            params['max_chars'] = 5000
    call_id = uuid.uuid4().hex
    evidence = {'call_id': call_id, 'synthetic_test_only': True, 'arm': args.arm,
                'bank': str(bank), 'tool': args.tool, 'params': params,
                'time_utc': datetime.now(timezone.utc).isoformat()}
    try:
        server = StdioServerParameters(command=sys.executable,
            args=['-B', '-m', 'decision_memory', '--vault', str(bank), 'mcp'],
            cwd=str(PROJECT), env={**os.environ, 'PYTHONUTF8': '1',
                                  'TEMP': str(temporary), 'TMP': str(temporary)})
        async with Client(server, mode='auto', read_timeout_seconds=15) as client:
            tools = (await client.list_tools()).tools
            if {t.name for t in tools} != {'search_memory', 'get_memory', 'build_context'}:
                raise ValueError('Unexpected MCP tools')
            if not all(t.annotations.read_only_hint for t in tools):
                raise ValueError('Tool annotations are not read-only')
            result = await client.call_tool(args.tool, params)
            evidence.update(is_error=bool(result.is_error), result=result.structured_content)
    except Exception as exc:
        evidence.update(is_error=True, error={'type': type(exc).__name__, 'message': str(exc)})
    folder = root / 'calls' / args.arm
    folder.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(evidence, ensure_ascii=False, indent=2) + '\n'
    (folder / f'{call_id}.json').write_text(raw, encoding='utf-8')
    print(raw)
    return 1 if evidence['is_error'] else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--arm', choices=['A0', 'A1'], required=True)
    parser.add_argument('--tool', choices=['search_memory', 'build_context', 'get_memory'], required=True)
    parser.add_argument('--query')
    parser.add_argument('--record-id')
    sys.exit(asyncio.run(main(parser.parse_args())))
