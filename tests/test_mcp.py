import asyncio
import os
import sys
import pytest

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from decision_memory.store import digest


@pytest.mark.parametrize('mode', ['auto', 'legacy'])
def test_stdio_tools_from_three_project_directories(store, record, tmp_path, mode):
    relative = store.stage(record)
    store.publish(relative, digest(store.draft(relative)[1]))

    async def exercise():
        for name in ('项目甲', 'project-beta', '项目 空格'):
            cwd = tmp_path / name
            cwd.mkdir()
            parameters = StdioServerParameters(command=sys.executable,
                args=['-m', 'decision_memory', '--vault', str(store.root), 'mcp'],
                cwd=str(cwd), env={**os.environ, 'PYTHONUTF8': '1'})
            async with Client(parameters, read_timeout_seconds=10, mode=mode) as client:
                tools = (await client.list_tools()).tools
                names = {t.name for t in tools}
                assert names == {'search_memory', 'get_memory', 'build_context'}
                assert all(t.annotations.read_only_hint for t in tools)
                search = await client.call_tool('search_memory', {'query': '维护'})
                assert not search.is_error, search.content
                assert search.structured_content['results'][0]['record']['id'] == record.id
                result = await client.call_tool('get_memory', {'record_id': record.id})
                assert result.structured_content['record']['exceptions'] == record.exceptions
                context = await client.call_tool('build_context', {'query': '维护'})
                assert context.structured_content['memories'][0]['sources'] == record.sources
                missing = await client.call_tool('publish', {})
                assert missing.is_error

    asyncio.run(exercise())
