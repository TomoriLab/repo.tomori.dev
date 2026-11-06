#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Build APT indexes from verified Debian source and binary manifests."""

import argparse
import datetime
import email.utils
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from site_renderer import render_site

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def manifest_files(manifest):
    entries = re.findall(r'^ ([a-f0-9]{64})\s+(\d+)\s+(\S+)$', manifest.read_text(), re.MULTILINE)
    if not entries:
        raise ValueError(f'Missing SHA-256 entries: {manifest}')
    for digest, size, name in entries:
        if Path(name).name != name:
            raise ValueError(f'Invalid manifest filename: {name}')
        file = manifest.parent / name
        if file.stat().st_size != int(size) or sha256(file) != digest:
            raise ValueError(f'Manifest verification failed: {file}')
        yield file


def copy_immutable(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and sha256(source) != sha256(destination):
        raise ValueError(f'Increment the package version before replacing {destination.name}')
    shutil.copy2(source, destination)


def write_index(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.with_suffix(path.suffix + '.gz').write_bytes(gzip.compress(data, mtime=0))
    path.with_suffix(path.suffix + '.xz').write_bytes(lzma.compress(data))
    for file in [path, path.with_suffix(path.suffix + '.gz'), path.with_suffix(path.suffix + '.xz')]:
        for algorithm in ['sha256', 'sha512']:
            digest = hashlib.new(algorithm, file.read_bytes()).hexdigest()
            destination = file.parent / 'by-hash' / algorithm.upper() / digest
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)


def control_entries(data):
    for paragraph in data.decode().strip().split('\n\n'):
        if paragraph:
            fields = dict(re.findall(r'^([^\s:]+): (.*)$', paragraph, re.MULTILINE))
            yield fields, (paragraph + '\n\n').encode()


def create_repository(artifacts, output, configuration):
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='repository-', dir=output.parent))
    try:
        if output.exists():
            shutil.copytree(output / 'pool', staging / 'pool')
            for directory in (output / 'dists').rglob('by-hash'):
                shutil.copytree(directory, staging / directory.relative_to(output))
        membership = {}
        for suite, settings in configuration['suites'].items():
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', suite):
                raise ValueError(f'Invalid suite name: {suite}')
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', settings.get('target_release', suite)):
                raise ValueError(f'Invalid target release for {suite}')
            selected = membership[suite] = set()
            for project in settings['projects']:
                source_directory = artifacts / suite / project
                manifests = sorted(source_directory.glob('*.dsc')) + sorted(source_directory.glob('*.changes'))
                if not any(file.suffix == '.dsc' for file in manifests) or not any(file.suffix == '.changes' for file in manifests):
                    raise ValueError(f'Source and binary manifests are required for {suite}/{project}')
                prefix = project[:4] if project.startswith('lib') else project[0]
                destination = staging / 'pool' / configuration['component'] / prefix / project
                for manifest in manifests:
                    for file in [manifest, *manifest_files(manifest)]:
                        target = destination / file.name
                        copy_immutable(file, target)
                        selected.add(str(target.relative_to(staging)))

        package_entries = list(control_entries(subprocess.check_output(['apt-ftparchive', 'packages', 'pool'], cwd=staging)))
        source_entries = list(control_entries(subprocess.check_output(['apt-ftparchive', 'sources', 'pool'], cwd=staging)))
        inventory = []
        summary = {}
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        valid_until = email.utils.format_datetime(now + datetime.timedelta(days=configuration['valid_days']), usegmt=True)
        for suite, selected in membership.items():
            packages = [(fields, data) for fields, data in package_entries if fields['Filename'] in selected]
            sources = [(fields, data) for fields, data in source_entries
                       if str(Path(fields['Directory']) / (fields['Package'] + '_' + fields['Version'].split(':')[-1] + '.dsc')) in selected]
            if not packages or not sources:
                raise ValueError(f'Empty package or source index for {suite}')
            for fields, _ in packages:
                if fields['Architecture'] not in [*configuration['architectures'], 'all']:
                    raise ValueError(f"Unsupported architecture: {fields['Filename']}")
                inventory.append({name: fields[name] for name in ['Package', 'Version', 'Architecture', 'Depends', 'Description', 'Filename', 'SHA256'] if name in fields}
                                 | {'Size': int(fields['Size']), 'Suite': suite})
            distribution = staging / 'dists' / suite
            directories = []
            for architecture in configuration['architectures']:
                directory = distribution / configuration['component'] / ('binary-' + architecture)
                write_index(directory / 'Packages', b''.join(data for fields, data in packages if fields['Architecture'] in [architecture, 'all']))
                directories.append((directory, architecture))
            directory = distribution / configuration['component'] / 'source'
            write_index(directory / 'Sources', b''.join(data for _, data in sources))
            directories.append((directory, 'source'))
            for directory, architecture in directories:
                (directory / 'Release').write_text(f"Archive: {suite}\nComponent: {configuration['component']}\nOrigin: {configuration['origin']}\nArchitecture: {architecture}\n")
            options = {
                'Origin': configuration['origin'], 'Label': configuration['label'],
                'Suite': configuration['suites'][suite].get('target_release', suite), 'Codename': suite,
                'Architectures': ' '.join(configuration['architectures']),
                'Components': configuration['component'], 'Acquire-By-Hash': 'yes',
                'NotAutomatic': 'yes', 'ButAutomaticUpgrades': 'yes',
                'Date': email.utils.format_datetime(now, usegmt=True),
                'Description': configuration['description'],
            }
            command = ['apt-ftparchive']
            for name, value in options.items():
                command += ['-o', f'APT::FTPArchive::Release::{name}={value}']
            command += ['release', str(distribution)]
            release = subprocess.check_output(command, cwd=staging).decode()
            # apt-ftparchive does not emit Valid-Until from its Release options.
            (distribution / 'Release').write_text('Valid-Until: ' + valid_until + '\n' + release)
            summary[suite] = {'packages': len(packages), 'sources': len(sources)}
        (staging / 'keys').mkdir()
        for suffix in ['gpg', 'asc']:
            name = 'tomori-archive-keyring.' + suffix
            shutil.copy2(ROOT / 'keys' / name, staging / 'keys' / name)
        inventory.sort(key=lambda item: (item['Suite'], item['Package'], item['Version']))
        (staging / 'package-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
        render_site(staging, configuration, inventory)
        (staging / 'robots.txt').write_text('User-agent: *\nDisallow: /pool/\nDisallow: /dists/\n')
        previous = output.with_name(output.name + '.previous')
        if previous.exists():
            shutil.rmtree(previous)
        if output.exists():
            output.rename(previous)
        staging.chmod(0o755)
        staging.rename(output)
        print(json.dumps({'suites': summary, 'output': str(output), 'valid_until': valid_until}))
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, default=ROOT / 'artifacts')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/public')
    arguments = parser.parse_args()
    configuration = json.loads((ROOT / 'config/repository.json').read_text())
    create_repository(arguments.artifacts.resolve(), arguments.output.resolve(), configuration)
