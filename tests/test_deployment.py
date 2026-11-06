# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise configuration-driven deployment with isolated dummy resources."""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import deployment_config
import deploy

specification = importlib.util.spec_from_file_location('configure_caddy', SCRIPTS / 'configure-caddy.py')
configure_caddy = importlib.util.module_from_spec(specification)
specification.loader.exec_module(configure_caddy)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ['config', 'scripts', 'keys', 'build/public/keys', 'build/public/pool', 'build/public/dists']:
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / 'config/repository.json').write_text(json.dumps({'base_url': 'https://archive.invalid'}))
        (self.root / 'config/credentials.json').write_text('{"fixture_secret": "not-for-upload"}')
        (self.root / 'keys/private-backup.key').write_text('fixture-only private material')
        (self.root / 'build/public/keys/tomori-archive-keyring.gpg').write_bytes(b'fixture-public-key')
        (self.root / 'build/public/pool/package').write_bytes(b'fixture-package')
        for name in ['verify-repository.py', 'configure-caddy.py', 'deployment_config.py']:
            (self.root / 'scripts' / name).write_text('# Fixture support file.\n')
        self.configuration = {
            'ssh_host': 'publisher@deployment.invalid',
            'remote_root': str(self.root / 'remote'),
            'temporary_directory': str(self.root / 'uploads'),
            'manager': {
                'database_path': str(self.root / 'manager.sqlite'),
                'backup_directory': str(self.root / 'backups'),
                'web_container': 'fixture-manager',
                'api_base_url': 'http://manager.invalid:8080',
                'api_port_environment': None,
                'metadata_overrides': {'fixture_flag': True},
                'origin_certificate': str(self.root / 'origin.pem'),
                'private_key': str(self.root / 'origin.key'),
            },
        }
        self.configuration_path = self.root / 'config/deployment.json'
        self.configuration_path.write_text(json.dumps(self.configuration))
        self.addCleanup(patch.stopall)
        patch.object(deploy, 'ROOT', self.root).start()
        patch.object(deployment_config, 'ROOT', self.root).start()

    def test_missing_configuration_stops_before_commands(self):
        with patch.object(subprocess, 'run') as run, patch.object(subprocess, 'check_output') as output:
            with self.assertRaises(ValueError):
                deploy.deploy(self.root / 'missing.json')
        run.assert_not_called()
        output.assert_not_called()

    def test_unconfigured_example_and_unsafe_paths_are_rejected(self):
        for value in [None, '', '/', 'relative', '/storage/../other']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                deployment_config.required_path({'remote_root': value}, 'remote_root')
        manager = dict(self.configuration['manager'], api_base_url='http://user:password@manager.invalid')
        with self.assertRaises(ValueError):
            deployment_config.manager_configuration({'manager': manager})

    def test_upload_uses_configured_paths_and_explicit_support_files(self):
        upload = Path(self.configuration['temporary_directory']) / 'archive-upload.ABCd1234'
        calls = []

        def run(command, **options):
            calls.append((command, options))
            if command[0] == 'scp':
                support = Path(command[-4]).parent
                files = {str(file.relative_to(support)) for file in support.rglob('*') if file.is_file()}
                self.assertEqual(files, {'scripts/verify-repository.py', 'config/repository.json', 'keys/tomori-archive-keyring.gpg'})
                self.assertEqual((support / 'keys/tomori-archive-keyring.gpg').read_bytes(), b'fixture-public-key')
            return subprocess.CompletedProcess(command, 0)

        with patch.object(subprocess, 'run', side_effect=run), patch.object(subprocess, 'check_output', return_value=str(upload) + '\n') as output:
            with contextlib.redirect_stdout(io.StringIO()) as console:
                deploy.deploy(self.configuration_path)
        self.assertEqual(output.call_args.args[0][-2], self.configuration['ssh_host'])
        self.assertIn(self.configuration['temporary_directory'], output.call_args.args[0][-1])
        install = [options for command, options in calls if options.get('input') == deploy.REMOTE_INSTALL]
        self.assertEqual(len(install), 1)
        self.assertNotIn(self.configuration['remote_root'], install[0]['input'])
        self.assertTrue(any(self.configuration['remote_root'] in command[-1] for command, _ in calls if command[0] == 'ssh'))
        self.assertNotIn(self.configuration['ssh_host'], console.getvalue())

    def test_invalid_upload_path_stops_before_transfer(self):
        with patch.object(subprocess, 'run') as run, patch.object(subprocess, 'check_output', return_value=str(self.root / 'unowned') + '\n'):
            with self.assertRaises(ValueError):
                deploy.deploy(self.configuration_path)
        self.assertFalse(any(call.args[0][0] == 'scp' for call in run.call_args_list))

    def test_manager_support_excludes_ssh_and_unrelated_configuration(self):
        payload = self.root / 'config/caddy-proxy-host.json'
        payload.write_text('{"domains": ["archive.invalid"], "enabled": false}')
        directory = self.root / 'support-test'
        directory.mkdir()
        support = deploy.prepare_support(directory, self.configuration, True)
        uploaded = json.loads((support / 'config/deployment.json').read_text())
        self.assertEqual(set(uploaded), {'manager'})
        self.assertFalse((support / 'config/credentials.json').exists())
        self.assertFalse((support / 'keys/private-backup.key').exists())

    def create_database(self, host=False):
        with contextlib.closing(sqlite3.connect(self.configuration['manager']['database_path'])) as database, database:
            database.executescript('''
                CREATE TABLE users (id INTEGER PRIMARY KEY, role TEXT, status TEXT);
                CREATE TABLE api_tokens (id INTEGER PRIMARY KEY, name TEXT, tokenHash TEXT, createdBy INTEGER, createdAt TEXT, expiresAt TEXT);
                CREATE TABLE proxy_hosts (id INTEGER PRIMARY KEY, domains TEXT, meta TEXT);
                INSERT INTO users VALUES (1, 'admin', 'active');
            ''')
            if host:
                database.execute('INSERT INTO proxy_hosts VALUES (7, ?, ?)', ('["archive.invalid"]', '{}'))

    def token_count(self):
        with contextlib.closing(sqlite3.connect(self.configuration['manager']['database_path'])) as database:
            return database.execute('SELECT COUNT(*) FROM api_tokens').fetchone()[0]

    def test_manager_updates_configured_host_and_cleans_token(self):
        self.create_database(host=True)
        payload = self.root / 'config/caddy-proxy-host.json'
        payload.write_text('{"domains": ["archive.invalid"], "enabled": false, "certificateId": 7}')
        with patch.object(configure_caddy.os, 'geteuid', return_value=0), patch.object(configure_caddy, 'request_api', return_value={'enabled': True}) as request:
            with contextlib.redirect_stdout(io.StringIO()):
                configure_caddy.configure(payload, self.configuration_path, update_host=True)
        self.assertEqual(request.call_args.args[0]['web_container'], 'fixture-manager')
        self.assertTrue(request.call_args.args[-1]['enabled'])
        self.assertEqual(self.token_count(), 0)
        self.assertEqual(len(list((self.root / 'backups').glob('*.sqlite'))), 1)

    def test_manager_api_failure_still_cleans_token(self):
        self.create_database(host=True)
        payload = self.root / 'config/caddy-proxy-host.json'
        payload.write_text('{"domains": ["archive.invalid"], "enabled": false}')
        with patch.object(configure_caddy.os, 'geteuid', return_value=0), patch.object(configure_caddy, 'request_api', side_effect=RuntimeError('Fixture failure.')):
            with self.assertRaises(RuntimeError):
                configure_caddy.configure(payload, self.configuration_path, update_host=True)
        self.assertEqual(self.token_count(), 0)

    def test_host_creation_uses_configured_metadata(self):
        self.create_database()
        payload = self.root / 'config/caddy-proxy-host.json'
        payload.write_text('{"domains": ["archive.invalid"], "enabled": false}')

        def request(manager, token, method, path, body):
            if method == 'POST':
                with contextlib.closing(sqlite3.connect(manager['database_path'])) as database, database:
                    database.execute('INSERT INTO proxy_hosts VALUES (8, ?, ?)', ('["archive.invalid"]', '{}'))
                return {'id': 8}
            return {'enabled': True}

        with patch.object(configure_caddy.os, 'geteuid', return_value=0), patch.object(configure_caddy, 'request_api', side_effect=request):
            with contextlib.redirect_stdout(io.StringIO()):
                configure_caddy.configure(payload, self.configuration_path)
        with contextlib.closing(sqlite3.connect(self.configuration['manager']['database_path'])) as database:
            metadata = json.loads(database.execute('SELECT meta FROM proxy_hosts WHERE id=8').fetchone()[0])
        self.assertEqual(metadata, {'fixture_flag': True})
        self.assertEqual(self.token_count(), 0)

    def test_certificate_import_uses_configured_paths(self):
        self.create_database(host=True)
        (self.root / 'origin.pem').write_text('fixture public certificate')
        (self.root / 'origin.key').write_text('fixture private certificate key')
        with patch.object(configure_caddy.os, 'geteuid', return_value=0), patch.object(subprocess, 'run'), patch.object(subprocess, 'check_output', return_value=b'fixture-public-component'), patch.object(configure_caddy, 'request_api', side_effect=[{'id': 9}, {}]) as request:
            with contextlib.redirect_stdout(io.StringIO()):
                configure_caddy.configure(deployment_path=self.configuration_path, import_certificate=True)
        self.assertEqual(request.call_args_list[0].args[-1]['certificatePem'], 'fixture public certificate')
        self.assertEqual(request.call_args_list[1].args[-1], {'certificateId': 9})
        self.assertEqual(self.token_count(), 0)

    def test_unconfigured_host_template_is_rejected(self):
        for payload in [
            {'domains': ['archive.invalid'], 'enabled': False, 'certificateId': None},
            {'domains': ['archive.invalid'], 'enabled': False, 'upstreams': []},
            {'domains': ['archive.invalid'], 'enabled': False, 'customPreHandlersJson': '[{"handler":"file_server","root":null}]'},
        ]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                configure_caddy.validate_payload(payload, 'archive.invalid')

    def test_manager_request_uses_configured_endpoint_and_redacts_api_error(self):
        manager = self.configuration['manager']
        result = subprocess.CompletedProcess([], 0, stdout='{"status":400,"body":{"fixture_secret":"redact"}}')
        with patch.object(subprocess, 'run', return_value=result) as run:
            with self.assertRaisesRegex(RuntimeError, r'^Manager API returned HTTP 400$'):
                configure_caddy.request_api(manager, 'fixture-token', 'PUT', '/fixture', {})
        self.assertIn(manager['web_container'], run.call_args.args[0])
        self.assertEqual(json.loads(run.call_args.kwargs['input'])['base_url'], manager['api_base_url'])


class RemoteInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = self.root / 'published'
        self.previous = self.base / 'releases/20300101T000000Z'
        (self.previous / 'pool').mkdir(parents=True)
        (self.previous / 'pool/old-package').write_bytes(b'old')
        (self.previous / 'dists/test/by-hash/SHA256').mkdir(parents=True)
        (self.previous / 'dists/test/by-hash/SHA256/old-index').write_bytes(b'old-index')
        (self.base / 'current').symlink_to(Path('releases') / self.previous.name)
        self.upload = self.root / 'upload'
        self.upload.mkdir()

    def install(self, conflict=False, wrong_digest=False):
        payload = self.root / 'payload'
        (payload / 'pool').mkdir(parents=True)
        (payload / 'pool/new-package').write_bytes(b'new')
        (payload / 'dists').mkdir()
        if conflict:
            (payload / 'pool/old-package').write_bytes(b'changed')
        archive = self.upload / 'repository.tar'
        with tarfile.open(archive, 'w') as package:
            for path in payload.iterdir():
                package.add(path, arcname=path.name)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        arguments = ['remote', str(self.upload), '20300102T000000Z', 'invalid' if wrong_digest else digest, str(self.base)]
        with patch.object(sys, 'argv', arguments), patch.object(subprocess, 'run'), contextlib.redirect_stdout(io.StringIO()) as output:
            exec(deploy.REMOTE_INSTALL, {})
        self.assertNotIn(str(self.base), output.getvalue())

    def test_activation_retains_immutable_packages_and_indexes(self):
        self.install()
        current = (self.base / 'current').resolve()
        self.assertEqual(current.name, '20300102T000000Z')
        self.assertEqual((current / 'pool/old-package').read_bytes(), b'old')
        self.assertEqual((current / 'pool/new-package').read_bytes(), b'new')
        self.assertEqual((current / 'dists/test/by-hash/SHA256/old-index').read_bytes(), b'old-index')

    def test_conflict_preserves_active_release(self):
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.install(conflict=True)
        self.assertEqual((self.base / 'current').resolve(), self.previous)

    def test_transport_failure_preserves_active_release(self):
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.install(wrong_digest=True)
        self.assertEqual((self.base / 'current').resolve(), self.previous)


if __name__ == '__main__':
    unittest.main()
