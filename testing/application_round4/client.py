"""Read-only bridge for one manually started, isolated R04 application case."""
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

PROJECT = next((p for p in Path(__file__).resolve().parents
                if (p / 'pyproject.toml').is_file() and (p / 'src/decision_memory').is_dir()), None)
if PROJECT is None:
    raise RuntimeError('Place this client under a source checkout containing pyproject.toml and src/decision_memory')
ROOT = Path(__file__).resolve().parent

async def main(args):
    if not ROOT.is_relative_to((PROJECT / 'testing/runs').resolve()):
        raise ValueError('Only a prepared testing/runs child is allowed')
    meta = json.loads((ROOT / 'run.json').read_text(encoding='utf-8'))
    if meta.get('round_id') != 'R04-application-normal' or not meta.get('synthetic_only'):
        raise ValueError('Not a prepared synthetic R04 run')
    bank = (ROOT / 'bank').resolve()
    if not bank.is_relative_to(ROOT) or not (bank / '.decision-memory/manifest.json').is_file():
        raise ValueError('Invalid isolated bank')
    temporary = ROOT / 'tmp'
    temporary.mkdir(exist_ok=True)
    params = {'project': 'SYN-team-tools', 'environments': ['windows']}
    if args.tool == 'get_memory':
        if not args.record_id:
            raise ValueError('Record ID required')
        params['record_id'] = args.record_id
    else:
        if not args.query:
            raise ValueError('Query required')
        params['query'] = args.query
        if args.tool == 'build_context':
            params['max_chars'] = 5000
    call_id = uuid.uuid4().hex
    evidence = {'call_id': call_id, 'synthetic_only': True, 'bank': str(bank),
                'tool': args.tool, 'params': params,
                'started_at': datetime.now(timezone.utc).isoformat()}
    folder = ROOT / 'calls'
    folder.mkdir(exist_ok=True)
    def save():
        (folder / f'{call_id}.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    evidence['status'] = 'started'
    save()
    try:
        server = StdioServerParameters(command=sys.executable,
            args=['-B', '-m', 'decision_memory', '--vault', str(bank), 'mcp'], cwd=str(PROJECT),
            env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8',
                 'TMP': str(temporary), 'TEMP': str(temporary)})
        async with Client(server, mode='auto', read_timeout_seconds=15) as client:
            exposed = (await client.list_tools()).tools
            if {t.name for t in exposed} != {'search_memory', 'build_context', 'get_memory'}:
                raise ValueError('Unexpected tools')
            if not all(t.annotations.read_only_hint for t in exposed):
                raise ValueError('Read-only annotations required')
            result = await client.call_tool(args.tool, params)
            evidence.update(status='completed', is_error=bool(result.is_error), result=result.structured_content)
    except Exception as exc:
        evidence.update(status='failed', is_error=True, error={'type': type(exc).__name__, 'message': str(exc)})
    evidence['finished_at'] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 1 if evidence.get('is_error') else 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tool', choices=['search_memory', 'build_context', 'get_memory'], required=True)
    parser.add_argument('--query')
    parser.add_argument('--record-id')
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(asyncio.run(main(parser.parse_args())))
