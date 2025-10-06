/** @odoo-module **/

$(document).ready(() => {
  const boton = document.getElementById("submit_form_solicitud");
  if (boton) {
    boton.addEventListener("click", async function (e) {
      e.preventDefault();
      boton.disabled = true; // Deshabilitar el botón para evitar múltiples envíos
      boton.textContent = "Enviando...";
      const form = document.querySelector('form[action="/solicitud/mantenimiento/servicio"]');
      const formData = new FormData(form);

      // Validación simple: tipo de servicio y fecha
      if (!formData.get("tipo_servicio") || !formData.get("fecha_servicio")) {
        mostrarNotificacion("notificacion-error", "Por favor completa todos los campos obligatorios.");
        boton.disabled = false;
        boton.textContent = "Enviar Solicitud";
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
            boton.disabled = false;
            boton.textContent = "Enviar Solicitud";
        } else {
          mostrarNotificacion("notificacion-error", "Error en el servidor.");
          boton.disabled = false;
          boton.textContent = "Enviar Solicitud";
        }
      } catch (error) {
        console.error("notificacion-error:", error);
        mostrarNotificacion("notificacion-error", "No se pudo enviar la solicitud.");
        boton.disabled = false;
        boton.textContent = "Enviar Solicitud";

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
