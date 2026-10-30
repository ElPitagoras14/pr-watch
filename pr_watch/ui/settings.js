// Ajustes: primero la forja, despues el token y despues el ambito elegido de
// una lista. El token guardado nunca llega aqui; solo se sabe si existe.
"use strict";

(function () {
  const { api, el } = window.prw;
  const $ = (id) => document.getElementById(id);
  const MANUAL = "__manual__";

  let vm = null;
  let tokenOk = false; // el token (escrito o guardado) paso el paso 1
  let verified = false; // el ambito elegido paso el paso 2
  let busy = false;
  let check = 0; // descarta respuestas de comprobaciones ya superadas

  // La forja seleccionada en la ventana, que puede no ser la activa todavia.
  function forge() {
    return { provider: $("provider").value, host: $("host").value.trim() };
  }

  // Como se describe la forja seleccionada: ambito, permisos, sustantivo.
  function card() {
    const sel = $("provider").value;
    return (vm.providers || []).find((p) => p.value === sel) || {};
  }

  function forgeChanged() {
    const f = forge();
    if (f.provider !== vm.provider) return true;
    return !!card().needs_host && f.host !== vm.host;
  }

  function currentScope() {
    const sel = $("scope-select");
    if (sel.value === MANUAL) return $("scope-manual").value.trim();
    return sel.value || "";
  }

  function credentialChanged() {
    return $("token").value.trim() !== "" || currentScope() !== vm.scope || forgeChanged();
  }

  function refresh() {
    const needsVerify = credentialChanged() || !vm.has_token;
    $("btn-save").disabled = busy || (needsVerify && !verified) || currentScope() === "";
    $("btn-verify").disabled = busy;
    $("scope-select").disabled = busy || !tokenOk;
    $("scope-manual").disabled = busy || !tokenOk;
    $("scope-manual").hidden = $("scope-select").value !== MANUAL;
    $("host-field").hidden = !card().needs_host;
  }

  function setStatus(id, text, tone) {
    const node = $(id);
    node.textContent = text || "";
    node.className = "status" + (tone ? " tone-" + tone : "");
  }

  function errorText(r) {
    const forja = card().label || "la forja";
    const ambito = (card().scope_label || "ámbito").toLowerCase();
    return (
      {
        invalid: forja + " rechazó el token: hay que renovarlo.",
        scope: "Sin acceso al " + ambito + ": " + (r.message || "") + ".",
        network: "No se pudo conectar con " + forja + ": " + (r.message || "red") + ".",
        rate: "Límite de peticiones agotado; inténtalo más tarde.",
      }[r.kind] ||
      r.message ||
      "No se pudo verificar."
    );
  }

  // scopes: [{value, label}]. El ambito personal llega primero, como
  // `user:<login>`; el resto son organizaciones o grupos.
  function fillScopes(scopes, preferred, preferredLabel) {
    const sel = $("scope-select");
    const list = scopes.slice();
    if (preferred && !list.some((s) => s.value === preferred)) {
      list.push({ value: preferred, label: preferredLabel || preferred });
    }
    const vacio = list.length ? "Elige " + (card().scope_label || "ámbito").toLowerCase() : "—";
    const opts = [el("option", { value: "" }, vacio)];
    for (const s of list) opts.push(el("option", { value: s.value }, s.label));
    opts.push(el("option", { value: MANUAL }, "Otro (escribir a mano)…"));
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

  // Las etiquetas salen de la forja seleccionada, no de la activa: elegir
  // GitLab en el desplegable ya cambia los textos, sin guardar nada.
  function applyCard() {
    const c = card();
    $("scope-label").textContent = c.scope_label || "Ámbito";
    $("scope-manual").placeholder = c.scope_placeholder || "";
    $("perms").textContent = (c.permissions || []).join(", ");
    $("per-block-label").textContent = "Máximo de " + (c.noun || "PR") + " por bloque";
    $("create-token").textContent = "Crear token en " + (c.label || "la forja");
  }

  // Cambiar de forja invalida lo verificado: otro servidor, otro token.
  function forgeSwitched() {
    check++;
    busy = false;
    resetScope();
    applyCard();
    setStatus("verify-status", "");
    setStatus("save-status", "");
    refresh();
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
    const f = forge();
    const r = (await api().settings_verify_token(f, token)) || {};
    if (id !== check) return;
    busy = false;
    if (token !== $("token").value.trim()) {
      setStatus("verify-status", "");
      refresh();
      return;
    }
    if (!r.ok) {
      // Que aun no haya token para esa forja no es un error que pintar.
      if (r.missing) {
        setStatus("verify-status", "");
        $("token").focus();
      } else {
        setStatus("verify-status", errorText(r), "red");
      }
      refresh();
      return;
    }
    tokenOk = true;
    setStatus("verify-status", "Conectado como " + r.login, "green");
    const scopes = r.scopes || [];
    // Antes de reescribir la lista, lo que el usuario ya tuviera elegido.
    const mismaForja = !forgeChanged();
    const preferred = currentScope() || (mismaForja ? vm.scope : "");
    fillScopes(scopes, preferred, preferred === vm.scope ? vm.scope_display : "");
    const propios = scopes.filter((s) => !s.value.startsWith("user:"));
    if (propios.length === 0) {
      setStatus(
        "scope-status",
        "El token no ve ningún " +
          (card().scope_label || "ámbito").toLowerCase() +
          ": elige tu espacio personal o escríbelo con «Otro…».",
        "amber",
      );
    }
    refresh();
    if (currentScope()) verifyScope();
    else $("scope-select").focus();
  }

  // ---- paso 2: el ambito ----

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
    const r = (await api().settings_verify(forge(), scope, token)) || {};
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

  function fillProviders() {
    const sel = $("provider");
    sel.replaceChildren(
      ...(vm.providers || []).map((p) => el("option", { value: p.value }, p.label)),
    );
    sel.value = vm.provider;
  }

  function fill(data) {
    vm = data;
    check++;
    busy = false;
    fillProviders();
    $("host").value = vm.host || "";
    applyCard();
    $("token").value = "";
    $("token").placeholder = vm.has_token
      ? "Guardado · escribe uno nuevo para cambiarlo"
      : "Pega aquí el token";
    $("interval").value = vm.poll_interval_secs;
    $("interval").min = vm.min_interval_secs;
    $("per-block").value = vm.max_per_block;
    $("per-block").min = vm.min_per_block;
    $("per-block").max = vm.max_per_block_limit;
    $("notifications").checked = !!vm.notifications;
    $("logout-line").style.display = vm.has_token ? "" : "none";
    $("create-token").hidden = !vm.has_create_token_url;
    $("plaintext").replaceChildren(
      vm.plaintext_warning ? el("div", { class: "warn" }, vm.plaintext_warning) : "",
    );
    setStatus("verify-status", "");
    setStatus("save-status", "");
    $("notes").textContent = "";
    resetScope();
    // Con el ambito configurado pero sin lista todavia, se muestra solo.
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
    const f = forge();
    const r =
      (await api().settings_save({
        provider: f.provider,
        host: f.host,
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

  $("provider").addEventListener("change", () => {
    forgeSwitched();
    verifyToken(); // por si esa forja ya tiene token guardado
  });
  $("host").addEventListener("input", forgeSwitched);
  $("host").addEventListener("change", () => {
    forgeSwitched();
    if ($("host").value.trim()) verifyToken();
  });
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
    clampNumber(
      "interval",
      vm.min_interval_secs,
      86400,
      (c) => "El intervalo mínimo es " + vm.min_interval_secs + " s; se usa " + c + ".",
    ),
  );
  $("per-block").addEventListener("change", () =>
    clampNumber(
      "per-block",
      vm.min_per_block,
      vm.max_per_block_limit,
      (c) =>
        "El tope va de " + vm.min_per_block + " a " + vm.max_per_block_limit + "; se usa " + c + ".",
    ),
  );
  $("btn-verify").addEventListener("click", verifyToken);
  $("btn-save").addEventListener("click", save);
  $("btn-cancel").addEventListener("click", () => api().settings_close());
  $("btn-close").addEventListener("click", () => api().settings_close());
  $("btn-logout").addEventListener("click", logout);
  // La URL la construye Python desde la forja seleccionada: desde aqui no
  // sale ninguna direccion.
  $("create-token").addEventListener("click", () => api().open_create_token(forge()));
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
