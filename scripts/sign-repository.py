#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Sign each configured APT suite with the archive signing key."""

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
configuration = json.loads((ROOT / 'config/repository.json').read_text())
for suite in configuration['suites']:
    directory = ROOT / 'build/public/dists' / suite
    options = ['gpg', '--batch', '--yes', '--local-user', configuration['signing_fingerprint'], '--digest-algo', 'SHA512']
    for name, operation in [('InRelease', ['--clearsign']), ('Release.gpg', ['--armor', '--detach-sign'])]:
        destination = directory / name
        temporary = destination.with_name(name + '.new')
        subprocess.run(options + ['--output', str(temporary)] + operation + [str(directory / 'Release')], check=True)
        temporary.replace(destination)
