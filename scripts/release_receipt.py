"""Bind a built customer wheel to every tracked source file; never publish it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def receipt(root: Path, wheel: Path, revision: str, ref: str) -> dict:
    if git(root, 'rev-parse', 'HEAD') != revision:
        raise ValueError('Receipt revision does not match the checked-out source')
    if git(root, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Receipt requires unchanged tracked source')
    source = {}
    for name in git(root, 'ls-files', '-z').split('\0'):
        if name:
            path = root / name
            if path.is_symlink() or not path.is_file():
                raise ValueError('Receipt source must contain ordinary tracked files')
            source[name] = digest(path.read_bytes())
    expected = {name.removeprefix('src/'): value for name, value in source.items()
                if name.startswith('src/nova_cli_public/')}
    if not expected:
        raise ValueError('Customer package source is missing')
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Wheel contains duplicate members')
        members = {name: archive.read(name) for name in names if not name.endswith('/')}
    packaged = {name: digest(value) for name, value in members.items()
                if name.startswith('nova_cli_public/')}
    if packaged != expected:
        raise ValueError('Wheel package files do not match the complete tracked source')
    metadata_names = [name for name in members if name.endswith('.dist-info/METADATA')]
    if len(metadata_names) != 1:
        raise ValueError('Wheel must contain one distribution metadata record')
    metadata_prefix = metadata_names[0].rsplit('/', 1)[0] + '/'
    if any(name not in expected and not name.startswith(metadata_prefix) for name in members):
        raise ValueError('Wheel contains files outside the customer package and its metadata')
    metadata = BytesParser().parsebytes(members[metadata_names[0]])
    project = tomllib.loads((root / 'pyproject.toml').read_text())['project']
    if metadata['Name'] != project['name'] or metadata['Version'] != project['version']:
        raise ValueError('Wheel distribution does not match the checked-out project')
    readme = project.get('readme')
    if isinstance(readme, str):
        packaged_readme = metadata.get_payload(decode=True).decode('utf-8')
        if packaged_readme.rstrip('\n') != (root / readme).read_text().rstrip('\n'):
            raise ValueError('Wheel description does not match the current customer README')
    return {'schema_version': 1, 'revision': revision, 'source_ref': ref,
            'release_qualified': False,
            'distribution': metadata['Name'], 'version': metadata['Version'],
            'source_files_sha256': source,
            'wheel': {'filename': wheel.name, 'sha256': digest(wheel.read_bytes()),
                      'files_sha256': {name: digest(value) for name, value in members.items()}}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', required=True, type=Path)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--ref', default=os.environ.get('GITHUB_REF', 'local'))
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = receipt(root, args.wheel, args.revision, args.ref)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
