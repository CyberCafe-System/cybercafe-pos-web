# CyberCafe POS Web

Frontend web del sistema de gestión integral para Cybercafé.

Este proyecto corresponde al panel administrativo y punto de venta (POS) del sistema. Será la interfaz principal utilizada por el personal del local para registrar ventas, controlar el inventario y gestionar la renta de computadoras.

El frontend web está desarrollado con tecnologías web estándar, sin frameworks complejos ni PHP, y consume la API REST central construida en Django.

---

## Tecnologías utilizadas

- HTML5
- CSS3
- JavaScript vanilla
- Fetch API para peticiones HTTP al backend
- Git / GitHub

---

## Requisitos

Antes de trabajar en el proyecto, se recomienda contar con:

- Un navegador moderno: Google Chrome, Firefox o Edge
- Un editor de código, como Visual Studio Code
- La extensión Live Server instalada en VS Code
- Git instalado
- Acceso al repositorio del proyecto

---

## 1. Inicialización del proyecto

Dado que este proyecto no utiliza un entorno de servidor pesado como Node.js o PHP, la inicialización consiste en clonar el repositorio y crear la estructura base de carpetas.

Desde la terminal:

```bash
git clone https://github.com/CyberCafe-System/cybercafe-pos-web.git
cd cybercafe-pos-web
```

---

## 2. Estructura del proyecto

Se recomienda utilizar una estructura modular basada en carpetas para separar la estructura (HTML), el diseño (CSS) y la lógica (JavaScript).

```text
cybercafe-pos-web/
│
├── index.html           # Archivo principal (Login / estructura base)
├── pos.html             # Interfaz del punto de venta (cajero)
├── admin.html           # Interfaz del panel administrativo
│
├── css/
│   ├── styles.css       # Estilos globales
│   ├── pos.css          # Estilos específicos del POS
│   └── admin.css        # Estilos del panel de administración
│
├── js/
│   ├── api.js           # Lógica central para comunicarse con Django
│   ├── auth.js          # Manejo de JWT (login, logout y validación)
│   ├── pos.js           # Lógica de ventas y rentas
│   └── admin.js         # Lógica de CRUD (inventario, usuarios, equipos)
│
├── assets/
│   ├── img/             # Imágenes y logos
│   └── icons/           # Íconos de la interfaz
│
├── .gitignore
├── README.md
└── .vscode/
```

Esta estructura permite mantener el código ordenado y facilitar su mantenimiento. Al separar los archivos JS según su función, evitamos tener un único archivo gigante difícil de mantener.

---

## 3. Organización de las vistas y lógica

### Archivos HTML

Serán los encargados de estructurar la información. En lugar de usar PHP para crear vistas dinámicas, se utilizará HTML estático y JavaScript para rellenar los datos, como la lista de productos o equipos, solicitándolos al backend.

### js/api.js

Contiene la URL base del backend y funciones reutilizables.

```javascript
const API_BASE_URL = "http://127.0.0.1:8000/api";
```

### js/auth.js

Se encargará de capturar el usuario y la contraseña, enviarlos al backend y guardar el token JWT en `localStorage`. Este token se enviará en cada solicitud posterior para demostrar que el usuario tiene acceso.

---

## 4. Roles y permisos en la web

El sistema web limitará las opciones visibles según el rol del usuario que inicie sesión:

- **Administrador:** Tendrá acceso a `admin.html` y podrá administrar usuarios, registrar equipos, gestionar el inventario completo, establecer tarifas de renta y generar reportes de ventas.
- **Cajero:** Tendrá acceso exclusivo a `pos.html`. Sus funciones principales son la atención al cliente, el registro de ventas y la asignación de computadoras.

> El rol de **Asistente** operará exclusivamente desde la aplicación móvil en Flutter, por lo que no tendrá una interfaz principal en este repositorio.

---

## 5. Módulo POS (punto de venta)

La interfaz principal para el cajero (`pos.html`) se dividirá en dos pestañas principales:

1. **Venta de productos:** Permite registrar comidas, bebidas y postres, mostrando cantidad y precio unitario. Calcula el subtotal y el total, descontando el stock automáticamente al completar la venta y permitiendo generar un ticket.
2. **Renta de equipos:** Muestra las computadoras y consolas disponibles, permite registrar la hora de inicio, el tiempo contratado y el costo. Si un equipo tiene disponibilidad parcial, mostrará una advertencia visual.

---

## 6. Ejecutar el entorno de desarrollo

Al no usar frameworks de JavaScript ni procesadores de backend como PHP, la ejecución es directa:

1. Abre la carpeta `cybercafe-pos-web` en Visual Studio Code.
2. Abre el archivo `index.html`.
3. Haz clic derecho sobre el archivo y selecciona **Open with Live Server**.
4. El navegador se abrirá automáticamente en una dirección local, por ejemplo: `http://127.0.0.1:5500/index.html`

> Para que el sistema web funcione completamente, el servidor del backend (Django) debe estar ejecutándose al mismo tiempo en el puerto 8000.

---

## 7. Arquitectura de comunicación

El frontend web no se conecta directamente a la base de datos MySQL. Su único canal de comunicación es la API REST.

```text
       Navegador web (cliente)                 Servidor local
 ┌─────────────────────────────────┐      ┌────────────────────────┐
 │                                 │      │                        │
 │  1. HTML/CSS muestra la UI      │      │   Django Backend       │
 │                                 ├─────►│   (Puerto 8000)        │
 │  2. JS hace un fetch() a la API │      │                        │
 │                                 │◄─────┤  Devuelve datos (JSON) │
 │  3. JS actualiza el HTML        │      │                        │
 │     con los datos recibidos     │      └──────────┬─────────────┘
 │                                 │                 │
 └─────────────────────────────────┘                 ▼
                                               Base de datos
                                                  (MySQL)
```

---

## 8. Estado actual del proyecto

Actualmente, el proyecto se encuentra en la etapa inicial de configuración de repositorios.

Se ha establecido:

- La inicialización del repositorio en blanco para el frontend web
- La elección de tecnologías web puras (HTML, CSS y JS) para evitar configuraciones complejas
- La estructura base que acogerá la interfaz del cajero y el administrador

---

## 9. Próximos pasos

El desarrollo web se acoplará a los avances del backend, siguiendo las fases del cronograma:

1. Maquetación de la pantalla de login web y conexión con el endpoint de autenticación JWT.
2. Maquetación de la interfaz web para el cajero (POS de ventas) y lógica de carrito.
3. Creación de la interfaz para el POS de rentas, con cuadrícula de computadoras y motor visual de tiempos.
4. Creación de paneles administrativos para registro de equipos y visualización de reportes.
5. Simulaciones de carga interactuando al mismo tiempo con la app móvil.

---

## Descripción breve

Este repositorio forma parte del sistema integral de Cybercafé y se enfoca en la experiencia web del negocio, priorizando una interfaz clara, funcional y fácil de mantener para las operaciones diarias.

Este es un prompt conceptuyal dispuesto a cambios 