# Automation notes

Context for AI-assisted work and other automation. Keep end-user instructions in
the [public README](../README.md) and implementation or operational details in
this directory.

Project source code and documentation use `AGPL-3.0-only`; preserve the SPDX
identifiers and [license text](../LICENSE). The bundled font retains its OFL
notice. The logo and distributed Debian packages are outside the project's
software license grant.

## Entry points

| Path | Responsibility |
| --- | --- |
| `config/repository.json` | Channels, architectures, projects, signing fingerprint, and metadata lifetime |
| `scripts/build-repository.py` | Manifest verification, immutable package pool, indexes, and inventory |
| `scripts/site_renderer.py` | Static pages and architecture-specific source configurations |
| `scripts/sign-repository.py` | Sign each configured channel |
| `scripts/verify-repository.py` | Verify signatures, expiration, indexes, and payloads |
| `config/deployment.json` | Ignored environment-specific deployment and manager settings |
| `scripts/deployment_config.py` | Validate local deployment settings |
| `scripts/deploy.py` | Verified SSH upload and atomic release switch |
| `scripts/configure-caddy.py` | Caddy Proxy Manager host and certificate operations |
| `site/` | Templates, translations, styles, navigation, assets, and package metadata |

The public JSON templates are `config/*.example.json`. Runtime JSON settings are
local and ignored; initialize them with the [configuration guide](configuration.md).
Keep real SSH destinations, origin addresses, storage paths, container names,
account IDs, resource IDs, and certificate IDs out of public files, including
examples, tests, documentation, and comments. The archive fingerprint is public
and must match the local archive keyrings.

Build output and package artifacts are ignored by Git. A clean checkout needs
the corresponding package artifacts to build an archive. Existing signed output
is sufficient for a site-only regeneration. See
[Publishing and operations](operations.md) for the complete commands.

Local environment files, private keys, TLS material, credential files, database
copies, logs, and backups are also ignored. The entire `keys/` directory is
excluded from Git. Environment examples can be published as
`.env.example` or `.env.template`. Ignore rules apply to untracked files;
inspect the Git index separately when adding exclusions.

## Behavior to preserve

- Package files at published paths are immutable. Changed artifacts require a
  new Debian package version. Retain old pool and `by-hash` files during updates.
- Channel membership comes from configured project manifests. A file's presence
  in the shared pool does not make it part of every channel.
- Filter catalogs by the selected architecture and `all` before calculating
  category totals or pagination. Explicit architecture paths work without
  JavaScript. Legacy package paths retain a usable fallback.
- Installation and catalog navigation share
  `tomori-repository-architecture`. Explicit catalog URLs take precedence over
  a stored choice. Invalid preferences and blocked storage retain usable links.
- English is the default language. Explicit language URLs and saved manual
  preferences retain their defined behavior. Korean and English translation
  files contain the same keys.
- Source links match each binary's source package and version, including debug
  symbol packages. Preserve both upstream and Debian packaging links.
- Static Open Graph metadata, keyboard focus, mobile layouts, local fonts,
  appearance preferences, and operator links are part of the site behavior.
- Archive signing runs on the signing workstation. The private archive key
  stays off the deployment server.

## Publication boundary

Use ignored local configuration for deployment-specific values. Public examples
leave those fields unset. Retain configuration validation before remote access
and keep deployment uploads limited to the explicitly required files. Audit
publication candidates using Git ignore rules and inspect the index separately;
ignored local configuration is intentionally outside the published source tree.

## Checks by change

For deployment changes:

```sh
python3 -m unittest discover -s tests -v
```

These tests use temporary files and dummy resources. SSH, Docker, manager API,
and certificate-tool calls are mocked. They check configuration validation,
upload contents, token cleanup, and atomic activation without contacting an
operational service. Run them in an isolated environment with no credentials or
external network access.

For site changes with existing signed output:

```sh
make site
make verify
python3 -m py_compile scripts/site_renderer.py
node --check site/language.js
```

Check both languages, both channels, and both architectures. Include shared
`all` packages, unequal architecture totals, empty categories, final pages,
legacy URLs, and navigation between installation and catalog pages. Compare
the generated `.sources` files with their channel and architecture selection.

For artifact changes, follow the build, sign, and verify procedure in
[Publishing and operations](operations.md). Validate installation against the
public archive in an isolated environment for the target release and
architecture. A successful APT simulation does not establish runtime behavior.

For documentation-only changes, validate links, fenced shell syntax, and the
documented file paths. Rebuilding packages or deploying the archive is not
required to validate a Markdown change.

Keep validation results scoped to the checks actually performed. Static HTML
and JavaScript checks do not establish browser appearance or interaction.
Container tests with Xvfb and software rendering do not establish physical GPU,
Wayland, or host desktop behavior. Previous stage-specific results are recorded
in [Validation records](validation.md).
