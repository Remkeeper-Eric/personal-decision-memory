"""Generate a local test summary from supplied JUnit evidence, not live memory."""
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sqlite3
import tomllib
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description='Summarize this checkout test output without reading personal memory')
    parser.add_argument('--junit', type=Path, default=ROOT / 'runtime/pytest.xml')
    parser.add_argument('--output', type=Path, default=ROOT / 'runtime/release-report.json')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'runtime').resolve()):
        parser.error('Report output must stay under this checkout runtime/')
    xml = ET.parse(args.junit).getroot()
    suites = xml.findall('testsuite') if xml.tag == 'testsuites' else [xml]
    counts = {key: sum(int(s.get(key, '0')) for s in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    report = {
        'release': tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version'],
        'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
        'dependencies': {name: version(name) for name in ('mcp', 'pydantic', 'PyYAML', 'pytest')},
        'engineering_tests': counts,
        'all_engineering_tests_passed': counts['tests'] > 0 and not any(counts[k] for k in ('failures', 'errors', 'skipped')),
        'manual_checks': [],
        'note': 'JUnit evidence only; no live vault read, no claim of GUI or personalization acceptance.'
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
