/** @odoo-module **/

$(document).ready(() => {
  const boton = document.getElementById("submit_form_solicitud");
  if (boton) {
    boton.addEventListener("click", async function (e) {
      e.preventDefault();

      const form = document.querySelector('form[action="/solicitud/mantenimiento/servicio"]');
      const formData = new FormData(form);

      // Validación simple: tipo de servicio y fecha
      if (!formData.get("tipo_servicio") || !formData.get("fecha_servicio")) {
        mostrarNotificacion("notificacion-error", "Por favor completa todos los campos obligatorios.");
        return;
      }

      try {
        const response = await fetch("/solicitud/mantenimiento/servicio", {
          method: "POST",
          body: formData,
        });
        console.log(response)
        if (response.ok) {
          mostrarNotificacion("notificacion-exito", "Solicitud enviada correctamente.");
        } else {
          mostrarNotificacion("notificacion-error", "Error en el servidor.");
        }
      } catch (error) {
        console.error("notificacion-error:", error);
        mostrarNotificacion("notificacion-error", "No se pudo enviar la solicitud.");
      }
    });
  }

  function mostrarNotificacion(id, mensaje) {
    const noti = document.getElementById(id);
    if (noti) {
      noti.textContent = mensaje;
      noti.style.display = "block";
      setTimeout(() => {
        noti.style.display = "none";
      }, 3000);
    }
  }
});
