// Ajustes: primero el token, despues la organizacion elegida de una lista.
// El token guardado nunca llega aqui; solo se sabe si existe.
"use strict";

(function () {
  const { api, el } = window.prw;
  const $ = (id) => document.getElementById(id);
  const MANUAL = "__manual__";

  let vm = null;
  let tokenOk = false; // el token (escrito o guardado) paso el paso 1
  let verified = false; // la organizacion elegida paso el paso 2
  let busy = false;
  let check = 0; // descarta respuestas de comprobaciones ya superadas

  function currentScope() {
    const sel = $("scope-select");
    if (sel.value === MANUAL) return $("scope-manual").value.trim();
    return sel.value || "";
  }

  function credentialChanged() {
    return $("token").value.trim() !== "" || currentScope() !== vm.scope;
  }

  function refresh() {
    const needsVerify = credentialChanged() || !vm.has_token;
    $("btn-save").disabled = busy || (needsVerify && !verified) || currentScope() === "";
    $("btn-verify").disabled = busy || ($("token").value.trim() === "" && !vm.has_token);
    $("scope-select").disabled = busy || !tokenOk;
    $("scope-manual").disabled = busy || !tokenOk;
    $("scope-manual").hidden = $("scope-select").value !== MANUAL;
  }

  function setStatus(id, text, tone) {
    const node = $(id);
    node.textContent = text || "";
    node.className = "status" + (tone ? " tone-" + tone : "");
  }

  function errorText(r) {
    return {
      invalid: "GitHub rechazó el token: hay que renovarlo.",
      scope: "Sin acceso a la organización: " + (r.message || "") +
        ". Revisa el dueño del token o si la organización ya lo aprobó.",
      network: "No se pudo conectar con GitHub: " + (r.message || "red") + ".",
      rate: "Límite de peticiones de GitHub agotado; inténtalo más tarde.",
    }[r.kind] || r.message || "No se pudo verificar.";
  }

  // scopes: [{value, label}]. La cuenta personal llega primero, como
  // `user:<login>`; el resto son organizaciones.
  function fillScopes(scopes, preferred, preferredLabel) {
    const sel = $("scope-select");
    const list = scopes.slice();
    if (preferred && !list.some((s) => s.value === preferred)) {
      list.push({ value: preferred, label: preferredLabel || preferred });
    }
    const opts = [el("option", { value: "" }, list.length ? "Elige cuenta u organización" : "—")];
    for (const s of list) opts.push(el("option", { value: s.value }, s.label));
    opts.push(el("option", { value: MANUAL }, "Otra organización (escribir a mano)…"));
    sel.replaceChildren(...opts);
    sel.value = preferred || "";
  }

  function resetScope() {
    tokenOk = false;
    verified = false;
    fillScopes([], "");
    $("scope-select").value = "";
    $("scope-manual").value = "";
    setStatus("scope-status", "");
  }

  // ---- paso 1: el token ----

  async function verifyToken() {
    const id = ++check;
    busy = true;
    tokenOk = false;
    verified = false;
    refresh();
    setStatus("verify-status", "Comprobando…");
    setStatus("scope-status", "");
    const token = $("token").value.trim();
    const r = (await api().settings_verify_token(token)) || {};
    if (id !== check) return;
    busy = false;
    if (token !== $("token").value.trim()) {
      setStatus("verify-status", "");
      refresh();
      return;
    }
    if (!r.ok) {
      setStatus("verify-status", errorText(r), "red");
      refresh();
      return;
    }
    tokenOk = true;
    setStatus("verify-status", "Conectado como " + r.login, "green");
    const scopes = r.scopes || [];
    // Antes de reescribir la lista, lo que el usuario ya tuviera elegido.
    const preferred = currentScope() || vm.scope;
    fillScopes(scopes, preferred, preferred === vm.scope ? vm.scope_display : "");
    const orgs = scopes.filter((s) => !s.value.startsWith("user:"));
    if (orgs.length === 0) {
      setStatus(
        "scope-status",
        "El token no ve ninguna organización: elige tu cuenta personal o escribe una " +
          "organización con «Otra…».",
        "amber",
      );
    }
    refresh();
    if (currentScope()) verifyScope();
    else $("scope-select").focus();
  }

  // ---- paso 2: la organizacion ----

  async function verifyScope() {
    const scope = currentScope();
    verified = false;
    if (!scope) {
      setStatus("scope-status", "");
      refresh();
      return;
    }
    const id = ++check;
    busy = true;
    refresh();
    setStatus("scope-status", "Comprobando acceso…");
    const token = $("token").value.trim();
    const r = (await api().settings_verify(scope, token)) || {};
    if (id !== check) return;
    busy = false;
    if (scope !== currentScope() || token !== $("token").value.trim()) {
      setStatus("scope-status", "");
      refresh();
      return;
    }
    if (r.ok) {
      verified = true;
      const label = $("scope-select").selectedOptions[0];
      const name = $("scope-select").value === MANUAL || !label ? scope : label.textContent;
      setStatus("scope-status", "Acceso a " + name + " correcto.", "green");
    } else {
      setStatus("scope-status", errorText(r), "red");
    }
    refresh();
  }

  // ---- carga ----

  function fill(data) {
    vm = data;
    check++;
    busy = false;
    $("provider").textContent = vm.provider;
    $("scope-label").textContent = vm.scope_label;
    $("token").value = "";
    $("token").placeholder = vm.has_token
      ? "Guardado · escribe uno nuevo para cambiarlo"
      : "Pega aquí el token";
    $("perms").textContent = vm.permissions.join(", ");
    $("interval").value = vm.poll_interval_secs;
    $("interval").min = vm.min_interval_secs;
    $("per-block").value = vm.max_per_block;
    $("per-block").min = vm.min_per_block;
    $("per-block").max = vm.max_per_block_limit;
    $("notifications").checked = !!vm.notifications;
    $("logout-line").style.display = vm.has_token ? "" : "none";
    $("plaintext").replaceChildren(
      vm.plaintext_warning ? el("div", { class: "warn" }, vm.plaintext_warning) : "",
    );
    setStatus("verify-status", "");
    setStatus("save-status", "");
    $("notes").textContent = "";
    resetScope();
    // Con la organizacion configurada pero sin lista todavia, se muestra sola.
    if (vm.scope) fillScopes([], vm.scope, vm.scope_display);
    refresh();
    if (vm.has_token) verifyToken(); // con lo guardado, sin escribir nada
    else $("token").focus();
  }

  function clampNumber(id, min, max, message) {
    const input = $(id);
    let v = parseInt(input.value, 10);
    if (Number.isNaN(v)) v = min;
    const c = Math.min(Math.max(v, min), max);
    if (c !== v) {
      input.value = c;
      $("notes").textContent = message(c);
    }
  }

  async function save() {
    busy = true;
    refresh();
    setStatus("save-status", "Guardando…");
    const r = (await api().settings_save({
      scope: currentScope(),
      token: $("token").value.trim(),
      poll_interval_secs: parseInt($("interval").value, 10),
      max_per_block: parseInt($("per-block").value, 10),
      notifications: $("notifications").checked,
    })) || {};
    busy = false;
    if (!r.ok) {
      setStatus("save-status", r.error || "No se pudo guardar.", "red");
      refresh();
    }
    // Si se guardo, Python cierra la ventana.
  }

  async function logout() {
    const data = await api().settings_logout();
    fill(data || Object.assign({}, vm, { has_token: false, plaintext_warning: null }));
  }

  $("token").addEventListener("input", () => {
    check++;
    busy = false;
    tokenOk = false;
    verified = false;
    setStatus("verify-status", "");
    setStatus("scope-status", "");
    refresh();
  });
  $("token").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !$("btn-verify").disabled) verifyToken();
  });
  $("scope-select").addEventListener("change", () => {
    refresh();
    if ($("scope-select").value === MANUAL) {
      verified = false;
      setStatus("scope-status", "");
      $("scope-manual").focus();
      refresh();
    } else {
      verifyScope();
    }
  });
  $("scope-manual").addEventListener("input", () => {
    verified = false;
    setStatus("scope-status", "");
    refresh();
  });
  $("scope-manual").addEventListener("change", verifyScope);
  $("scope-manual").addEventListener("keydown", (e) => {
    if (e.key === "Enter") verifyScope();
  });
  $("interval").addEventListener("change", () =>
    clampNumber("interval", vm.min_interval_secs, 86400,
      (c) => "El intervalo mínimo es " + vm.min_interval_secs + " s; se usa " + c + "."),
  );
  $("per-block").addEventListener("change", () =>
    clampNumber("per-block", vm.min_per_block, vm.max_per_block_limit,
      (c) => "El tope va de " + vm.min_per_block + " a " + vm.max_per_block_limit +
        "; se usa " + c + "."),
  );
  $("btn-verify").addEventListener("click", verifyToken);
  $("btn-save").addEventListener("click", save);
  $("btn-cancel").addEventListener("click", () => api().settings_close());
  $("btn-close").addEventListener("click", () => api().settings_close());
  $("btn-logout").addEventListener("click", logout);
  $("create-token").addEventListener("click", () => api().open_url(vm.create_token_url));
  $("open-config").addEventListener("click", () => api().open_config_file());
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") api().settings_close();
  });

  function reportHeight() {
    api().content_height(Math.ceil($("panel").getBoundingClientRect().height));
  }
  new ResizeObserver(reportHeight).observe($("panel"));

  async function start() {
    const sc = await window.prw.loadScenario();
    fill(sc ? sc.settings : await api().settings_load());
  }

  if (window.prw.isPreview) start();
  else window.addEventListener("pywebviewready", start);
})();
