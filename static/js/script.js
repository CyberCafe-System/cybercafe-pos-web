/* Inicializacion de eventos al cargar el DOM */
document.addEventListener("DOMContentLoaded", () => {
    
    /* Funcionalidad para colapsar el menu lateral */
    const wrapper = document.getElementById("wrapper");
    const menuToggle = document.getElementById("menu-toggle");

    if (menuToggle && wrapper) {
        menuToggle.addEventListener("click", (e) => {
            e.preventDefault();
            wrapper.classList.toggle("toggled");
        });
    }
});