#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Manage an archive host through a locally configured Caddy manager."""

import argparse
import contextlib
import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess

from deployment_config import DEFAULT_CONFIGURATION, load_configuration, manager_configuration, repository_domain, required_path


def request_api(manager, token, method, path, body):
    javascript = '''let input = ''; for await (const chunk of process.stdin) input += chunk;
const value = JSON.parse(input);
const baseUrl = new URL(value.base_url);
const port = value.port_environment && process.env[value.port_environment];
if (port) baseUrl.port = port;
const response = await fetch(new URL(value.path, baseUrl), {
  method: value.method,
  headers: {Authorization: `Bearer ${value.token}`, 'Content-Type': 'application/json'},
  body: JSON.stringify(value.body),
});
process.stdout.write(JSON.stringify({status: response.status, body: await response.json()}));'''
    values = {'token': token, 'method': method, 'path': path, 'body': body,
              'base_url': manager['api_base_url'], 'port_environment': manager.get('api_port_environment')}
    result = subprocess.run(['docker', 'exec', '-i', manager['web_container'], 'node', '--input-type=module', '-e', javascript],
                            input=json.dumps(values), text=True, capture_output=True, check=True)
    response = json.loads(result.stdout)
    if not 200 <= response['status'] < 300:
        raise RuntimeError(f"Manager API returned HTTP {response['status']}")
    return response['body']


def validate_payload(payload, domain):
    if payload.get('domains') != [domain] or payload.get('enabled') is not False:
        raise ValueError('Provide a disabled host configuration for the configured repository domain.')
    if 'certificateId' in payload and (type(payload['certificateId']) is not int or payload['certificateId'] <= 0):
        raise ValueError('Configure a provisioned certificateId in the local host configuration.')
    if 'upstreams' in payload and not payload['upstreams']:
        raise ValueError('Configure the upstream list required by the target manager.')
    if 'customPreHandlersJson' in payload:
        handlers = json.loads(payload['customPreHandlersJson'])
        pending = [handlers]
        while pending:
            item = pending.pop()
            if isinstance(item, list):
                pending.extend(item)
            elif isinstance(item, dict):
                if item.get('handler') == 'file_server':
                    required_path(item, 'root')
                pending.extend(item.values())


