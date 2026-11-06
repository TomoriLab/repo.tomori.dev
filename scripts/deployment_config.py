#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Read deployment settings without embedding environment-specific defaults."""

import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIGURATION = ROOT / 'config/deployment.json'


def load_configuration(path=DEFAULT_CONFIGURATION):
    path = Path(path)
    if not path.is_file():
        raise ValueError('Initialize the local deployment configuration from its public example.')
    configuration = json.loads(path.read_text())
    if not isinstance(configuration, dict):
        raise ValueError('The deployment configuration must be a JSON object.')
    return configuration


def required_text(configuration, name):
    value = configuration.get(name)
    if not isinstance(value, str) or not value.strip() or any(character in value for character in '\x00\r\n'):
        raise ValueError('Configure the deployment field: ' + name)
    return value


def required_path(configuration, name):
    value = Path(required_text(configuration, name))
    if not value.is_absolute() or value == Path(value.anchor) or '..' in value.parts:
        raise ValueError('Configure a non-root absolute deployment path: ' + name)
    return value


def manager_configuration(configuration):
    manager = configuration.get('manager')
    if not isinstance(manager, dict):
        raise ValueError('Configure the deployment manager object.')
    for name in ['database_path', 'backup_directory']:
        required_path(manager, name)
    container = required_text(manager, 'web_container')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', container):
        raise ValueError('Configure a valid manager container name.')
    url = urlsplit(required_text(manager, 'api_base_url'))
    if url.scheme not in ['http', 'https'] or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Configure an HTTP manager API URL without embedded credentials.')
    url.port
    environment = manager.get('api_port_environment')
    if environment is not None and (not isinstance(environment, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', environment)):
        raise ValueError('Configure a valid manager API port environment variable name.')
    if not isinstance(manager.get('metadata_overrides', {}), dict):
        raise ValueError('Manager metadata overrides must be a JSON object.')
    return manager


def repository_domain():
    configuration = json.loads((ROOT / 'config/repository.json').read_text())
    domain = urlsplit(configuration['base_url']).hostname
    if not domain:
        raise ValueError('Configure a repository URL with a hostname.')
    return domain
