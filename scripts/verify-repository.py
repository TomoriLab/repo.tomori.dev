#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Verify signatures, index hashes, package payloads, and source artifacts."""

import argparse
import datetime
import email.utils
import hashlib
import gzip
import lzma
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def paragraphs(text):
    for paragraph in text.strip().split('\n\n'):
        result = {}
        key = None
        for line in paragraph.splitlines():
            if line.startswith((' ', '\t')):
                result[key] += '\n' + line
            else:
                key, value = line.split(':', 1)
                result[key] = value.strip()
        yield result


def verify_file(root, name, size, digest, algorithm='sha256'):
    file = root / name
    if not file.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Path escapes the repository: {name}')
    if file.stat().st_size != int(size):
        raise ValueError(f'Incorrect file size: {name}')
    with file.open('rb') as stream:
        if hashlib.file_digest(stream, algorithm).hexdigest() != digest:
            raise ValueError(f'Incorrect {algorithm} digest: {name}')


def verify_suite(public, configuration, suite):
    distribution = public / 'dists' / suite
    keyring = ROOT / 'keys/tomori-archive-keyring.gpg'
    with tempfile.TemporaryDirectory(prefix='repository-verify-') as directory:
        options = ['gpgv', '--homedir', directory, '--status-fd=1', '--keyring', str(keyring)]
        for files in [['InRelease'], ['Release.gpg', 'Release']]:
            result = subprocess.run(options + [str(distribution / name) for name in files], check=True, capture_output=True, text=True)
            if '[GNUPG:] VALIDSIG ' + configuration['signing_fingerprint'] not in result.stdout:
                raise ValueError('The Release signature does not match the configured fingerprint')
        extracted = Path(directory) / 'Release'
        subprocess.run(options + ['--output', str(extracted), str(distribution / 'InRelease')], check=True, capture_output=True)
        if extracted.read_bytes() != (distribution / 'Release').read_bytes():
            raise ValueError('InRelease and Release contain different metadata')
    release = next(paragraphs((distribution / 'Release').read_text()))
    if release['Suite'] != configuration['suites'][suite].get('target_release', suite) or release['Codename'] != suite:
        raise ValueError(f'Incorrect suite identity: {suite}')
    if email.utils.parsedate_to_datetime(release['Valid-Until']) <= datetime.datetime.now(datetime.timezone.utc):
        raise ValueError('Repository metadata has expired')
    for line in release['SHA256'].strip().splitlines():
        digest, size, name = line.split()
        verify_file(distribution, name, size, digest)
    component = distribution / configuration['component']
    binary_directories = [component / ('binary-' + architecture) for architecture in configuration['architectures']]
    packages = [package for directory in binary_directories for package in paragraphs((directory / 'Packages').read_text())]
    for package in packages:
        verify_file(public, package['Filename'], package['Size'], package['SHA256'])
    sources = list(paragraphs((component / 'source/Sources').read_text()))
    for source in sources:
        for line in source['Checksums-Sha256'].strip().splitlines():
            digest, size, name = line.split()
            verify_file(public, str(Path(source['Directory']) / name), size, digest)
    for directory in [*binary_directories, component / 'source']:
        for file in directory.iterdir():
            if file.is_file() and file.name != 'Release':
                data = file.read_bytes()
                if file.suffix in ['.gz', '.xz']:
                    decompress = gzip.decompress if file.suffix == '.gz' else lzma.decompress
                    if decompress(data) != file.with_suffix('').read_bytes():
                        raise ValueError(f'Compressed index differs: {file}')
                digest = hashlib.sha256(data).hexdigest()
                if (directory / 'by-hash/SHA256' / digest).read_bytes() != data:
                    raise ValueError(f'Missing by-hash index: {file}')
    inventory = json.loads((public / 'package-inventory.json').read_text())
    expected = {(item['Package'], item['Version'], item['Architecture'], item['SHA256']) for item in inventory if item['Suite'] == suite}
    actual = {(item['Package'], item['Version'], item['Architecture'], item['SHA256']) for item in packages}
    if actual != expected:
        raise ValueError(f'Inventory does not match the {suite} package index')
    return {'packages_verified': len(actual), 'sources_verified': len(sources), 'valid_until': release['Valid-Until']}


def verify(public):
    configuration = json.loads((ROOT / 'config/repository.json').read_text())
    results = {suite: verify_suite(public, configuration, suite) for suite in configuration['suites']}
    print(json.dumps({'signature': configuration['signing_fingerprint'], 'suites': results}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', type=Path, default=ROOT / 'build/public')
    arguments = parser.parse_args()
    verify(arguments.public.resolve())
