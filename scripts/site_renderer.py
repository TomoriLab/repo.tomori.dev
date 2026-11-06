#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Render static installation, package, and source pages in Korean and English."""

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil
import struct
from string import Template
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PAGE_SIZE = 12
CATEGORIES = ['general', 'development', 'documentation', 'debug', 'all']


def escape(value):
    return html.escape(str(value), quote=True)


def package_category(package):
    name = package['Package']
    if name.endswith('-dbgsym'):
        return 'debug'
    if name.endswith('-dev'):
        return 'development'
    if name.endswith('-doc'):
        return 'documentation'
    return 'general'


def category_path(category, page=1, architecture=None):
    prefix = 'packages/' + (architecture + '/' if architecture else '') + (category + '/' if category != 'general' else '')
    return prefix if page == 1 else prefix + f'page/{page}/'


def package_page_count(packages, category):
    count = sum(category == 'all' or package_category(item) == category for item in packages)
    return max(1, math.ceil(count / PAGE_SIZE))


def suite_prefix(suite, configuration):
    if suite == configuration['default_suite']:
        return ''
    return 'backports/' if configuration['suites'][suite].get('backports') else suite + '/'


def suite_label(settings, translated):
    label = escape(settings['label'])
    if settings.get('backports'):
        label += ' ' + translated['backports_label']
    return label


def navigation_link(url, label, selected=False):
    current = ' aria-current="page"' if selected else ''
    return f'<a href="{escape(url)}"{current}>{label}</a>'


def render_code_block(identifier, label, content, translated):
    fingerprint = ' fingerprint' if identifier == 'archive-fingerprint' else ''
    return f'''<div class="code-block{fingerprint}">
      <div class="code-toolbar"><span class="code-label">{label}</span>
        <button type="button" class="copy-button" data-copy-target="{identifier}" aria-label="{translated['copy_action'].format(label=label)}" hidden>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M15 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3"/></svg>
          <span data-copy-label>{translated['copy_label']}</span>
        </button>
      </div>
      <pre><code id="{identifier}">{escape(content)}</code></pre>
    </div>'''


def read_sources(output, suite, configuration):
    index = output / 'dists' / suite / configuration['component'] / 'source/Sources'
    sources = []
    for paragraph in index.read_text().strip().split('\n\n'):
        fields = dict(re.findall(r'^([^\s:]+): (.*)$', paragraph, re.MULTILINE))
        sources.append({name: fields[name] for name in ['Package', 'Version', 'Directory', 'Vcs-Browser', 'Vcs-Git'] if name in fields})
    return sorted(sources, key=lambda item: item['Package'])


def read_package_sources(output, suite, configuration, sources):
    sources_by_version = {(source['Package'], source['Version']): source for source in sources}
    package_sources = {}
    for architecture in configuration['architectures']:
        index = output / 'dists' / suite / configuration['component'] / ('binary-' + architecture) / 'Packages'
        for paragraph in index.read_text().strip().split('\n\n'):
            fields = dict(re.findall(r'^([^\s:]+): (.*)$', paragraph, re.MULTILINE))
            source = re.fullmatch(r'([^\s]+)(?: \(([^)]+)\))?', fields.get('Source', fields['Package']))
            if not source:
                raise ValueError(f"Invalid Source field for {fields['Package']}")
            source_key = (source[1], source[2] or fields['Version'])
            if source_key not in sources_by_version:
                raise ValueError(f"Missing source metadata for {fields['Package']}: {source_key}")
            package_sources[fields['Filename']] = sources_by_version[source_key]
    return package_sources


def render_source_links(source, upstream_sources, translated):
    links = []
    for label, url in [
        (translated['upstream_source'], upstream_sources.get(source['Package'])),
        (translated['debian_packaging'], source.get('Vcs-Browser') or source.get('Vcs-Git')),
    ]:
        if not url:
            continue
        parsed = urlsplit(url)
        if parsed.scheme not in ['http', 'https'] or not parsed.netloc:
            raise ValueError(f'Invalid source repository URL: {url}')
        links.append(f'<div class="source-link"><span class="source-link-label">{label}</span>'
                     f'<a href="{escape(url)}" rel="noopener noreferrer">{escape(url)}</a></div>')
    return ''.join(links) or translated['source_unavailable']


