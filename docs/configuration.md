# Configuration examples

Public examples are in `config/`. Copy them to the local filenames expected by
the scripts, then set the deployment-specific values. Run this from the
repository root; existing local files are preserved:

```sh
for name in repository deployment caddy-proxy-host cloudflare; do
    if [ ! -e "config/$name.json" ]; then
        cp "config/$name.example.json" "config/$name.json"
    fi
done
```

| Public example | Local file | Purpose |
| --- | --- | --- |
| [repository.example.json](../config/repository.example.json) | `config/repository.json` | Archive generation, signing, verification, and site rendering |
| [deployment.example.json](../config/deployment.example.json) | `config/deployment.json` | SSH destination, storage paths, and manager connection settings |
| [caddy-proxy-host.example.json](../config/caddy-proxy-host.example.json) | `config/caddy-proxy-host.json` | Caddy Proxy Manager host creation or updates |
| [cloudflare.example.json](../config/cloudflare.example.json) | `config/cloudflare.json` | Record of Cloudflare DNS, TLS, and resource identifiers |

Local JSON settings, certificates, private key material, and the entire `keys/`
directory are ignored by Git. The four named JSON examples remain publishable.

## Archive settings

The repository example contains the public settings for `repo.tomori.dev`,
including its channels, architectures, project lists, and signing fingerprint.
The fingerprint must match the locally prepared public keyrings in `keys/`.

For a different archive, update the origin, label, base URL, signing fingerprint,
and project lists. Supply the corresponding public keyrings and package
artifacts before building. The private signing key stays on the signing
workstation.

## Local public keyrings

Prepare binary and ASCII-armored public exports on the signing workstation.
The following commands read the configured fingerprint and export its public
key from the local GnuPG keyring:

```sh
(
set -eu
fingerprint=$(python3 -c 'import json; from pathlib import Path; print(json.loads(Path("config/repository.json").read_text())["signing_fingerprint"])')
gpg --list-keys "$fingerprint"
mkdir -p keys
gpg --export "$fingerprint" > keys/tomori-archive-keyring.gpg
gpg --armor --export "$fingerprint" > keys/tomori-archive-keyring.asc
)
```

These files remain local build inputs. The archive builder copies the public
exports into the published APT tree so clients can download the signing key.
Only public exports belong in this directory; the private signing key stays
in the workstation's GnuPG keyring.

## Deployment settings

The deployment example contains unset fields. Fill these in the ignored local
`config/deployment.json` before running deployment or manager operations:

| Field | Local value |
| --- | --- |
| `ssh_host` | SSH destination accepted by the local OpenSSH client |
| `remote_root` | Absolute directory containing release directories and the current symlink |
| `temporary_directory` | Absolute remote directory for private upload staging |
| `manager.database_path` | Absolute path of the manager database on its host |
| `manager.web_container` | Container in which the manager API client runs |
| `manager.api_base_url` | Internal HTTP or HTTPS API base URL without embedded credentials |
| `manager.api_port_environment` | Optional container environment variable that overrides the API port |
| `manager.backup_directory` | Absolute database-backup directory |
| `manager.origin_certificate` | Absolute server-local origin-certificate path |
| `manager.private_key` | Absolute server-local TLS private-key path |
| `manager.metadata_overrides` | Optional manager metadata applied during host creation |

SSH publishing needs the top-level fields. Manager operations also need the
manager connection and backup fields. Certificate import needs its certificate
and private-key paths. No production destination or path is used as a fallback.

## Caddy host settings

Set the upstream list and file-server root for the target instance. The public
example leaves the list empty and the root unset. Set `certificateId` to the
integer ID of the certificate provisioned in the target Caddy Proxy Manager.
Its example value is `null` because certificate IDs
belong to a specific manager instance. Configure this field before applying the
host configuration.

Keep `enabled: false` in the local input file: `configure-caddy.py` creates or
updates the host and enables it through the manager API. The example retains
the file-server handler, public APT access, cache headers, and by-hash paths for
both channels and architectures. `customPreHandlersJson` is a JSON string
containing the handler array.

The scripts load environment-specific settings from the ignored deployment
configuration. See [Publishing and operations](operations.md).

## Cloudflare record

Cloudflare configuration is provisioned separately. `cloudflare.json` records
the resulting state; the Python publishing scripts do not apply this file to
the Cloudflare API.

Fill the account and zone IDs, DNS record ID and origin IPv4 address, rule IDs,
and certificate ID and expiration from the target environment. `null` values in
the example mean these fields have not been configured. The public domain,
proxied DNS setting, and strict TLS rule describe the intended repository setup.
Keep API credentials in the local credential environment rather than these
publishable examples.
