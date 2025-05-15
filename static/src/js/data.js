/** @odoo-module **/


document
  .getElementById("enviar_medicion")
  .addEventListener("click", async function () {
    const data = {
      equipo_id: document.getElementById("equipo_id").value,
      uso_promedio: document.getElementById("uso_promedio").value,
      temperatura: document.getElementById("temperatura").value,
      presion: document.getElementById("presion").value,
      tem_ambiente: document.getElementById("tem_ambiente").value,
    };
    try {
      const response = await fetch("/guardar/medicion/equipo", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      });

      const result = await response.json();
      if (result.result.success) {
        mostrarNotificacion("notificacion-exito");
      } else {
        mostrarNotificacion("notificacion-error");
      }
    } catch (error) {
      console.error("Error al enviar datos:", error);
      mostrarNotificacion("notificacion-error");
    }
  });

function mostrarNotificacion(id) {
  const noti = document.getElementById(id);
  noti.style.display = "block";
  setTimeout(() => {
    noti.style.display = "none";
    window.location.reload()
  }, 4000);
}