def render_installation(suite, settings, configuration, notes, language, translated):
    base_url = configuration['base_url'].rstrip('/')
    target = escape(settings.get('target_release', suite))
    architecture_panels = []
    for index, architecture in enumerate(configuration['architectures']):
        filename = f'tomori-{suite}-{architecture}.sources'
        identifier = 'architecture-' + architecture
        checked = ' checked' if index == 0 else ''
        description = {'amd64': 'x86-64', 'arm64': 'AArch64'}.get(architecture, architecture)
        instructions = f'''sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSLo /tmp/tomori-archive-keyring.gpg {base_url}/keys/tomori-archive-keyring.gpg
gpg --show-keys --with-fingerprint /tmp/tomori-archive-keyring.gpg
sudo install -m 0644 /tmp/tomori-archive-keyring.gpg /etc/apt/keyrings/tomori-archive-keyring.gpg
curl -fsS {base_url}/{filename} | sudo tee /etc/apt/sources.list.d/tomori.sources >/dev/null
sudo apt update'''
        registration = render_code_block('repository-commands-' + architecture, translated['repository_commands'], instructions, translated)
        architecture_panels.append(f'''<input class="architecture-input visually-hidden" type="radio" name="architecture" id="{identifier}" value="{architecture}" data-architecture-choice aria-controls="{identifier}-panel"{checked}>
        <label class="architecture-option" for="{identifier}"><strong>{escape(architecture)}</strong><span>{escape(description)}</span></label>
        <div class="architecture-panel" id="{identifier}-panel" data-architecture-panel="{architecture}">
          <div class="source-download"><a class="download-button" href="/{filename}" download="{filename}">{translated['download_repository_source'].format(architecture=architecture)}</a><code>{filename}</code></div>
          {registration}
        </div>''')
    package_notes = ''.join('<li><code>' + escape(package) + '</code>: ' + escape(note[language]) + '</li>'
                            for package, note in notes.get(suite, {}).items())
    if package_notes:
        package_notes = f'<details class="package-notes"><summary>{translated["package_notes_heading"]}</summary><ul>{package_notes}</ul></details>'
    fingerprint = render_code_block('archive-fingerprint', translated['signing_key'], configuration['signing_fingerprint'], translated)
    installation = render_code_block('installation-command', translated['installation_command_label'], f'sudo apt install -t {target} PACKAGE', translated)
    architecture_instruction = translated['architecture_instruction'].format(command='<code>dpkg --print-architecture</code>')
    return f'''<div class="content-stack">
    <section class="content-card" aria-labelledby="registration-heading">
      <h2 id="registration-heading">{translated['register_repository']}</h2>
      <p>{translated['fingerprint_instruction']}</p>
      {fingerprint}
      <fieldset class="architecture-picker" aria-describedby="architecture-instruction">
        <legend>{translated['architecture_selection']}</legend>
        <p id="architecture-instruction">{architecture_instruction}</p>
        <div class="architecture-options">{''.join(architecture_panels)}</div>
      </fieldset>
    </section>
    <section class="content-card" aria-labelledby="installation-heading">
      <h2 id="installation-heading">{translated['install_packages']}</h2>
      <p>{translated['installation_selection']}</p>
      {installation}{package_notes}
    </section>
    </div>'''


