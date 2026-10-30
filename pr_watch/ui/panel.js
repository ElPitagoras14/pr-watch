// Panel: dibuja el modelo de vista que manda Python y reenvia las acciones.
// No decide nada: etiquetas, colores, orden y avisos llegan ya resueltos.
"use strict";

(function () {
  const { api, relative, el } = window.prw;
  let current = null;

  function $(id) {
    return document.getElementById(id);
  }

  function reportHeight() {
    // El alto del contenido, no el de la ventana: si no, nunca encogeria.
    const h = Math.ceil($("panel").getBoundingClientRect().height);
    api().content_height(h);
  }

  function renderAccount(rows) {
    $("account").replaceChildren(
      ...rows.map((r) =>
        el(
          "div",
          { class: "kv" },
          el("span", { class: "k" }, r.label),
          el("span", { class: "v" + (r.tone ? " tone-" + r.tone : ""), title: r.value }, r.value),
        ),
      ),
    );
  }

  function renderNotice(n) {
    if (!n) {
      $("notice").replaceChildren();
      return;
    }
    const action = n.action
      ? el("a", { onclick: () => api().open_settings() }, n.action.label)
      : null;
    $("notice").replaceChildren(el("div", { class: "notice tone-" + n.tone }, n.text, action));
  }

  function renderRow(r) {
    return el(
      "div",
      {
        class: "row" + (r.unseen ? " unseen" : ""),
        title: r.hover,
        onclick: () => api().open_url(r.url),
      },
      el(
        "div",
        { class: "t" },
        el(
          "span",
          { class: "title" },
          el("span", { class: "dot tone-" + r.tone }),
          r.ref + " " + r.title,
        ),
        el("span", { class: "label tone-" + r.tone }, r.label),
      ),
      el("div", { class: "s" }, r.sub),
    );
  }

  function renderBlocks(vm) {
    const out = [];
    if (vm.empty) {
      out.push(el("hr"), el("div", { class: "empty" }, vm.empty));
    }
    for (const b of vm.blocks) {
      out.push(
        el("hr"),
        el(
          "div",
          { class: "sec" },
          el("span", {}, b.title + " · " + b.total),
          el("a", { onclick: () => api().open_url(b.link.url) }, b.link.label),
        ),
        ...b.rows.map(renderRow),
      );
    }
    $("blocks").replaceChildren(...out);
  }

  function renderFooter() {
    if (!current) return;
    const f = current.footer;
    $("updated").textContent =
      f.updated_at === null
        ? f.updated_text
        : (function () {
            const rel = relative(Date.now() - f.updated_at);
            return rel === "justo ahora" ? "Actualizado justo ahora" : "Actualizado " + rel;
          })();
    $("version").textContent = f.version;
  }

  function render(vm) {
    current = vm;
    $("title").textContent = vm.title;
    const pin = $("btn-pin");
    pin.classList.toggle("on", !!vm.pinned);
    pin.title = vm.pinned
      ? "Fijado: no se oculta al perder el foco"
      : "Fijar para que no se oculte";
    renderAccount(vm.account);
    renderNotice(vm.notice);
    renderBlocks(vm);
    renderFooter();
    requestAnimationFrame(reportHeight);
  }

  window.render = render;

  $("btn-refresh").addEventListener("click", () => api().refresh());
  $("btn-settings").addEventListener("click", () => api().open_settings());
  $("btn-pin").addEventListener("click", () => api().toggle_pin());
  $("btn-close").addEventListener("click", () => api().hide());
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") api().hide();
  });
  window.addEventListener("blur", () => api().blur());

  // El pie dice cuanto hace: se refresca solo mientras el panel esta abierto.
  setInterval(renderFooter, 10000);

  window.addEventListener("pywebviewready", () => api().ready());

  window.prw.loadScenario().then((sc) => {
    if (sc) render(sc.panel);
  });
})();
