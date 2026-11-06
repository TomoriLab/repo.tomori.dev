# Publishing and operations

Deployment settings are read from ignored local configuration. Public examples
contain no SSH destination, storage layout, manager endpoint, or instance IDs.
Run local commands from the repository root. Manager and rollback operations run
on the host that owns the configured database and storage.

## Configure the checkout

Follow the [configuration guide](configuration.md) to create the local JSON files
and prepare the public archive keyrings. Set the deployment destination and paths
before publishing. Configure manager fields only when manager operations are
needed. Missing required values stop the operation before remote commands run.

## Build and sign

The build tools are Python 3.11 or later, `apt-utils`, `dpkg`, GnuPG, GNU Make,
and an OpenSSH client. All Python scripts use the standard library. Place each
project's `.dsc`, `.changes`, and all files referenced by those manifests in:

```text
artifacts/
  trixie/
    kwi/
    libghostty-vt/
    kirigami-app-components/
    simdutf/
    kf6-ki18n/
    kf6-kirigami/
    kirigami-addons/
  unstable/
    kwi/
    libghostty-vt/
    kirigami-app-components/
```

Suite membership is configured in `config/repository.json`. Only files
referenced by a suite's manifests enter its indexes; a shared package pool does
not make packages available in other suites. The builder signs neither suite
until `make sign` runs.

Package artifacts are stored in this ignored directory when available locally.
The Git repository contains the publishing tools and public configuration
examples. Public key exports, binary packages, and source artifacts are served
through APT and excluded from Git.

```sh
make build
export GPG_TTY="$(tty)"
make sign
make verify
```

`make publish` runs these steps in order. An alternate artifact location can be
provided with `make publish ARTIFACTS=/absolute/path/to/artifacts`.
The GPG private key remains on the signing workstation. Pinentry handles any
required passphrase. Never copy the private archive key to the web server.

The builder verifies manifest sizes and SHA-256 checksums, rejects conflicting
files at immutable package paths, and produces `Packages`, `Sources`, compressed
indexes, and SHA-256/SHA-512 `by-hash` paths. It retains the existing package pool
and historical `by-hash` indexes. Increment the Debian package version when
changing an artifact. `make verify` checks both signatures for every suite,
compares `InRelease` with `Release`, verifies every indexed file, and rejects
expired metadata.

## Deploy

`config/deployment.json` supplies `ssh_host`, `remote_root`, and
`temporary_directory`. The configured account needs SSH access, trusted host keys,
and permission to run the remote verification and installation commands.

```sh
make verify
make deploy
```

An alternate settings file can be selected explicitly:

```sh
python3 scripts/deploy.py --deployment-config config/deployment.json
```

The deployer uploads the archive and an explicit set of verification inputs.
Only manager operations add manager support files. Local credential directories,
the complete configuration directory, and the complete key directory are not
uploaded. The remote installer verifies the transport checksum and repository,
retains immutable pool and by-hash files, then switches the release symlink.

For initial host registration after provisioning its certificate:

```sh
python3 scripts/deploy.py --configure-caddy
```

## Manager operations

Manager settings include the database path, service container, API base URL,
backup directory, and optional certificate paths and metadata overrides.
The repository domain is derived from `config/repository.json`.

Configure the local host payload's certificate ID, upstream list, and file-server
root before applying it. Keep its input `enabled` field false; the helper enables
the configured host after applying the requested operation.

```sh
sudo python3 scripts/configure-caddy.py config/caddy-proxy-host.json --update-host
```

To import the origin certificate and key from the configured local paths:

```sh
sudo python3 scripts/configure-caddy.py --import-certificate
```

The helper backs up the configured database, creates a short-lived local API
token, applies the operation, and removes the token in a `finally` block.
Certificate material is read on the manager host. The archive signing private
key remains on the signing workstation.

Cloudflare provisioning is managed separately. Keep DNS proxying and TLS settings
consistent with the local origin certificate and host configuration. Operational
resource identifiers belong in the ignored local files.

## Refresh metadata and roll back a release

The metadata lifetime is configured by `valid_days` in `config/repository.json`.
Check each channel's signed `Valid-Until` value. Refresh metadata before expiry,
even when package versions have not changed:

```sh
export GPG_TTY="$(tty)"
make publish
make deploy
```

Keep the previous public tree or restore it before publishing from a fresh
checkout so existing package and by-hash paths remain available.

For rollback, use a retained release whose metadata is still valid. Run the
following on the storage host with its local deployment configuration available:

```sh
(
set -eu
repository_directory=$(python3 -c 'import json; from pathlib import Path; print(json.loads(Path("config/deployment.json").read_text())["remote_root"])')
printf 'Release directory name: '
IFS= read -r release_name
test -n "$release_name"
sudo test -d "$repository_directory/releases/$release_name"
sudo ln -s "releases/$release_name" "$repository_directory/current.rollback"
sudo mv -Tf "$repository_directory/current.rollback" "$repository_directory/current"
)
```
