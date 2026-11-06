<!-- SPDX-License-Identifier: AGPL-3.0-only -->

# Security policy

## Reporting a vulnerability

Report suspected vulnerabilities privately before publishing exploit details.
The maintainer is [zeroday0619](https://github.com/zeroday0619).

When available, use **Report a vulnerability** in the GitHub repository's
security advisories. Private vulnerability reporting must be enabled separately
from this file; see [GitHub's reporting guide](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately).

If that option is unavailable, open an issue titled
`Request for private security contact` containing only a request for a private
reporting channel. Do not include the affected endpoint, exploit, credentials,
or other sensitive details in the public issue. Wait for an agreed private
channel before sharing the report.

Include the following in the private report:

- Affected source revision or public URL. For package issues, include the
  package name, version, Debian channel, and architecture.
- A description of the trust boundary crossed and the potential impact.
- Reproduction steps or a minimal proof of concept using dummy data.
- Required privileges, configuration, and other exploitation conditions.
- Relevant redacted logs and any proposed mitigation.

Never send private signing keys, TLS private keys, credentials, complete
configuration files, database copies, or unrelated personal information.
Coordinate remediation and public disclosure with the maintainer. This policy
does not specify response or remediation deadlines.

## Scope and trust boundaries

This policy covers the static repository website, archive generation and
verification tools, signing and deployment scripts, public configuration
examples, and the integrity of the published APT archive at `repo.tomori.dev`.
It applies to the source tree rooted at this file, including `scripts/`,
`site/`, `config/`, and `tests/`.

The public website serves static content and signed Debian archive metadata.
Building, signing, publishing, and management operations are separate trusted
maintainer actions. The signing workstation, deployment credentials, local
configuration, management interfaces, and private key material are outside the
public content boundary.

Package manifests, filenames, archive members, package descriptions, source
links, and other metadata remain inputs requiring validation. Their inclusion
in a maintainer workflow does not make them executable instructions or safe
HTML. A report should distinguish an unauthenticated public attack from one
that requires a maintainer to process an artifact or run a privileged command.

## Security requirements

The following properties define the intended security boundaries. They are
requirements for implementation and review, not a claim that every deployment
or failure mode has been verified.

- Published suites must have valid signatures from the configured archive
  signing key. Verification must check signed metadata, expiration, manifest
  sizes, and hashes of indexed content before activating a release.
- The private archive signing key must remain on the signing workstation.
  Only public key exports may enter the published archive. Client trust must
  use the archive key specified in the [installation instructions](README.md#add-the-repository).
- Artifact paths and archive members must remain within their intended
  directories. Traversal, unsafe links, or unexpected file types must not
  overwrite files outside those boundaries.
- Files at published package and by-hash paths must remain immutable.
  Conflicting content must stop publication. Release activation must occur
  atomically after verification so a failed update retains the active release.
- Package metadata and URLs must not become executable code, unsafe HTML, or
  script-capable links in generated pages. Rendering must preserve escaping
  and validate URL schemes where links are constructed.
- Deployment destinations, origin addresses, storage paths, management
  endpoints, instance identifiers, and private certificate paths must come
  from ignored local settings. Public examples must leave these values unset.
  Missing required settings must stop the operation before remote changes.
- SSH publishing must verify host identity and upload only explicitly required
  archive and support files. Complete credential, configuration, and key
  directories must not be copied as deployment support.
- Management credentials and TLS private keys must remain outside public
  content, diagnostics, and source control. Temporary management tokens must
  have bounded lifetimes and be removed after success or failure.

## Assessing reports and package issues

Report signing or verification bypasses, publication of unauthorized content,
command execution, path escapes, credential exposure, management access, and
browser script injection with evidence of the affected boundary. Severity
depends on reachability, required privileges, and the resulting impact. A test
pass, dependency version, or scanner alert alone does not establish whether a
boundary can be crossed.

For vulnerabilities in distributed packages or dependencies, include the
upstream advisory and affected package version when available. Report archive
integrity failures and vulnerabilities introduced by this project's packaging
or publishing process here. Upstream vulnerabilities may also require a report
to the affected project's security contact. A third-party origin does not
exclude a report that demonstrates an impact on this archive or its users.

An archive signature establishes the origin and integrity of signed content;
it does not establish that a package has no vulnerabilities. Historical files
may be retained for archive consistency. Their continued availability does not
establish a security maintenance commitment for every retained version.

## Handling sensitive information

Runtime configuration and the entire local `keys/` directory are excluded from
Git. Ignore rules do not remove material already tracked or present in history.
If a credential is exposed, revoke or rotate it and coordinate removal of
affected files and historical copies. Removing a hardcoded value alone does
not invalidate an exposed credential.

The public archive domain, public signing-key fingerprint, public key exports,
and operator profile links are intentional public information. Report them
when they are involved in a demonstrated security failure rather than solely
because they are visible.

Use local fixtures and systems under your control for reproduction. This
policy does not authorize testing against the live repository, origin server,
management services, or third-party infrastructure. Obtain explicit permission
before testing those systems. Operational configuration guidance is in
[Configuration](docs/configuration.md) and
[Publishing and operations](docs/operations.md).
