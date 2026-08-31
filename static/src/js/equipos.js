/** @odoo-module **/

$(document).ready(() => {
  const form = document.querySelector('form[action="/solicitud/mantenimiento/servicio"]');
  if (!form) return;

  const button = form.querySelector('[type="submit"]');
  const notify = (id, message) => {
    const element = document.getElementById(id);
    if (!element) return;
    element.textContent = message;
    element.style.display = "block";
    window.setTimeout(() => { element.style.display = "none"; }, 4000);
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    if (button) {
      button.disabled = true;
      button.dataset.originalText = button.textContent;
      button.textContent = "Enviando solicitud…";
    }

    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const payload = await response.json();
      if (!response.ok || !payload.result?.success) throw new Error("Solicitud rechazada");
      notify("notificacion-exito", "Solicitud enviada correctamente. Redirigiendo…");
      window.setTimeout(() => window.location.assign(payload.result.redirect_url), 650);
    } catch (error) {
      notify("notificacion-error", "No se pudo enviar la solicitud. Revise los datos e inténtelo nuevamente.");
      if (button) {
        button.disabled = false;
        button.textContent = button.dataset.originalText || "Enviar solicitud";
      }
    }
  });
});
