import importlib.util
from pathlib import Path
import tomllib

import pytest


spec = importlib.util.spec_from_file_location('installer', Path(__file__).parents[1] / 'scripts/install_codex.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_install_preserves_config_and_replaces_legacy_manual_policy(tmp_path):
    project = Path(__file__).parents[1]
    home = tmp_path / 'fake-codex'
    skills = tmp_path / 'fake-skills'
    home.mkdir()
    old = '# 保留我的其他要求\n\n' + installer.LEGACY_BEGIN + '\n旧主动复盘要求\n' + installer.LEGACY_END + '\n尾部保留\n'
    (home / 'AGENTS.md').write_text(old, encoding='utf-8')
    config = 'model = "test-model"\n\n[mcp_servers.other]\ncommand = "keep-me"\n'
    (home / 'config.toml').write_text(config, encoding='utf-8')
    backups = tmp_path / 'only-test-backups'
    dry = installer.install(home, skills, tmp_path / 'vault', backups, project)
    assert not dry['applied'] and not backups.exists()
    result = installer.install(home, skills, tmp_path / 'vault', backups, project, apply=True)
    assert result['applied']
    updated = (home / 'AGENTS.md').read_text(encoding='utf-8')
    assert '# 保留我的其他要求' in updated and '尾部保留' in updated
    assert installer.LEGACY_BEGIN not in updated
    parsed = tomllib.loads((home / 'config.toml').read_text(encoding='utf-8'))
    assert parsed['model'] == 'test-model'
    assert parsed['mcp_servers']['other']['command'] == 'keep-me'
    assert 'personal-decision-memory' in parsed['mcp_servers']
    temporary = Path(parsed['mcp_servers']['personal-decision-memory']['env']['TEMP'])
    assert temporary.is_dir() and temporary.is_relative_to(tmp_path)
    repeated = installer.install(home, skills, tmp_path / 'vault', backups, project, apply=True)
    assert repeated['changed_paths'] == []
    assert all(Path(p).is_relative_to(tmp_path) for p in result['changed_paths'])
    assert Path(result['backup']).is_relative_to(backups)


def test_refuse_overwriting_an_unmanaged_skill(tmp_path):
    existing = tmp_path / 'skills/decision-context'
    existing.mkdir(parents=True)
    (existing / 'SKILL.md').write_text('human-owned')
    with pytest.raises(ValueError, match='非本项目'):
        installer.plan(tmp_path / 'codex', tmp_path / 'skills', tmp_path / 'vault')


def test_instruction_upgrade_preserves_equivalent_mcp_config_bytes(tmp_path):
    home, skills = tmp_path / 'codex', tmp_path / 'skills'
    vault, backups = tmp_path / 'vault', tmp_path / 'backups'
    installer.install(home, skills, vault, backups, apply=True)
    config = home / 'config.toml'
    original = config.read_bytes() + b'\n# Keep my existing formatting and comments.\n'
    config.write_bytes(original)
    (home / 'AGENTS.md').write_text(installer.BEGIN + '\nold page-only policy\n' + installer.END, encoding='utf-8')
    result = installer.install(home, skills, vault, backups, apply=True)
    assert str(home / 'AGENTS.md') in result['changed_paths']
    assert str(config) not in result['changed_paths']
    assert config.read_bytes() == original


def test_refuse_malformed_instruction_markers():
    with pytest.raises(ValueError, match='边界'):
        installer.replace_block(installer.BEGIN + '\nunfinished', 'replacement')


def test_refuse_replacing_other_program_under_same_mcp_name():
    with pytest.raises(ValueError, match='其他程序'):
        installer.replace_mcp('[mcp_servers.personal-decision-memory]\ncommand="other"\n',
                              installer.mcp_stanza(Path('python'), Path('vault'), Path('tmp')))
