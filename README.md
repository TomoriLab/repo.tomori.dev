# repo.tomori.dev

A signed APT repository for Debian binary and source packages.

[Browse the repository](https://repo.tomori.dev/) ·
[English](https://repo.tomori.dev/en/) ·
[한국어](https://repo.tomori.dev/ko/)

## Supported systems

Debian unstable is the default channel. Debian 13 (trixie) has a separate
backports channel. Both support amd64 (x86-64) and arm64 (AArch64).

| Channel | amd64 configuration | arm64 configuration |
| --- | --- | --- |
| Debian unstable | [Download .sources](https://repo.tomori.dev/tomori-unstable-amd64.sources) | [Download .sources](https://repo.tomori.dev/tomori-unstable-arm64.sources) |
| Debian 13 (trixie) backports | [Download .sources](https://repo.tomori.dev/tomori-trixie-amd64.sources) | [Download .sources](https://repo.tomori.dev/tomori-trixie-arm64.sources) |

The website lets you select a channel and architecture. Package lists include
the selected architecture and shared `all` packages, with descriptions and links
to upstream code and Debian packaging repositories.

## Add the repository

The setup requires `curl` and GnuPG. Install them if needed:

```sh
sudo apt install ca-certificates curl gnupg
```

The archive signing key fingerprint is:

```text
55A5EA46C60A959E75119B4F39F74FF9CEA87CC9
```

Use `suite=unstable` for Debian unstable. For Debian 13, change it to
`suite=trixie`. The commands detect the system architecture, check the key
fingerprint, and register the matching source configuration.

```sh
(
set -eu
suite=unstable
architecture=$(dpkg --print-architecture)
key_directory=$(mktemp -d)
trap 'rm -rf -- "$key_directory"' EXIT

curl -fsSLo "$key_directory/tomori.gpg" \
  https://repo.tomori.dev/keys/tomori-archive-keyring.gpg
fingerprint=$(gpg --show-keys --with-colons "$key_directory/tomori.gpg" \
  | awk -F: '$1 == "fpr" { print $10; exit }')
test "$fingerprint" = 55A5EA46C60A959E75119B4F39F74FF9CEA87CC9
curl -fsSLo "$key_directory/tomori.sources" \
  "https://repo.tomori.dev/tomori-$suite-$architecture.sources"

sudo install -d -m 0755 /etc/apt/keyrings /etc/apt/sources.list.d
sudo install -m 0644 "$key_directory/tomori.gpg" \
  /etc/apt/keyrings/tomori-archive-keyring.gpg
sudo install -m 0644 "$key_directory/tomori.sources" \
  /etc/apt/sources.list.d/tomori.sources
sudo apt update
)
```

## Install packages

Choose a package from the website and replace `PACKAGE` with its name. Specify
the target release on the initial installation so APT selects the required
dependencies.

On Debian unstable:

```sh
sudo apt install -t unstable PACKAGE
```

On Debian 13 (trixie):

```sh
sudo apt install -t tomori-trixie PACKAGE
```

Check the candidate version with `apt-cache policy PACKAGE`. Use normal APT
commands to update installed packages. Package-specific compatibility notes are
listed on the installation page.

## Source packages

The source configurations enable both `deb` and `deb-src`. Download source
archives from the website's Sources menu or use APT:

```sh
apt source -t unstable SOURCE
```

For trixie backports, use `apt source -t tomori-trixie SOURCE`. Replace `SOURCE`
with the source package name shown in the catalog.

## Maintainer

Maintained by [zeroday0619](https://github.com/zeroday0619).

[Profile](https://zeroday0619.dev) ·
[Debian Salsa](https://salsa.debian.org/zeroday0619) ·
[Twitter](https://twitter.com/dev_zeroday0619) ·
[Mastodon](https://social.silicon.moe/@zeroday0619) ·
[Tomori Lab](https://github.com/TomoriLab)

## Project documentation

This Git repository contains the website and archive publishing tools. Packages
and source archives are distributed through APT. Implementation details,
operating procedures, and automation notes are in the
[maintainer documentation](docs/README.md).

For vulnerability reporting and security boundaries, see the
[security policy](SECURITY.md).

## License

The original source code and documentation in this repository are licensed under
the GNU Affero General Public License, version 3 only (`AGPL-3.0-only`). See
[LICENSE](LICENSE) for the complete terms.

Separate materials retain their own licensing:

- The bundled Pretendard font uses the
  [SIL Open Font License 1.1](site/fonts/OFL.txt).
- The logo artwork in `site/images/logo.png` is outside this software license
  grant.
- Debian packages and upstream source archives distributed through APT retain
  their respective licenses.

## AI-Generated Code Notice

Parts of this project were created with assistance from AI tools (e.g. large language models). All AI-assisted contributions were reviewed and adapted by maintainers before inclusion. If you need provenance for specific changes, please refer to the Git history and commit messages.