def render_packages(packages, package_sources, upstream_sources, category, page, base_path, translated, architecture, architectures):
    selected = [item for item in packages if category == 'all' or package_category(item) == category]
    pages = max(1, math.ceil(len(selected) / PAGE_SIZE))
    first = (page - 1) * PAGE_SIZE
    visible = selected[first:first + PAGE_SIZE]
    categories = ''.join(navigation_link(base_path + category_path(name, architecture=architecture),
        translated['category_' + name] + f' <span class="count">{sum(name == "all" or package_category(item) == name for item in packages)}</span>',
        name == category) for name in CATEGORIES
        if name == 'all' or any(package_category(item) == name for item in packages))
    rows = ''.join('<tr role="row"><td role="cell" data-label="{package_label}"><a href="/{filename}">{package}</a></td>'
        '<td role="cell" data-label="{version_label}">{version}</td><td role="cell" data-label="{architecture_label}">{architecture}</td>'
        '<td role="cell" data-label="{description_label}" class="package-description">{description}</td>'
        '<td role="cell" data-label="{source_label}" class="source-links">{source_links}</td></tr>'.format(
        filename=escape(item['Filename']), package=escape(item['Package']), version=escape(item['Version']),
        architecture=escape(item['Architecture']), description=escape(item['Description']),
        package_label=translated['package_column'], version_label=translated['version_column'],
        architecture_label=translated['architecture_column'], description_label=translated['description_column'],
        source_label=translated['source_url_column'],
        source_links=render_source_links(package_sources[item['Filename']], upstream_sources, translated)) for item in visible)
    status = translated['package_range'].format(start=first + 1 if selected else 0, end=first + len(visible), total=len(selected))
    previous = navigation_link(base_path + category_path(category, page - 1, architecture), translated['previous_page']) if page > 1 else ''
    following = navigation_link(base_path + category_path(category, page + 1, architecture), translated['next_page']) if page < pages else ''
    architecture_links = ''.join(
        f'<a href="{escape(base_path + category_path(category, architecture=name))}" data-architecture-select="{escape(name)}"'
        + (' aria-current="page"' if name == architecture else '')
        + f'>{escape(name)}</a>' for name in architectures)
    shared = translated['architecture_shared'].format(architecture='<code>all</code>')
    return f'''<div class="catalog-card">
    <div class="catalog-architecture"><span class="section-label">{translated['architecture_selection']}</span>
      <nav class="architecture-menu" aria-label="{translated['architecture_selection']}">{architecture_links}</nav>
      <p>{shared}</p>
    </div>
    <nav class="category-menu" aria-label="{translated['package_categories']}">{categories}</nav>
    <p class="result-count">{status}</p>
    <div class="table" role="region" aria-label="{translated['packages_heading']}" tabindex="0">
      <table class="package-table" role="table" aria-label="{translated['packages_heading']}"><colgroup><col class="package-name-column"><col class="package-version-column"><col class="package-architecture-column"><col class="package-description-column"><col class="package-source-column"></colgroup>
      <thead role="rowgroup"><tr role="row"><th role="columnheader" scope="col">{translated['package_column']}</th><th role="columnheader" scope="col">{translated['version_column']}</th><th role="columnheader" scope="col">{translated['architecture_column']}</th><th role="columnheader" scope="col">{translated['description_column']}</th><th role="columnheader" scope="col">{translated['source_url_column']}</th></tr></thead>
      <tbody role="rowgroup">{rows}</tbody></table>
    </div>
    <nav class="pagination" aria-label="{translated['pagination_label']}">{previous}<span>{translated['page_status'].format(page=page, total=pages)}</span>{following}</nav>
    </div>'''


def render_sources(sources, settings, suite, translated):
    rows = []
    for source in sources:
        filename = source['Package'] + '_' + source['Version'].split(':')[-1] + '.dsc'
        directory = '/' + source['Directory'] + '/'
        rows.append(f'<tr role="row"><td role="cell" data-label="{translated["source_column"]}">{escape(source["Package"])}</td>'
                    f'<td role="cell" data-label="{translated["version_column"]}">{escape(source["Version"])}</td>'
                    f'<td role="cell" data-label="{translated["source_files"]}">'
                    f'<a href="{escape(directory + filename)}">.dsc</a> · '
                    f'<a href="{escape(directory)}">{translated["source_files"]}</a></td></tr>')
    target = escape(settings.get('target_release', suite))
    command = render_code_block('source-command', translated['source_command_label'], f'apt source -t {target} SOURCE', translated)
    return f'''<div class="content-stack">
    <section class="content-card" aria-labelledby="source-download-heading">
      <h2 id="source-download-heading">{translated['source_download']}</h2>
      <p>{translated['source_selection']}</p>{command}
    </section>
    <div class="catalog-card"><div class="table" role="region" aria-label="{translated['sources_heading']}" tabindex="0">
      <table class="source-table" role="table" aria-label="{translated['sources_heading']}"><thead role="rowgroup"><tr role="row"><th role="columnheader" scope="col">{translated['source_column']}</th><th role="columnheader" scope="col">{translated['version_column']}</th><th role="columnheader" scope="col">{translated['source_files']}</th></tr></thead>
      <tbody role="rowgroup">{''.join(rows)}</tbody></table>
    </div></div></div>'''


