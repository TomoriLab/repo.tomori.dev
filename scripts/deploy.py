#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Verify and atomically publish an archive using local deployment settings."""

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile

from deployment_config import DEFAULT_CONFIGURATION, load_configuration, manager_configuration, required_path, required_text

ROOT = Path(__file__).resolve().parents[1]
SSH_OPTIONS = ['-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'StrictHostKeyChecking=yes']
REMOTE_INSTALL = r'''
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

upload = Path(sys.argv[1])
release_name = sys.argv[2]
archive_digest = sys.argv[3]
base = Path(sys.argv[4])
if not base.is_absolute() or base == Path(base.anchor) or '..' in base.parts:
    raise ValueError('An absolute non-root deployment directory is required')
if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z', release_name):
    raise ValueError('Invalid release identifier')
archive = upload / 'repository.tar'
with archive.open('rb') as stream:
    if hashlib.file_digest(stream, 'sha256').hexdigest() != archive_digest:
        raise ValueError('The uploaded archive failed SHA-256 verification')
release = base / 'releases' / release_name
release.mkdir(parents=True, mode=0o755)
current = base / 'current'
previous = current.resolve().name if current.exists() else None
with tarfile.open(archive) as package:
    package.extractall(release, filter='data')

def retain_immutable(source, destination):
    for file in source.rglob('*'):
        if not file.is_file():
            continue
        target = destination / file.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            for candidate in [file, target]:
                with candidate.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if candidate == file:
                    expected = digest
                elif digest != expected:
                    raise ValueError('An immutable repository path changed')
        else:
            shutil.copy2(file, target)

if current.exists():
    retain_immutable(current / 'pool', release / 'pool')
    for directory in (current / 'dists').rglob('by-hash'):
        retain_immutable(directory, release / directory.relative_to(current))
for path in release.rglob('*'):
    if path.is_symlink():
        raise ValueError('Repository artifacts must not contain symbolic links')
    path.chmod(0o755 if path.is_dir() else 0o644)
subprocess.run(['python3', str(upload / 'scripts/verify-repository.py'), '--public', str(release)], check=True)
link = base / ('current-' + release_name)
link.symlink_to(Path('releases') / release_name)
os.replace(link, current)
print(json.dumps({'release': release_name, 'previous_release': previous, 'activated': True}))
'''


def prepare_support(directory, configuration, configure_caddy):
    support = directory / 'support'
    for name in ['scripts', 'config', 'keys']:
        (support / name).mkdir(parents=True, mode=0o700)
    shutil.copy2(ROOT / 'scripts/verify-repository.py', support / 'scripts/verify-repository.py')
    shutil.copy2(ROOT / 'config/repository.json', support / 'config/repository.json')
    shutil.copy2(ROOT / 'build/public/keys/tomori-archive-keyring.gpg', support / 'keys/tomori-archive-keyring.gpg')
    if configure_caddy:
        manager = manager_configuration(configuration)
        for name in ['configure-caddy.py', 'deployment_config.py']:
            shutil.copy2(ROOT / 'scripts' / name, support / 'scripts' / name)
        shutil.copy2(ROOT / 'config/caddy-proxy-host.json', support / 'config/caddy-proxy-host.json')
        path = support / 'config/deployment.json'
        path.write_text(json.dumps({'manager': manager}) + '\n')
        path.chmod(0o600)
    return support


def deploy(configuration_path=DEFAULT_CONFIGURATION, host=None, configure_caddy=False):
    configuration = load_configuration(configuration_path)
    host = host or required_text(configuration, 'ssh_host')
    if not re.fullmatch(r'[A-Za-z0-9_.@:\[\]-]+', host) or host.startswith('-'):
        raise ValueError('Configure a valid SSH destination.')
    remote_root = required_path(configuration, 'remote_root')
    temporary_directory = required_path(configuration, 'temporary_directory')
    if configure_caddy:
        manager_configuration(configuration)
    subprocess.run(['python3', str(ROOT / 'scripts/verify-repository.py')], check=True)
    public = ROOT / 'build/public'
    repository = json.loads((ROOT / 'config/repository.json').read_text())
    release_name = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    with tempfile.TemporaryDirectory(prefix='repository-deploy-') as directory:
        directory = Path(directory)
        archive = directory / 'repository.tar'
        with tarfile.open(archive, 'w') as package:
            for path in sorted(public.iterdir()):
                package.add(path, arcname=path.name)
        with archive.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        support = prepare_support(directory, configuration, configure_caddy)
        template = temporary_directory / 'archive-upload.XXXXXXXX'
        upload = subprocess.check_output(['ssh', *SSH_OPTIONS, host, shlex.join(['mktemp', '-d', str(template)])], text=True).strip()
        upload_path = Path(upload)
        if upload_path.parent != temporary_directory or not re.fullmatch(r'archive-upload\.[A-Za-z0-9]{8}', upload_path.name):
            raise ValueError('The server returned an unexpected upload directory')
        try:
            subprocess.run(['scp', *SSH_OPTIONS, '-r', str(archive), str(support / 'scripts'), str(support / 'config'),
                            str(support / 'keys'), host + ':' + upload + '/'], check=True)
            command = shlex.join(['sudo', '-n', 'python3', '-', upload, release_name, digest, str(remote_root)])
            subprocess.run(['ssh', *SSH_OPTIONS, host, command], input=REMOTE_INSTALL, text=True, check=True)
            if configure_caddy:
                command = shlex.join(['sudo', '-n', 'python3', upload + '/scripts/configure-caddy.py',
                    upload + '/config/caddy-proxy-host.json', '--deployment-config', upload + '/config/deployment.json'])
                subprocess.run(['ssh', *SSH_OPTIONS, host, command], check=True)
        finally:
            subprocess.run(['ssh', *SSH_OPTIONS, host, shlex.join(['rm', '-rf', '--', upload])], check=True)
    print(json.dumps({'release': release_name, 'url': repository['base_url']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment-config', type=Path, default=DEFAULT_CONFIGURATION)
    parser.add_argument('--host', help='Override the SSH destination from the local deployment configuration.')
    parser.add_argument('--configure-caddy', action='store_true', help='Register the hostname on the first deployment only.')
    arguments = parser.parse_args()
    try:
        deploy(arguments.deployment_config, arguments.host, arguments.configure_caddy)
    except ValueError as error:
        parser.error(str(error))
