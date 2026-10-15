"""Privacy and portability checks for the actual source release path."""
import importlib.util
from pathlib import Path
import shutil
import zipfile

import pytest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_release', PROJECT / 'scripts/prepare_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_archive_excludes_private_data_even_inside_source_directories(tmp_path):
    root = tmp_path / 'new checkout'
    (root / 'src/decision_memory').mkdir(parents=True)
    for name in ('README.md', 'LICENSE', 'pyproject.toml'):
        shutil.copyfile(PROJECT / name, root / name)
    (root / 'src/decision_memory/cli.py').write_text('# public source\n', encoding='utf-8')
    for name in ('vault/private.md', 'runtime/review-session.json', 'verification/report.json',
                 'testing/runs/old/answer.md', 'src/runtime/secret.json', 'scripts/.env'):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('private fixture', encoding='utf-8')
    result = release.build(root)
    with zipfile.ZipFile(result['archive']) as archive:
        names = archive.namelist()
    assert any(n.endswith('/src/decision_memory/cli.py') for n in names)
    assert not any('private' in n or '/runtime/' in n or '/testing/runs/' in n or '/verification/' in n or '/.env' in n for n in names)
    assert Path(result['archive']).with_suffix('.zip.sha256').is_file()


def test_source_check_reports_secret_location_without_printing_secret(tmp_path):
    (tmp_path / 'scripts').mkdir()
    secret = 'ghp_' + 'A' * 36
    (tmp_path / 'scripts/example.py').write_text('value = ' + repr(secret), encoding='utf-8')
    with pytest.raises(ValueError) as err:
        release.inspect(tmp_path)
    assert 'scripts/example.py' in str(err.value)
    assert secret not in str(err.value)


def test_actual_public_source_has_no_machine_home_paths():
    assert release.inspect(PROJECT)
