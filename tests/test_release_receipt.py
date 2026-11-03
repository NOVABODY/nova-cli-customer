"""A partial file list or stale wheel cannot become current release evidence."""
import importlib.util
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'release_receipt', Path(__file__).parents[1] / 'scripts' / 'release_receipt.py'
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.fixture
def built_source(tmp_path):
    package = tmp_path / 'src' / 'nova_cli_public'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('VERSION = "0.1.0"\n')
    (package / 'new_command.py').write_text('VALUE = "new behavior"\n')
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="nova-fora-cli"\nversion="0.1.0"\nreadme="README.md"\n')
    (tmp_path / 'README.md').write_text('# Synthetic customer help\n')
    (tmp_path / '.gitignore').write_text('dist/\n')
    for args in (['init', '-q'], ['add', '.'], ['-c', 'user.name=John Rust', '-c',
            'user.email=jrust-dfs@users.noreply.github.com', 'commit', '-qm', 'synthetic source']):
        subprocess.run(['git', '-C', str(tmp_path), *args], check=True)
    wheel = tmp_path / 'dist' / 'candidate.whl'
    wheel.parent.mkdir()
    members = {'nova_cli_public/' + path.name: path.read_bytes() for path in package.iterdir()}
    members['nova_fora_cli-0.1.0.dist-info/METADATA'] = b'Name: nova-fora-cli\nVersion: 0.1.0\n\n# Synthetic customer help\n'
    return tmp_path, wheel, members


def write_wheel(wheel, members):
    with zipfile.ZipFile(wheel, 'w') as archive:
        for name, value in members.items():
            archive.writestr(name, value)


def test_receipt_covers_all_tracked_and_packaged_files(built_source):
    root, wheel, members = built_source
    write_wheel(wheel, members)
    revision = release.git(root, 'rev-parse', 'HEAD')
    result = release.receipt(root, wheel, revision, 'refs/heads/main')
    assert result['revision'] == revision and not result['release_qualified']
    assert set(result['source_files_sha256']) == set(release.git(root, 'ls-files').splitlines())
    assert set(result['wheel']['files_sha256']) == set(members)
    assert result['wheel']['sha256'] == release.digest(wheel.read_bytes())
    assert str(root) not in json.dumps(result), 'Evidence must not contain local machine paths'


@pytest.mark.parametrize('change', ['stale', 'missing', 'extra', 'distribution', 'outside', 'readme'])
def test_receipt_refuses_a_stale_or_incomplete_wheel(built_source, change):
    root, wheel, members = built_source
    if change == 'stale':
        members['nova_cli_public/new_command.py'] = b'old behavior'
    elif change == 'missing':
        del members['nova_cli_public/new_command.py']
    elif change == 'extra':
        members['nova_cli_public/untracked.py'] = b'unreviewed behavior'
    elif change == 'outside':
        members['untracked_root_module.py'] = b'unreviewed code'
    elif change == 'readme':
        members['nova_fora_cli-0.1.0.dist-info/METADATA'] = b'Name: nova-fora-cli\nVersion: 0.1.0\n\nOld help\n'
    else:
        members['nova_fora_cli-0.1.0.dist-info/METADATA'] = b'Name: third-party-cli\nVersion: 0.1.0\n'
    write_wheel(wheel, members)
    with pytest.raises(ValueError, match='Wheel'):
        release.receipt(root, wheel, release.git(root, 'rev-parse', 'HEAD'), 'refs/pull/1/merge')


def test_receipt_refuses_dirty_source(built_source):
    root, wheel, members = built_source
    write_wheel(wheel, members)
    (root / 'src/nova_cli_public/new_command.py').write_text('changed after tests')
    with pytest.raises(ValueError, match='unchanged tracked source'):
        release.receipt(root, wheel, release.git(root, 'rev-parse', 'HEAD'), 'local')


def test_receipt_refuses_a_different_revision(built_source):
    root, wheel, members = built_source
    write_wheel(wheel, members)
    with pytest.raises(ValueError, match='revision'):
        release.receipt(root, wheel, 'a' * 40, 'local')
