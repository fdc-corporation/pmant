document.addEventListener("DOMContentLoaded", () => {
  document.addEventListener("click", (event) => {
    console.log(event.target);
    // Verifica si el elemento clickeado tiene la clase 'zoomable-image'
    if (event.target.matches(".zoomable-image")) {
      // Obtiene el `src` de la imagen clickeada
      console.log(event.target);
      const imgSrc = event.target.getAttribute("src");
      console.log("Imagen seleccionada:", imgSrc);

      // Muestra el visor y actualiza la imagen dentro del visor
      const visor = document.querySelector(".visor-imagen");
      const visorImg = visor.querySelector("img");

      visorImg.src = imgSrc;
      visor.classList.remove("display-none"); // Asegúrate de que el visor esté visible
    }

    // Cierra el visor si haces clic fuera de la imagen
    if (event.target.matches(".visor-imagen")) {
      event.target.classList.add("display-none"); // Oculta el visor
    }
  });
});
