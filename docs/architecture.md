# Repository architecture

Implementation reference for maintainers and automation agents. User installation
instructions are in the [public README](../README.md). Publishing commands and
server configuration are in [Publishing and operations](operations.md).

## APT source configuration

`scripts/site_renderer.py` generates one `.sources` download for every channel
and architecture. Each file enables `deb` and `deb-src`, selects one
architecture, and uses `/etc/apt/keyrings/tomori-archive-keyring.gpg` through
`Signed-By`.

The existing `tomori-unstable.sources` and `tomori-trixie.sources` files contain
both supported architectures. The legacy `tomori.sources` alias continues to
select the combined unstable configuration.

The trixie source file uses `Suites: trixie`. Its signed metadata uses
`Suite: tomori-trixie` and `Codename: trixie`. The distinct target allows
`apt install -t tomori-trixie` to select archive dependencies without making
Debian's base trixie archive the target over `trixie-security`.

Both channels set `NotAutomatic: yes` and `ButAutomaticUpgrades: yes` for
priority 100. Initial installation instructions explicitly select the target
release. See the [APT priority rules](https://manpages.debian.org/trixie/apt/apt_preferences.5.en.html).

## Website rendering and navigation

English is the default at the root URL regardless of browser language
preferences. A saved manual language selection takes precedence on later visits.
Explicit `/ko/` and `/en/` URLs always display the requested language. The root
HTML is English when JavaScript is unavailable, and language links remain usable.

Translations are in `site/translations/`, with a shared HTML template and static
CSS and JavaScript in `site/`. Each language has separate Installation, Packages,
and Sources pages. `/ko/` and `/en/` default to unstable; their `backports/`
subdirectories display Debian 13 packages. Channel, section, category, and
pagination menus are ordinary links that work without JavaScript. Package lists
have General, Development, Documentation, Debug symbols, and All categories,
with at most 12 packages per page. Each package row includes its original Debian
description synopsis, an upstream code repository URL, and a Debian packaging
repository URL. Source associations come from the binary indexes' `Source`
fields and match the source version in `Sources`, including debug symbol packages.
Debian repository URLs come from `Vcs-Browser` or `Vcs-Git`. Upstream code URLs
are maintained by source package name in `site/upstream-sources.json` so project
homepages are not mistaken for code repositories.
Language links preserve the current page.
Legacy `?suite=trixie` links redirect to the corresponding backports page.
Package pages have separate amd64 and arm64 paths, such as
`/en/packages/amd64/` and `/en/packages/arm64/`. Each catalog includes the selected
architecture and shared `all` packages. Category counts, result ranges, page
counts, and the header package count are calculated from this filtered set.
Switching architecture keeps the category and returns to its first page.
Language and channel links retain the selected architecture.

The catalog uses the same `tomori-repository-architecture` preference as the
installation page. With JavaScript enabled, installation choices update package
menu links and old package URLs redirect to the preferred architecture.
Explicit architecture URLs take precedence and update the preference.
Without JavaScript, architecture, category, and pagination links work as ordinary
static navigation. Old package URLs show amd64 with shared `all` packages.
Package-specific requirements are in `site/package-notes.json` and appear in an
expandable notes section on the installation page.
Asset URLs contain a content-derived version to invalidate browser and CDN
caches after website updates. The language script bypasses Rocket Loader and
handles language preferences, appearance preferences, copying commands, and
legacy URLs; the menus do not depend on it.
To publish website changes using the existing
signed repository indexes:

```sh
make site
make verify
make deploy
```

## Design and assets

The interface follows the palette, typography, spacing, geometry, and
accessibility guidance in the profile project's
[Fluent 2 design document](https://github.com/zeroday0619/profile/blob/main/DESIGN.md)
(reference blob `9ff7e8ba46b5d8646b6ab7e5db59d85a7a982bed`). The static repository
uses semantic HTML controls and CSS tokens for that visual system. The reference
project's React, server-rendering, profile, and Nintendo-specific implementation
details do not apply to this static archive.

The default appearance follows the system color scheme. Explicit light, dark,
or system choices use `tomori-repository-theme` in local storage and persist
across pages. Existing language preferences continue to use
`tomori-repository-language`. Both themes include visible keyboard focus,
reduced-motion rules, and forced-colors styles. A skip link targets the main
content. Primary controls have a minimum 48 CSS pixel touch area.

Package and source tables become labeled cards below 768 CSS pixels. Long
versions, descriptions, repository URLs, and commands wrap within their
containers. Copy buttons provide a live status message and preserve focus;
commands remain selectable when JavaScript is unavailable.

The Segoe UI and system font stack uses a bundled Pretendard variable font for
Korean coverage. The font is served from `site/fonts/` with its SIL Open Font
License in `site/fonts/OFL.txt`; rendering does not depend on a remote font host.
The font binary was obtained from the profile project's `public/fonts/` folder.
Operator identity and the six profile and organization destinations
are maintained in `site/operator.json` and rendered in the footer of every page.

The repository logo is stored in `site/images/logo.png`. The renderer
publishes a filename containing its content hash and uses it in the header,
footer, and browser icon. Explicit dimensions reserve space before the image
loads, and `object-fit: contain` preserves the complete artwork and aspect ratio.
Adjacent brand text supplies the accessible name, so logo images have empty
alternative text to avoid duplicate announcements.

Every generated page includes static [Open Graph](https://ogp.me/) metadata for
its language, section, and release channel. The title and description identify
the current section and channel, `og:url` matches the canonical URL, and locale
metadata identifies the English and Korean variants. The original logo is the
share image at an absolute HTTPS URL. Its dimensions are read from the PNG during
rendering, and its alternative description is localized. Link previews can read
this metadata without running JavaScript.

## Archive format references

- [apt-secure](https://manpages.debian.org/unstable/apt/apt-secure.8.en.html)
  describes signed repository metadata.
- [apt-ftparchive](https://manpages.debian.org/unstable/apt-utils/apt-ftparchive.1.en.html)
  describes binary, source, and Release index generation.
