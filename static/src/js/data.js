/** @odoo-module **/

$(document).ready(() => {
  const dashboard = document.querySelector(".pmant-dashboard");
  const menuToggle = document.querySelector(".pmant-menu-toggle");
  if (dashboard && menuToggle) {
    menuToggle.addEventListener("click", () => dashboard.classList.toggle("menu-open"));
    dashboard.querySelectorAll(".pmant-nav a").forEach((link) => {
      link.addEventListener("click", () => dashboard.classList.remove("menu-open"));
    });
  }

  const boton = document.getElementById("enviar_medicion");
  if (boton) {
    boton.addEventListener("click", async function () {
      const data = {
        equipo_id: document.getElementById("equipo_id").value,
        uso_promedio: document.getElementById("uso_promedio").value,
        temperatura: document.getElementById("temperatura").value,
        presion: document.getElementById("presion").value,
        tem_ambiente: document.getElementById("tem_ambiente").value,
      };

      if (
        !data.equipo_id ||
        !data.uso_promedio ||
        !data.temperatura ||
        !data.presion ||
        !data.tem_ambiente
      ) {
        mostrarNotificacion("notificacion-error");
        return;
      }

      try {
        const response = await fetch("/guardar/medicion/equipo", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params: data,
            id: Date.now(),
          }),
        });

        const result = await response.json();
        if (result.result?.success) {
          mostrarNotificacion("notificacion-exito");
        } else {
          mostrarNotificacion("notificacion-error");
        }
      } catch (error) {
        console.error("Error al enviar datos:", error);
        mostrarNotificacion("notificacion-error");
      }
    });
  }

  function mostrarNotificacion(id) {
    const noti = document.getElementById(id);
    if (noti) {
      noti.style.display = "block";
      setTimeout(() => {
        noti.style.display = "none";
        window.location.reload();
      }, 3000);
    }
  }

  const portalMain = document.querySelector(".pmant-page-rail ~ .main");
  if (portalMain) {
    let searchTimer;
    const applyEquipmentView = (mode) => {
      const tableMode = mode === "table";
      document.querySelectorAll(".pmant-page-rail ~ .main .main-equipos, .pmant-page-rail ~ .main .main_historail_pmant, .pmant-page-rail ~ .main .pmant-quote-list").forEach((container) => {
        container.classList.toggle("pmant-table-view", tableMode);
      });
      document.querySelectorAll("[data-pmant-view]").forEach((button) => {
        button.classList.toggle("active", button.dataset.pmantView === mode);
      });
    };

    const restoreEquipmentView = () => {
      applyEquipmentView(window.localStorage.getItem("pmant-equipment-view") || "cards");
      const path = window.location.pathname;
      document.querySelectorAll(".pmant-page-rail .pmant-nav a").forEach((link) => link.classList.remove("active"));
      let selector = 'a[href="/my/sedes"]';
      if (path.includes("/servicios/")) selector = 'a[href="/my/servicios/ejecucion"]';
      else if (path.includes("/equipos/") || path.match(/\/my\/\d+\/equipos/)) selector = '.pmant-nav a:nth-child(2)';
      else if (path.includes("/sede/") || path.includes("/area/")) selector = '.pmant-nav a:nth-child(4)';
      document.querySelector(`.pmant-page-rail ${selector}`)?.classList.add("active");
    };

    restoreEquipmentView();

    const ajaxNavigate = async (url, pushState = true) => {
      document.body.classList.add("pmant-page-loading");
      try {
        const response = await fetch(url, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });
        if (!response.ok || response.redirected) {
          window.location.assign(response.url || url);
          return;
        }
        const html = await response.text();
        const nextDocument = new DOMParser().parseFromString(html, "text/html");
        const nextMain = nextDocument.querySelector(".pmant-page-rail ~ .main");
        if (!nextMain) {
          window.location.assign(url);
          return;
        }
        document.querySelector(".pmant-page-rail ~ .main").replaceWith(nextMain);
        document.title = nextDocument.title || document.title;
        if (pushState) window.history.pushState({ pmant: true }, "", url);
        restoreEquipmentView();
        syncWhatsAppLinks();
        syncServiceFormButtons();
        window.scrollTo({ top: 0, behavior: "smooth" });
      } catch (error) {
        console.warn("Navegación AJAX no disponible; se usará navegación normal.", error);
        window.location.assign(url);
      } finally {
        document.body.classList.remove("pmant-page-loading");
      }
    };

    document.addEventListener("click", (event) => {
      const viewButton = event.target.closest("[data-pmant-view]");
      if (viewButton) {
        const mode = viewButton.dataset.pmantView;
        window.localStorage.setItem("pmant-equipment-view", mode);
        applyEquipmentView(mode);
        return;
      }
      const link = event.target.closest(".pmant-page-rail a, .pmant-page-rail ~ .main a");
      if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || link.target || link.hasAttribute("download")) return;
      const url = new URL(link.href, window.location.href);
      const isPortalPage = url.origin === window.location.origin && url.pathname.startsWith("/my/") && !url.pathname.startsWith("/my/sedes");
      if (!isPortalPage) return;
      event.preventDefault();
      ajaxNavigate(url.href);
    });

    document.addEventListener("submit", (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement) || form.method.toLowerCase() !== "get" || !form.closest(".pmant-page-rail ~ .main")) return;
      event.preventDefault();
      const url = new URL(form.action || window.location.href, window.location.href);
      url.search = new URLSearchParams(new FormData(form)).toString();
      ajaxNavigate(url.href);
    });

    document.addEventListener("input", (event) => {
      const input = event.target;
      const form = input.closest?.("form");
      if (!form || form.method.toLowerCase() !== "get" || !["search", "filtro"].includes(input.name)) return;
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => {
        const url = new URL(form.action || window.location.href, window.location.href);
        url.search = new URLSearchParams(new FormData(form)).toString();
        ajaxNavigate(url.href);
      }, 320);
    });

    window.addEventListener("popstate", () => window.location.reload());
  }

  const dashboardSearch = document.querySelector(".pmant-dashboard .pmant-search input");
  if (dashboardSearch) {
    let dashboardSearchTimer;
    dashboardSearch.addEventListener("input", () => {
      window.clearTimeout(dashboardSearchTimer);
      dashboardSearchTimer = window.setTimeout(() => dashboardSearch.form.requestSubmit(), 350);
    });
  }

  function syncWhatsAppLinks() {
    const supportLink = document.querySelector(".pmant-whatsapp-support");
    if (!supportLink) return;
    document.querySelectorAll('a[href="/contactus"]').forEach((link) => {
      link.href = supportLink.href;
      link.target = "_blank";
      link.rel = "noopener";
    });
  }
  syncWhatsAppLinks();

  function syncServiceFormButtons() {
    document.querySelectorAll('[data-bs-target="#exampleModal"]').forEach((button) => {
      button.innerHTML = '<i class="fa fa-file-text-o"></i> Formulario de Servicios';
      button.setAttribute("aria-label", "Abrir Formulario de Servicios");
    });
  }
  syncServiceFormButtons();

  document.addEventListener("click", (event) => {
    const serviceButton = event.target.closest('[data-bs-target="#exampleModal"]');
    if (!serviceButton || document.getElementById("exampleModal")) return;
    const match = window.location.pathname.match(/\/my\/equipo\/(\d+)\//);
    if (!match) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    window.location.assign(`/my/equipos/${match[1]}/detalles?open_service=1`);
  }, true);

  if (new URLSearchParams(window.location.search).get("open_service") === "1") {
    const serviceModal = document.getElementById("Model_Solicitud");
    if (serviceModal && window.bootstrap?.Modal) window.bootstrap.Modal.getOrCreateInstance(serviceModal).show();
  }
});
