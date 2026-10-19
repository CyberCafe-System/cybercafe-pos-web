import os
import uuid
from PIL import Image, ImageOps
from django.conf import settings
from django.utils.text import slugify


def procesar_imagen_a_webp(archivo, nombre_producto, max_dimension=(600, 600), calidad=85, imagen_anterior=None):
    """
    Convierte cualquier archivo de imagen subido (JPG, PNG, WEBP, etc.) al formato WebP optimizado:
    - Corrige orientación EXIF (típica de fotos tomadas con teléfonos móviles).
    - Preserva transparencia si la imagen tiene canal alfa (RGBA/PNG).
    - Redimensiona proporcionalmente a un tamaño óptimo para catálogo/POS (por defecto max 600x600 px).
    - Comprime a formato WebP moderno de alta eficiencia.
    - Genera un nombre de archivo limpio, seguro y único.
    - Limpia la imagen física previa del disco si se está actualizando el producto.
    Retorna la ruta relativa para el campo `imagen` de la base de datos (ej. 'productos/coca_cola_a1b2c3d4.webp').
    """
    carpeta = settings.MEDIA_ROOT / 'productos'
    carpeta.mkdir(parents=True, exist_ok=True)

    # Abrir la imagen en memoria con Pillow
    img = Image.open(archivo)

    # Corregir rotación EXIF de móviles
    img = ImageOps.exif_transpose(img)

    # Preservar canal alfa si existe transparencia; de lo contrario convertir a RGB
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        img = img.convert('RGBA')
    else:
        img = img.convert('RGB')

    # Redimensionar proporcionalmente con filtro Lanczos de alta nitidez
    img.thumbnail(max_dimension, Image.Resampling.LANCZOS)

    # Nombre seguro y único
    slug_nombre = slugify(nombre_producto) or 'producto'
    sufijo_unico = uuid.uuid4().hex[:8]
    nombre_archivo = f"{slug_nombre}_{sufijo_unico}.webp"
    ruta_destino = carpeta / nombre_archivo

    # Guardar en formato WebP optimizado
    img.save(ruta_destino, format='WEBP', quality=calidad, method=6)

    # Eliminar imagen física anterior si existe y no es la misma
    if imagen_anterior:
        ruta_anterior = settings.MEDIA_ROOT / imagen_anterior
        if ruta_anterior.is_file() and ruta_anterior != ruta_destino:
            try:
                os.remove(ruta_anterior)
            except OSError:
                pass

    return f"productos/{nombre_archivo}"
