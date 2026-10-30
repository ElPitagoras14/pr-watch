// Comun al panel y a los ajustes: acceso al proceso y modo vista previa.
"use strict";

(function () {
  const params = new URLSearchParams(location.search);

  // En la vista previa no hay pywebview: las llamadas se registran en la
  // consola y devuelven lo que tenga preparado el escenario (D16).
  const previewReplies = {};

  function fakeApi() {
    return new Proxy(
      {},
      {
        get(_target, name) {
          return (...args) => {
            if (name === "content_height") {
              // La pagina de vista previa ajusta el iframe como lo haria la ventana.
              window.parent.postMessage({ type: "content_height", value: args[0] }, "*");
              return Promise.resolve();
            }
            console.log("[vista previa] api." + String(name), ...args);
            return Promise.resolve(previewReplies[name]);
          };
        },
      },
    );
  }

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : fakeApi();
  }

  function relative(ms) {
    const secs = Math.max(0, Math.floor(ms / 1000));
    if (secs < 10) return "justo ahora";
    if (secs < 60) return "hace " + secs + " s";
    const mins = Math.floor(secs / 60);
    if (mins < 60) return "hace " + mins + " min";
    const hours = Math.floor(mins / 60);
    if (hours < 24) return "hace " + hours + " h";
    return "hace " + Math.floor(hours / 24) + " d";
  }

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children) {
      if (c === null || c === undefined) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  // Los glifos Segoe solo existen en Windows.
  if (!/Windows/i.test(navigator.userAgent)) {
    document.documentElement.classList.add("no-segoe");
  }
  if (params.get("theme")) {
    document.documentElement.dataset.theme = params.get("theme");
  }

  async function loadScenario() {
    const name = params.get("preview");
    if (!name) return null;
    const res = await fetch("preview/scenarios.json", { cache: "no-store" });
    const all = await res.json();
    const sc = all[name];
    Object.assign(previewReplies, (sc && sc.replies) || {});
    return sc || null;
  }

  window.prw = { api, relative, el, params, loadScenario, isPreview: !!params.get("preview") };
})();
