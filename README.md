# CyberCafe POS Web

Este proyecto corresponde al módulo web del sistema de gestión para un cybercafé, orientado a la administración del local, control de ventas y gestión del punto de venta (POS).

La aplicación está desarrollada con Python y Django, y sirve como interfaz web para operaciones administrativas del negocio. A diferencia de la app móvil y la API del backend, este repositorio se centra en la parte del sistema web que puede ejecutarse de forma local para pruebas, gestión y desarrollo de la interfaz del negocio.

---

## Tecnologías utilizadas

- Python 3
- Django 6.1.1
- SQLite (configuración por defecto para desarrollo)
- Django REST Framework
- Simple JWT
- HTML, CSS y JavaScript para la capa visual y front-end
- Git / GitHub

---

## Requisitos previos

Antes de ejecutar este proyecto, asegúrate de tener instalado:

- Python 3.10 o superior
- pip
- virtualenv o venv
- Git
- Visual Studio Code (recomendado)

---

## Estructura del proyecto

```text
cybercafe-pos-web/
├── config/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── pos_app/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── migrations/
│   ├── models.py
│   ├── tests.py
│   └── views.py
├── templates/
│   ├── index.html
│   └── pages/
├── static/
│   ├── css/
│   ├── js/
│   └── src/
├── manage.py
├── requirements.txt
├── README.md
└── db.sqlite3
```

### Descripción de carpetas

- `config/`: configuración principal del proyecto Django.
- `pos_app/`: aplicación principal del sistema POS.
- `templates/`: archivos HTML para las vistas del proyecto.
- `static/`: recursos frontend (CSS, JS, imágenes y assets).
- `manage.py`: punto de entrada para ejecutar comandos de Django.

---

## Instalación

1. Clona el repositorio:

```bash
git clone <url-del-repositorio>
cd cybercafe-pos-web
```

2. Crea un entorno virtual:

```bash
python -m venv .venv
```

3. Activa el entorno virtual:

- Windows:

```bash
.venv\Scripts\activate
```

- Linux/macOS:

```bash
source .venv/bin/activate
```

4. Instala las dependencias:

```bash
pip install -r requirements.txt
```

---

## Configuración inicial

Este proyecto ya incluye una configuración base de Django, pero aun se encuentra en desarrollo. Para inicializar la base de datos local:

```bash
python manage.py migrate
```

Si deseas crear un usuario administrador para pruebas:

```bash
python manage.py createsuperuser
```

---

## Ejecutar la aplicación

Inicia el servidor local de desarrollo:

```bash
python manage.py runserver
```

Luego abre la siguiente dirección en el navegador:

```text
http://127.0.0.1:8000/
```

Para acceder al panel administrativo de Django:

```text
http://127.0.0.1:8000/admin/
```

---

## Estado actual del proyecto

Este repositorio se encuentra en una fase inicial de construcción. Actualmente incluye la base del proyecto Django con:

- configuración principal del proyecto
- estructura de app `pos_app`
- archivos estáticos y templates base
- dependencias iniciales del entorno

Todavía falta implementar gran parte de la lógica del negocio, como:

- autenticación de usuarios
- panel de control del POS
- gestión de ventas
- administración de inventario
- control de equipos y horarios de renta
- conexión con el backend central o API del sistema

---

## Objetivos del módulo web

El módulo web del cybercafé tiene como finalidad:

- gestionar ventas y cobros del local
- controlar productos y servicios ofrecidos
- supervisar el estado de las computadoras y equipos
- visualizar información administrativa del negocio
- ofrecer una interfaz para uso del personal del negocio

---

## Próximos pasos recomendados

1. Definir modelos principales: usuarios, equipos, productos, ventas y alquileres.
2. Crear vistas para login y dashboard administrativo.
3. Diseñar la interfaz del POS para ventas rápidas.
4. Implementar lógica para gestionar inventario y horarios de renta.
5. Conectar el proyecto con la API central del sistema o con la base de datos del negocio.
6. Añadir autenticación y permisos por roles.

---

## Descripción breve

Este repositorio forma parte del sistema integral de Cybercafé y representa la capa web de gestión del negocio. Su objetivo es centralizar la operación administrativa y de ventas para que el personal del local pueda controlar el funcionamiento del establecimiento de forma ordenada y eficiente.

Este proyecto sigue en desarrollo y está preparado para crecer junto con el backend y la aplicación móvil del sistema.

prompt generado para posibles cambios
