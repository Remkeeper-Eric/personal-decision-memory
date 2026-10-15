"""Build a source-only ZIP from an explicit allowlist; never traverse user data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ('src', 'scripts', 'skills', 'tests', 'testing', 'docs', 'examples', '.github', '.cursor/rules')
TOP_FILES = ('.gitignore', '.editorconfig', 'AGENTS.md', 'README.md', 'CONTRIBUTING.md',
             'CHANGELOG.md', 'LICENSE', 'pyproject.toml', 'requirements.lock.txt')
SUFFIXES = {'.py', '.md', '.json', '.yaml', '.yml', '.html', '.ps1', '.mdc', '.toml', '.txt'}
PRIVATE_PARTS = {'vault', 'runtime', 'verification', 'dist', 'build', '.git', '.venv',
                 '__pycache__', '.pytest_cache', '.decision-memory', 'install-backups'}
SECRET = re.compile(r'(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
LOCAL_HOME = re.compile(r'[A-Za-z]:[/\\]Users[/\\][^/\\\s\"\']+')


def allowed(relative):
    parts = relative.parts
    return (not any(p in PRIVATE_PARTS or p.endswith('.egg-info') for p in parts)
            and not (len(parts) >= 2 and parts[:2] == ('testing', 'runs'))
            and not any(p.startswith('.env') for p in parts)
            and (relative.as_posix() in TOP_FILES or relative.suffix in SUFFIXES))


def source_files(root=ROOT):
    root = root.resolve()
    found = []
    candidates = [root / name for name in TOP_FILES]
    for name in DIRECTORIES:
        folder = root / name
        if folder.is_symlink():
            raise ValueError(f'Refusing a linked source directory: {name}')
        if folder.is_dir():
            # Prune private directories before descending, including testing/runs.
            import os
            for current, dirs, names in os.walk(folder, followlinks=False):
                parent = Path(current)
                for directory in list(dirs):
                    path = parent / directory
                    relative = path.relative_to(root)
                    if path.is_symlink():
                        raise ValueError(f'Refusing a linked source path: {relative}')
                    if directory in PRIVATE_PARTS or directory.endswith('.egg-info') or relative.parts[:2] == ('testing', 'runs'):
                        dirs.remove(directory)
                candidates.extend(parent / n for n in names)
    for path in candidates:
        relative = path.relative_to(root)
        if not allowed(relative):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f'Refusing a linked source file: {relative}')
        if path.is_file():
            found.append(path)
    return sorted(set(found))


def inspect(root=ROOT):
    root = root.resolve()
    files = source_files(root)
    problems = []
    for path in files:
        text = path.read_text(encoding='utf-8-sig')
        if SECRET.search(text):
            problems.append({'file': path.relative_to(root).as_posix(), 'reason': 'possible credential or private key'})
        if LOCAL_HOME.search(text):
            problems.append({'file': path.relative_to(root).as_posix(), 'reason': 'machine-specific Windows home path'})
    required = ('README.md', 'LICENSE', 'pyproject.toml', 'src/decision_memory/cli.py')
    problems.extend({'file': name, 'reason': 'required release file missing'} for name in required if not (root / name).is_file())
    if problems:
        # Report filenames only, never echo a potential secret.
        raise ValueError(json.dumps(problems, ensure_ascii=False))
    return files


def build(root=ROOT, destination=None):
    root = root.resolve()
    files = inspect(root)
    metadata = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    name, version = metadata['name'], metadata['version']
    label = f'{name}-{version}'
    if not re.fullmatch(r'[A-Za-z0-9._-]+', label):
        raise ValueError('Invalid project name/version for archive')
    folder = (destination or root / 'dist').resolve()
    if not folder.is_relative_to(root / 'dist'):
        raise ValueError('Release destination must stay under this checkout dist/')
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    archive = folder / f'{label}-{stamp}-source.zip'
    manifest = {'project': name, 'version': version, 'license': 'MIT',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'files': {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                'excluded': ['private vaults', 'runtime', 'verification', 'testing/runs', '.venv', 'Git state'],
                'note': 'Source bundle. Pattern checks do not replace review of the upload list.'}
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as output:
        for path in files:
            output.write(path, f'{label}/{path.relative_to(root).as_posix()}')
        output.writestr(f'{label}/RELEASE-MANIFEST.json', manifest_bytes)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n', encoding='utf-8')
    return {'archive': str(archive), 'sha256': checksum, 'source_files': len(files)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Check or package public source files; no Git commit or upload')
    parser.add_argument('--check', action='store_true', help='Inspect the source list without creating a ZIP')
    args = parser.parse_args()
    try:
        result = {'source_files': len(inspect()), 'check': 'passed'} if args.check else build()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, f'{exc}\n')
