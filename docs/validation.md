# Validation records

These are dated validation snapshots rather than a live package count or service
status. The [public inventory](https://repo.tomori.dev/package-inventory.json)
records the published package versions and architectures.

## Initial amd64 release: 7 November 2026

The following record predates the arm64 publication and architecture-filtered
catalog. Its counts describe that release stage.

The 2026-11-07 Trixie deployment contains 103 binary packages, including 45 debug
symbol packages, from seven source packages. The 18 existing unstable binaries
retain their versions and SHA-256 hashes. Verification checks both suites on the
workstation and again on the server before publication.

A fresh Debian 13 amd64 container installed `kwi` and `kwi-part` directly from
the public HTTPS repository using `apt-get install -t tomori-trixie`. APT selected
Qt 6.8.2 from Debian and the required backports from this archive. `apt-get check`
and `dpkg --audit` passed, and an upgrade simulation reported no pending updates
or removals. Dependencies for all 58 non-debug packages resolved in a separate
APT simulation; those 58 packages were not all installed.

The installed packages passed the PTY command test and KPart loading with four
settings pages under Xvfb with software OpenGL. The standalone application also
rendered all five settings pages. Both Kirigami form styles loaded; the optional
flat style emitted transient parent-layout warnings. Physical GPU rendering,
Wayland sessions, and Flatpak host activation were not tested. Trixie's older
KNotifications API leaves the notification configuration action disabled.

APT downloaded all 25 files for the seven Trixie source packages through the
public repository. Their SHA-256 hashes matched the signed Sources index. The
Korean and English pages displayed the correct package counts and installation
commands when switching releases. No packages were installed on the workstation
or repository server during these checks.

## arm64 publication: 7 November 2026

Native arm64 builds were published for unstable and trixie. The signed inventory
contained the following entries, including debug symbols and retained data
package versions:

| Channel | amd64 | arm64 | all | Total |
| --- | ---: | ---: | ---: | ---: |
| unstable | 16 | 16 | 2 | 34 |
| trixie | 96 | 96 | 8 | 200 |

All 121 binary files from the previous amd64 publication retained their hashes.
All 152 ELF payloads in the arm64 packages identified AArch64. Fresh native arm64
containers installed Kwi and KPart from the public archive on both releases.
All 11 regular unstable packages and 58 regular trixie packages were installed
in those containers. APT dependency checks, PTY commands, KPart loading, and all
four KPart settings pages passed with both default and flat form styles.

The trixie Kirigami Addons revision `1.15.0-1~bpo13+2` includes explicit ownership
for generated menu objects. Its 13-test suite and 20 repetitions of the menu
lifetime test passed. GPU and Wayland behavior remained outside these checks.

## Architecture-specific downloads and catalogs: 7 November 2026

Four public `.sources` downloads were checked with isolated signed APT updates.
Each acquired its selected architecture's binary index and selected the expected
Kwi candidate.

At the catalog-filtering validation stage, the site contained
201 pages, including 104 architecture-specific catalog pages and 88 legacy
catalog aliases. Each architecture's unstable catalog contained 18 entries;
each trixie catalog contained 104. Shared `all` entries appeared in both
architecture catalogs.

Generated rows, descriptions, both source links, category totals, page counts,
and internal links passed validation. An additional fixture covered unequal
architecture totals, an empty debug category, and legacy page clamping.
JavaScript contract checks covered saved preferences, explicit architecture
URLs, language and channel navigation, legacy URLs, and blocked storage.
Twenty public catalog URLs and the deployed JavaScript and CSS matched the
validated output.

Browser visual and interaction checks were not repeated after preview access
was denied. The additional catalog and runtime harnesses were task-local and
are not included in this repository.