def write_source_configurations(output, configuration):
    for suite in configuration['suites']:
        for architecture in [None, *configuration['architectures']]:
            architectures = architecture or ' '.join(configuration['architectures'])
            suffix = '-' + architecture if architecture else ''
            filename = f'tomori-{suite}{suffix}.sources'
            entry = f"Types: deb deb-src\nURIs: {configuration['base_url']}\nSuites: {suite}\nComponents: {configuration['component']}\nArchitectures: {architectures}\nSigned-By: /etc/apt/keyrings/tomori-archive-keyring.gpg\n"
            (output / filename).write_text(entry)
    shutil.copy2(output / ('tomori-' + configuration['legacy_suite'] + '.sources'), output / 'tomori.sources')


def render_site(output, configuration, inventory):
    write_source_configurations(output, configuration)
    template = Template((ROOT / 'site/index.html').read_text())
    languages = {language: json.loads((ROOT / 'site/translations' / (language + '.json')).read_text()) for language in ['ko', 'en']}
    if languages['ko'].keys() != languages['en'].keys():
        raise ValueError('Korean and English translations must contain the same keys')
    notes = json.loads((ROOT / 'site/package-notes.json').read_text())
    upstream_sources = json.loads((ROOT / 'site/upstream-sources.json').read_text())
    operator = json.loads((ROOT / 'site/operator.json').read_text())
    operator_links = ''.join('<li><a href="' + escape(link['url']) + '" target="_blank" rel="noopener noreferrer">'
                             + escape(link['label']) + '</a></li>' for link in operator['links'])
    logo = ROOT / 'site/images/logo.png'
    logo_data = logo.read_bytes()
    if logo_data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('The repository logo must be a PNG image')
    logo_width, logo_height = struct.unpack('>II', logo_data[16:24])
    logo_name = 'logo-' + hashlib.sha256(logo_data).hexdigest()[:16] + '.png'
    asset_version = hashlib.sha256((ROOT / 'site/site.css').read_bytes() + (ROOT / 'site/language.js').read_bytes()).hexdigest()[:16]
    base_url = configuration['base_url'].rstrip('/')
    page_count = 0
    for suite, settings in configuration['suites'].items():
        prefix = suite_prefix(suite, configuration)
        packages = sorted((item for item in inventory if item['Suite'] == suite), key=lambda item: item['Package'])
        packages_by_architecture = {architecture: [item for item in packages if item['Architecture'] in [architecture, 'all']]
                                    for architecture in configuration['architectures']}
        sources = read_sources(output, suite, configuration)
        package_sources = read_package_sources(output, suite, configuration, sources)
        pages = [('', 'installation', None, 1, None), ('sources/', 'sources', None, 1, None)]
        for architecture in [None, *configuration['architectures']]:
            catalog = packages_by_architecture[architecture] if architecture else packages
            for category in CATEGORIES:
                for page in range(1, package_page_count(catalog, category) + 1):
                    pages.append((category_path(category, page, architecture), 'packages', category, page, architecture))
        for language in languages:
            translated = {name: escape(value) for name, value in languages[language].items()}
            base_path = '/' + language + '/' + prefix
            package_directory = output / language / prefix / 'packages'
            if package_directory.exists():
                # Rebuilding the generated catalog removes obsolete pagination and unfiltered pages.
                shutil.rmtree(package_directory)
            for relative_path, view, category, page, requested_architecture in pages:
                architecture = requested_architecture or configuration['architectures'][0]
                catalog_architecture = architecture if view == 'packages' else ''
                catalog = packages_by_architecture[architecture] if view == 'packages' else packages
                canonical_path = relative_path
                catalog_targets = ''
                if view == 'installation':
                    content = render_installation(suite, settings, configuration, notes, language, translated)
                elif view == 'packages':
                    requested_page = page
                    page = min(page, package_page_count(catalog, category))
                    canonical_path = category_path(category, page, architecture)
                    if requested_architecture is None:
                        catalog_targets = escape(json.dumps({name: base_path + category_path(category,
                            min(requested_page, package_page_count(items, category)), name)
                            for name, items in packages_by_architecture.items()}))
                    content = render_packages(catalog, package_sources, upstream_sources, category, page, base_path, translated,
                                              architecture, configuration['architectures'])
                else:
                    content = render_sources(sources, settings, suite, translated)
                package_path = category_path('general', architecture=architecture)
                view_path = {'installation': '', 'packages': package_path, 'sources': 'sources/'}[view]
                suite_navigation = ''.join(navigation_link('/' + language + '/' + suite_prefix(name, configuration) + view_path,
                    suite_label(other, translated) + (' <span class="badge">' + translated['default_label'] + '</span>' if name == configuration['default_suite'] else ''),
                    name == suite) for name, other in configuration['suites'].items())
                menu_navigation = ''.join(navigation_link(base_path + path, translated['menu_' + name], name == view)
                    for name, path in [('installation', ''), ('packages', package_path), ('sources', 'sources/')])
                page_path = prefix + canonical_path
                suite_name = suite_label(settings, translated)
                suite_description = translated['backports_description' if settings.get('backports') else 'unstable_description']
                context = translated | {
                    'base_url': escape(base_url), 'asset_version': asset_version, 'language': language,
                    'logo_url': '/assets/' + logo_name,
                    'social_image_url': escape(base_url + '/assets/' + logo_name),
                    'social_image_width': str(logo_width), 'social_image_height': str(logo_height),
                    'locale': 'ko_KR' if language == 'ko' else 'en_US',
                    'alternate_locale': 'en_US' if language == 'ko' else 'ko_KR',
                    'page_title': translated['menu_' + view] + ' · ' + suite_name + ' · ' + translated['title'],
                    'page_description': translated['intro_' + view] + ' ' + suite_description,
                    'language_redirect': 'false', 'default_suite': escape(configuration['default_suite']),
                    'suite': escape(suite), 'view_path': escape(canonical_path),
                    'catalog_architecture': escape(catalog_architecture), 'catalog_targets': catalog_targets,
                    'canonical_url': escape(base_url + '/' + language + '/' + page_path),
                    'korean_url': '/ko/' + page_path, 'english_url': '/en/' + page_path,
                    'korean_current': ' aria-current="page"' if language == 'ko' else '',
                    'english_current': ' aria-current="page"' if language == 'en' else '',
                    'suite_navigation': suite_navigation, 'menu_navigation': menu_navigation,
                    'suite_name': suite_name,
                    'view_title': translated['menu_' + view], 'view_intro': translated['intro_' + view],
                    'package_count': str(len(catalog)), 'source_count': str(len(sources)),
                    'architectures': escape(architecture + ', all' if view == 'packages' else ', '.join(configuration['architectures'])),
                    'operator_name': escape(operator['name']), 'operator_links': operator_links,
                    'suite_description': suite_description,
                    'compatibility': translated['compatibility'].format(architectures=', '.join(configuration['architectures'])),
                    'content': content,
                    'release_url': '/dists/' + suite + '/InRelease',
                }
                destination = output / language / prefix / relative_path
                destination.mkdir(parents=True, exist_ok=True)
                (destination / 'index.html').write_text(template.substitute(context))
                page_count += 1
                if language == 'en' and suite == configuration['default_suite'] and not relative_path:
                    (output / 'index.html').write_text(template.substitute(context | {'language_redirect': 'true'}))
                    page_count += 1
    assets = output / 'assets'
    assets.mkdir(exist_ok=True)
    for name in ['site.css', 'language.js']:
        shutil.copy2(ROOT / 'site' / name, assets / name)
    shutil.copy2(logo, assets / logo_name)
    shutil.copytree(ROOT / 'site/fonts', assets / 'fonts', dirs_exist_ok=True)
    return page_count


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/public')
    arguments = parser.parse_args()
    configuration = json.loads((ROOT / 'config/repository.json').read_text())
    inventory = json.loads((arguments.output / 'package-inventory.json').read_text())
    count = render_site(arguments.output, configuration, inventory)
    print(json.dumps({'pages': count, 'packages': len(inventory), 'default_suite': configuration['default_suite']}))
