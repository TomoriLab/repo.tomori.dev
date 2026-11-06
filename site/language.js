// SPDX-License-Identifier: AGPL-3.0-only
(() => {
  "use strict";
  const supportedLanguages = ["ko", "en"];
  const supportedArchitectures = ["amd64", "arm64"];
  const languageStorageKey = "tomori-repository-language";
  const themeStorageKey = "tomori-repository-theme";
  const architectureStorageKey = "tomori-repository-architecture";
  const documentSettings = document.documentElement.dataset;
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  const copyResetTimers = new WeakMap();
  let themePreference = "system";
  let activeCopyButton = null;

  function storedValue(key) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  function storeValue(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      // Explicit selections still apply to the current page when storage is blocked.
    }
  }

  function applyTheme() {
    document.documentElement.dataset.theme = themePreference === "system"
      ? (systemTheme.matches ? "dark" : "light") : themePreference;
  }

  const storedTheme = storedValue(themeStorageKey);
  if (["system", "light", "dark"].includes(storedTheme)) themePreference = storedTheme;
  applyTheme();
  systemTheme.addEventListener("change", () => {
    if (themePreference === "system") applyTheme();
  });

  function preferredLanguage() {
    const selectedLanguage = storedValue(languageStorageKey);
    if (supportedLanguages.includes(selectedLanguage)) return selectedLanguage;
    return "en";
  }

  function preferredArchitecture() {
    const architecture = storedValue(architectureStorageKey);
    return supportedArchitectures.includes(architecture) ? architecture : supportedArchitectures[0];
  }

  function activeArchitecture() {
    return !documentSettings.catalogTargets && supportedArchitectures.includes(documentSettings.catalogArchitecture)
      ? documentSettings.catalogArchitecture : preferredArchitecture();
  }

  function catalogUrl(value, architecture) {
    const target = new URL(value, location.origin);
    if (target.origin !== location.origin) return null;
    const segments = target.pathname.split("/");
    const index = segments.indexOf("packages");
    if (index === -1) return null;
    if (supportedArchitectures.includes(segments[index + 1])) {
      segments[index + 1] = architecture;
    } else {
      segments.splice(index + 1, 0, architecture);
    }
    target.pathname = segments.join("/");
    return target;
  }

  function updateCatalogLinks(architecture) {
    for (const link of document.querySelectorAll("a[href]")) {
      if (link.hasAttribute("data-architecture-select")) continue;
      const target = catalogUrl(link.href, architecture);
      if (target) link.href = target.pathname + target.search + target.hash;
    }
  }

  const legacySuite = new URL(location.href).searchParams.get("suite");
  if (documentSettings.languageRedirect === "true" || ["unstable", "trixie"].includes(legacySuite)) {
    const language = documentSettings.languageRedirect === "true" ? preferredLanguage() : document.documentElement.lang;
    const suite = ["unstable", "trixie"].includes(legacySuite) ? legacySuite : documentSettings.defaultSuite;
    const prefix = suite === "trixie" ? "backports/" : "";
    const target = new URL(`/${language}/${prefix}${documentSettings.viewPath}`, location.origin);
    target.search = location.search;
    target.searchParams.delete("suite");
    target.hash = location.hash;
    const catalogTarget = catalogUrl(target, activeArchitecture());
    if (catalogTarget) catalogTarget.pathname = catalogTarget.pathname.replace(/\/page\/\d+\/$/, "/");
    location.replace((catalogTarget || target).href);
  } else if (documentSettings.catalogTargets) {
    const targets = JSON.parse(documentSettings.catalogTargets);
    location.replace(new URL(targets[preferredArchitecture()], location.origin).href);
  }

  function initializeControls() {
    const architectureInputs = [...document.querySelectorAll("[data-architecture-choice]")];
    const selectedArchitecture = activeArchitecture();
    if (!documentSettings.catalogTargets && supportedArchitectures.includes(documentSettings.catalogArchitecture)) {
      storeValue(architectureStorageKey, selectedArchitecture);
    }
    updateCatalogLinks(selectedArchitecture);
    for (const input of architectureInputs) {
      if (input.value === selectedArchitecture) input.checked = true;
      input.addEventListener("change", () => {
        if (input.checked) {
          storeValue(architectureStorageKey, input.value);
          updateCatalogLinks(input.value);
        }
      });
    }
    const themeSelector = document.getElementById("theme-select");
    if (themeSelector) {
      themeSelector.value = themePreference;
      themeSelector.closest(".theme-control").hidden = false;
      themeSelector.addEventListener("change", () => {
        themePreference = themeSelector.value;
        storeValue(themeStorageKey, themePreference);
        applyTheme();
      });
    }
    for (const button of document.querySelectorAll("[data-copy-target]")) button.hidden = false;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeControls, { once: true });
  } else {
    initializeControls();
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return;
      } catch {
        // Selection copying also supports browsers without clipboard API access.
      }
    }
    const focusedElement = document.activeElement;
    const selection = document.createElement("textarea");
    selection.value = text;
    selection.setAttribute("readonly", "");
    selection.style.cssText = "position:fixed;left:0;top:0;width:1px;height:1px;opacity:0";
    document.body.appendChild(selection);
    selection.select();
    try {
      if (!document.execCommand("copy")) throw new Error("Clipboard copy failed.");
    } finally {
      selection.remove();
      focusedElement?.focus({ preventScroll: true });
    }
  }

  document.addEventListener("click", async (event) => {
    const architectureLink = event.target.closest?.("a[data-architecture-select]");
    if (architectureLink && supportedArchitectures.includes(architectureLink.dataset.architectureSelect)) {
      storeValue(architectureStorageKey, architectureLink.dataset.architectureSelect);
      return;
    }
    const languageLink = event.target.closest?.("a[data-language]");
    if (languageLink && supportedLanguages.includes(languageLink.dataset.language)) {
      storeValue(languageStorageKey, languageLink.dataset.language);
      return;
    }
    const button = event.target.closest?.("[data-copy-target]");
    if (!button || button.dataset.copyPending === "true") return;
    const content = document.getElementById(button.dataset.copyTarget);
    const status = document.getElementById("copy-status");
    const label = button.querySelector("[data-copy-label]");
    if (!content || !status || !label) return;
    clearTimeout(copyResetTimers.get(button));
    activeCopyButton = button;
    button.dataset.copyPending = "true";
    button.setAttribute("aria-busy", "true");
    status.textContent = "";
    try {
      await copyText(content.textContent);
      status.textContent = documentSettings.copySuccess;
      label.textContent = documentSettings.copiedLabel;
    } catch {
      status.textContent = documentSettings.copyFailure;
      label.textContent = documentSettings.copyLabel;
    } finally {
      delete button.dataset.copyPending;
      button.removeAttribute("aria-busy");
      copyResetTimers.set(button, setTimeout(() => {
        label.textContent = documentSettings.copyLabel;
        if (activeCopyButton === button) {
          status.textContent = "";
          activeCopyButton = null;
        }
      }, 4000));
    }
  });
})();