def configure(payload_path=None, deployment_path=DEFAULT_CONFIGURATION, origin_certificate=None,
              private_key=None, update_host=False, import_certificate=False):
    if os.geteuid() != 0:
        raise PermissionError('This command requires root access to the configured manager database.')
    manager = manager_configuration(load_configuration(deployment_path))
    domain = repository_domain()
    certificate_mode = import_certificate or origin_certificate is not None
    if certificate_mode:
        origin_certificate = Path(origin_certificate) if origin_certificate else required_path(manager, 'origin_certificate')
        private_key = Path(private_key) if private_key else required_path(manager, 'private_key')
        subprocess.run(['openssl', 'x509', '-in', str(origin_certificate), '-noout', '-checkhost', domain], check=True)
        certificate_public = subprocess.check_output(['openssl', 'x509', '-in', str(origin_certificate), '-pubkey', '-noout'])
        private_public = subprocess.check_output(['openssl', 'pkey', '-in', str(private_key), '-pubout'])
        if certificate_public != private_public:
            raise ValueError('The origin certificate and private key do not match.')
    else:
        if payload_path is None:
            raise ValueError('Provide a local host configuration or select certificate import.')
        payload = json.loads(Path(payload_path).read_text())
        validate_payload(payload, domain)
    database_path = required_path(manager, 'database_path')
    if not database_path.is_file():
        raise ValueError('The configured manager database is unavailable.')
    os.umask(0o077)
    with contextlib.closing(sqlite3.connect(database_path)) as database, database:
        database.row_factory = sqlite3.Row
        matches = database.execute('SELECT id,domains FROM proxy_hosts WHERE domains LIKE ?', ('%' + domain + '%',)).fetchall()
        if matches and not certificate_mode and not update_host:
            raise ValueError('The repository host already exists; select a host update.')
        if (certificate_mode or update_host) and (len(matches) != 1 or json.loads(matches[0]['domains']) != [domain]):
            raise ValueError('Exactly one matching repository host is required.')
        administrator = database.execute("SELECT id FROM users WHERE role='admin' AND status='active' ORDER BY id LIMIT 1").fetchone()
        if administrator is None:
            raise ValueError('No active administrator is available.')
        if database.execute('SELECT COUNT(*) FROM api_tokens WHERE createdBy=?', (administrator['id'],)).fetchone()[0] >= 10:
            raise ValueError('The administrator already has the maximum number of API tokens.')
        timestamp = datetime.datetime.now(datetime.timezone.utc)
        backup_directory = required_path(manager, 'backup_directory')
        backup_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        backup_path = backup_directory / ('manager-' + timestamp.strftime('%Y%m%dT%H%M%SZ') + '.sqlite')
        with contextlib.closing(sqlite3.connect(backup_path)) as backup:
            database.backup(backup)
        token = secrets.token_hex(32)
        expiry = timestamp + datetime.timedelta(minutes=5)
        cursor = database.execute('INSERT INTO api_tokens (name,tokenHash,createdBy,createdAt,expiresAt) VALUES (?,?,?,?,?)',
            (domain + ' deployment', hashlib.sha256(token.encode()).hexdigest(), administrator['id'], timestamp.isoformat(), expiry.isoformat()))
        token_id = cursor.lastrowid
        database.commit()
        try:
            if update_host:
                payload['enabled'] = True
                host = request_api(manager, token, 'PUT', '/api/v1/proxy-hosts/' + str(matches[0]['id']), payload)
                print(json.dumps({'operation': 'update-host', 'domain': domain, 'enabled': host['enabled']}))
            elif certificate_mode:
                certificate = request_api(manager, token, 'POST', '/api/v1/certificates', {
                    'name': domain + ' origin certificate', 'type': 'imported', 'domainNames': [domain],
                    'autoRenew': False, 'certificatePem': origin_certificate.read_text(), 'privateKeyPem': private_key.read_text()})
                request_api(manager, token, 'PUT', '/api/v1/proxy-hosts/' + str(matches[0]['id']), {'certificateId': certificate['id']})
                print(json.dumps({'operation': 'import-certificate', 'domain': domain}))
            else:
                host = request_api(manager, token, 'POST', '/api/v1/proxy-hosts', payload)
                host_id = host['id']
                overrides = manager.get('metadata_overrides', {})
                if overrides:
                    row = database.execute('SELECT meta FROM proxy_hosts WHERE id=?', (host_id,)).fetchone()
                    metadata = json.loads(row['meta'] or '{}')
                    metadata.update(overrides)
                    database.execute('UPDATE proxy_hosts SET meta=? WHERE id=?', (json.dumps(metadata), host_id))
                    database.commit()
                host = request_api(manager, token, 'PUT', '/api/v1/proxy-hosts/' + str(host_id), {'enabled': True})
                print(json.dumps({'operation': 'create-host', 'domain': domain, 'enabled': host['enabled']}))
        finally:
            database.execute('DELETE FROM api_tokens WHERE id=?', (token_id,))
            database.commit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path, nargs='?')
    parser.add_argument('--deployment-config', type=Path, default=DEFAULT_CONFIGURATION)
    parser.add_argument('--origin-certificate', type=Path)
    parser.add_argument('--private-key', type=Path)
    parser.add_argument('--import-certificate', action='store_true')
    parser.add_argument('--update-host', action='store_true')
    arguments = parser.parse_args()
    certificate_mode = arguments.import_certificate or arguments.origin_certificate is not None
    if arguments.update_host and (arguments.payload is None or certificate_mode):
        parser.error('--update-host requires a host payload and cannot import a certificate.')
    if certificate_mode and arguments.payload is not None:
        parser.error('Certificate import does not accept a host payload.')
    if arguments.private_key is not None and not certificate_mode:
        parser.error('--private-key requires certificate import.')
    try:
        configure(arguments.payload, arguments.deployment_config, arguments.origin_certificate,
                  arguments.private_key, arguments.update_host, arguments.import_certificate)
    except ValueError as error:
        parser.error(str(error))
