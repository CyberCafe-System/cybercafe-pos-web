import logging
from decimal import Decimal
from django.core.mail import EmailMultiAlternatives, get_connection
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

REMITENTE_DEFAULT = 'The COFFEE LAN <thecoffeelan@gmail.com>'


def _obtener_conexion_email():
    """
    Retorna la conexión de correo configurada.
    Si el servidor Django no ha sido reiniciado tras editar el .env, lee directamente
    el archivo .env para obtener EMAIL_HOST_PASSWORD en tiempo real.
    """
    import os
    from pathlib import Path

    password = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or os.environ.get('EMAIL_HOST_PASSWORD', '')
    
    if not password:
        env_path = getattr(settings, 'BASE_DIR', Path('.')) / '.env'
        if env_path.exists():
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('EMAIL_HOST_PASSWORD='):
                            val = line.split('=', 1)[1].strip().strip('"').strip("'")
                            if val:
                                password = val
                                os.environ['EMAIL_HOST_PASSWORD'] = password
                                setattr(settings, 'EMAIL_HOST_PASSWORD', password)
                                break
            except Exception as e:
                logger.warning("No se pudo leer .env dinámicamente: %s", e)

    backend = getattr(settings, 'EMAIL_BACKEND', '') or 'django.core.mail.backends.smtp.EmailBackend'
    
    if not password and ('smtp' in backend.lower()):
        return get_connection('django.core.mail.backends.console.EmailBackend'), True
    
    return get_connection(
        backend=backend,
        host=getattr(settings, 'EMAIL_HOST', 'smtp.gmail.com'),
        port=getattr(settings, 'EMAIL_PORT', 587),
        username=getattr(settings, 'EMAIL_HOST_USER', 'thecoffeelan@gmail.com'),
        password=password,
        use_tls=getattr(settings, 'EMAIL_USE_TLS', True),
        use_ssl=getattr(settings, 'EMAIL_USE_SSL', False)
    ), False


def enviar_factura_venta_correo(venta, destinatario_email=None):
    """
    Envía la factura en PDF de una venta POS al correo del cliente desde thecoffeelan@gmail.com.
    Retorna: (bool_exito, str_mensaje)
    """
    try:
        from pos_app.ticket import generar_factura_pdf
        
        cliente = venta.cliente
        email_destino = (destinatario_email or (cliente.correo if cliente else '')).strip()
        
        if not email_destino:
            return False, "El cliente no tiene un correo electrónico registrado."
        
        # 1. Generar archivo PDF adjunto
        pdf_bytes = generar_factura_pdf(venta)
        nombre_adjunto = f"Factura_Venta_V-{venta.venta_id}.pdf"
        
        # 2. Datos para el cuerpo
        nombre_cliente = f"{cliente.nombre} {cliente.apellido}" if cliente else "Estimado/a Cliente"
        fecha_str = timezone.localtime(venta.fecha).strftime('%d/%m/%Y %I:%M %p')
        cajero_str = venta.usuario.username if venta.usuario else "Sistema"
        total_str = f"${venta.total:,.2f}"
        subtotal_str = f"${venta.subtotal:,.2f}"
        iva_str = f"${venta.iva:,.2f}"
        
        detalles_html = ""
        detalles_txt = ""
        for det in venta.detalles.all():
            prod_nom = det.producto.nombre if det.producto else "Producto"
            cant = det.cantidad
            pu = f"${det.precio_unitario:,.2f}"
            st = f"${det.subtotal:,.2f}"
            detalles_html += f"""
            <tr>
                <td style="padding: 8px 12px; border-bottom: 1px solid #f0e6dd; color: #2C1E16;">{prod_nom}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #f0e6dd; text-align: center; color: #555;">{cant}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #f0e6dd; text-align: right; color: #555;">{pu}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #f0e6dd; text-align: right; font-weight: bold; color: #6F4E37;">{st}</td>
            </tr>
            """
            detalles_txt += f"  - {cant}x {prod_nom} ({pu} c/u) = {st}\n"

        # 3. Asunto y cuerpo en texto plano
        asunto = f"Factura de Compra #{venta.venta_id} - The COFFEE LAN"
        texto_plano = f"""
Hola, {nombre_cliente}.

¡Gracias por tu compra en The COFFEE LAN!
Adjunto a este correo encontrarás tu factura digital en formato PDF correspondiente al ticket #V-{venta.venta_id}.

Resumen de la Venta:
------------------------------------------
Ticket: #V-{venta.venta_id}
Fecha: {fecha_str}
Atendido por: {cajero_str}

Artículos:
{detalles_txt}
------------------------------------------
Subtotal: {subtotal_str}
IVA (13%): {iva_str}
TOTAL: {total_str}

The COFFEE LAN - El mejor café y la mejor conexión.
thecoffeelan@gmail.com
"""

        # 4. Cuerpo en HTML elegante
        html_contenido = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f7f4ef; margin: 0; padding: 20px; }}
                .card {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.06); }}
                .header {{ background-color: #2C1E16; padding: 30px 25px; text-align: center; color: #ffffff; }}
                .header h1 {{ margin: 0; font-size: 24px; letter-spacing: 1px; color: #ffffff; }}
                .header p {{ margin: 6px 0 0 0; color: #ffd89b; font-size: 13px; }}
                .body-content {{ padding: 30px 25px; color: #333333; }}
                .greeting {{ font-size: 18px; font-weight: bold; color: #2C1E16; margin-bottom: 10px; }}
                .info-box {{ background-color: #faf6f0; border-left: 4px solid #6F4E37; padding: 12px 16px; border-radius: 8px; margin: 18px 0; font-size: 13px; color: #555; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; }}
                th {{ background-color: #6F4E37; color: #ffffff; padding: 10px 12px; text-align: left; font-weight: 600; }}
                th.text-center {{ text-align: center; }}
                th.text-right {{ text-align: right; }}
                .totales-table {{ width: 100%; margin-top: 10px; }}
                .totales-table td {{ padding: 6px 12px; text-align: right; }}
                .total-destacado {{ font-size: 18px; font-weight: bold; color: #28a745; }}
                .adjunto-notice {{ background-color: #e8f4fd; border: 1px solid #b6e0fe; border-radius: 8px; padding: 12px; margin-top: 25px; text-align: center; font-size: 13px; color: #084298; }}
                .footer {{ background-color: #f1ede7; padding: 20px; text-align: center; font-size: 12px; color: #888888; border-top: 1px solid #e5dec9; }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="header">
                    <h1>☕ The COFFEE LAN</h1>
                    <p>Sistema de Facturación Electrónica</p>
                </div>
                <div class="body-content">
                    <div class="greeting">¡Hola, {nombre_cliente}!</div>
                    <p style="color: #666; font-size: 14px; line-height: 1.5;">
                        Gracias por tu visita y tu compra. Adjuntamos en este correo tu factura oficial en formato <strong>PDF</strong>.
                    </p>
                    
                    <div class="info-box">
                        <strong>Ticket:</strong> #V-{venta.venta_id} &nbsp;|&nbsp; 
                        <strong>Fecha:</strong> {fecha_str} &nbsp;|&nbsp; 
                        <strong>Atendido por:</strong> {cajero_str}
                    </div>

                    <table>
                        <thead>
                            <tr>
                                <th>Producto</th>
                                <th class="text-center">Cant.</th>
                                <th class="text-right">Precio</th>
                                <th class="text-right">Subtotal</th>
                            </tr>
                        </thead>
                        <tbody>
                            {detalles_html}
                        </tbody>
                    </table>

                    <table class="totales-table">
                        <tr>
                            <td style="color: #777;">Subtotal:</td>
                            <td style="width: 120px; font-weight: bold;">{subtotal_str}</td>
                        </tr>
                        <tr>
                            <td style="color: #777;">IVA (13%):</td>
                            <td style="width: 120px; font-weight: bold;">{iva_str}</td>
                        </tr>
                        <tr style="border-top: 2px solid #6F4E37;">
                            <td style="font-size: 16px; font-weight: bold; color: #2C1E16;">TOTAL PAGADO:</td>
                            <td class="total-destacado">{total_str}</td>
                        </tr>
                    </table>

                    <div class="adjunto-notice">
                        📎 <strong>Archivo Adjunto:</strong> Hemos anexado tu factura <code>{nombre_adjunto}</code> lista para descargar o imprimir.
                    </div>
                </div>
                <div class="footer">
                    <p style="margin: 0 0 5px 0;"><strong>The COFFEE LAN</strong> - El mejor café y la mejor conexión</p>
                    <p style="margin: 0;">Enviado desde: <a href="mailto:thecoffeelan@gmail.com" style="color: #6F4E37; text-decoration: none;">thecoffeelan@gmail.com</a></p>
                </div>
            </div>
        </body>
        </html>
        """

        # 5. Envío
        conexion, es_simulado = _obtener_conexion_email()
        msg = EmailMultiAlternatives(
            subject=asunto,
            body=texto_plano,
            from_email=REMITENTE_DEFAULT,
            to=[email_destino],
            connection=conexion
        )
        msg.attach_alternative(html_contenido, "text/html")
        msg.attach(nombre_adjunto, pdf_bytes, 'application/pdf')
        msg.send(fail_silently=False)

        if es_simulado:
            return False, "La configuración de correo no está activa. No se pudo enviar el mensaje."
        
        return True, f"Factura enviada exitosamente a {email_destino}."

    except Exception as e:
        logger.exception("Error al enviar factura por correo: %s", e)
        return False, "Ocurrió un error al enviar el correo. Inténtalo de nuevo más tarde."


def enviar_factura_renta_correo(renta, destinatario_email=None):
    """
    Envía el comprobante en PDF de una renta de equipo al correo del cliente desde thecoffeelan@gmail.com.
    Retorna: (bool_exito, str_mensaje)
    """
    try:
        from rentas.ticket import generar_factura_renta_pdf
        
        cliente = renta.cliente
        email_destino = (destinatario_email or (cliente.correo if cliente else '')).strip()
        
        if not email_destino:
            return False, "El cliente no tiene un correo electrónico registrado."
        
        # 1. Generar archivo PDF adjunto
        pdf_bytes = generar_factura_renta_pdf(renta)
        nombre_adjunto = f"Comprobante_Renta_R-{renta.renta_id}.pdf"
        
        # 2. Datos para el cuerpo
        nombre_cliente = f"{cliente.nombre} {cliente.apellido}" if cliente else "Estimado/a Cliente"
        fecha_str = timezone.localtime(renta.fecha).strftime('%d/%m/%Y %I:%M %p')
        cajero_str = renta.usuario.username if renta.usuario else "Sistema"
        total_str = f"${renta.total:,.2f}"
        
        detalles_html = ""
        detalles_txt = ""
        for det in renta.detalles.all():
            eq_nom = det.equipo.nombre if det.equipo else "Equipo"
            eq_tipo = det.equipo.get_tipo_display() if det.equipo else "Sesión"
            mins = (det.tiempo_de_renta or 0) + (det.tiempo_agregado or 0)
            st = f"${det.subtotal:,.2f}"
            detalles_html += f"""
            <tr>
                <td style="padding: 10px 12px; border-bottom: 1px solid #f0e6dd; color: #2C1E16; font-weight: 500;">
                    {eq_nom} <span style="font-size: 11px; background: #e9ecef; padding: 2px 6px; border-radius: 4px; margin-left: 6px;">{eq_tipo}</span>
                </td>
                <td style="padding: 10px 12px; border-bottom: 1px solid #f0e6dd; text-align: center; color: #555;">{mins} minutos</td>
                <td style="padding: 10px 12px; border-bottom: 1px solid #f0e6dd; text-align: right; font-weight: bold; color: #6F4E37;">{st}</td>
            </tr>
            """
            detalles_txt += f"  - {eq_nom} ({mins} min) = {st}\n"

        asunto = f"Comprobante de Renta #{renta.renta_id} - The COFFEE LAN"
        texto_plano = f"""
Hola, {nombre_cliente}.

¡Gracias por utilizar nuestras instalaciones en The COFFEE LAN!
Adjunto a este correo encontrarás el comprobante digital en formato PDF correspondiente a tu sesión de renta #{renta.renta_id}.

Resumen de la Sesión:
------------------------------------------
Ticket de Renta: #R-{renta.renta_id}
Fecha: {fecha_str}
Atendido por: {cajero_str}

Equipos Utilizados:
{detalles_txt}
------------------------------------------
TOTAL PAGADO: {total_str}

The COFFEE LAN - El mejor café y la mejor conexión.
thecoffeelan@gmail.com
"""

        html_contenido = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f7f4ef; margin: 0; padding: 20px; }}
                .card {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.06); }}
                .header {{ background-color: #2C1E16; padding: 30px 25px; text-align: center; color: #ffffff; }}
                .header h1 {{ margin: 0; font-size: 24px; letter-spacing: 1px; color: #ffffff; }}
                .header p {{ margin: 6px 0 0 0; color: #ffd89b; font-size: 13px; }}
                .body-content {{ padding: 30px 25px; color: #333333; }}
                .greeting {{ font-size: 18px; font-weight: bold; color: #2C1E16; margin-bottom: 10px; }}
                .info-box {{ background-color: #faf6f0; border-left: 4px solid #6F4E37; padding: 12px 16px; border-radius: 8px; margin: 18px 0; font-size: 13px; color: #555; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; }}
                th {{ background-color: #6F4E37; color: #ffffff; padding: 10px 12px; text-align: left; font-weight: 600; }}
                th.text-center {{ text-align: center; }}
                th.text-right {{ text-align: right; }}
                .total-destacado {{ font-size: 20px; font-weight: bold; color: #28a745; text-align: right; padding: 12px 0; }}
                .adjunto-notice {{ background-color: #e8f4fd; border: 1px solid #b6e0fe; border-radius: 8px; padding: 12px; margin-top: 25px; text-align: center; font-size: 13px; color: #084298; }}
                .footer {{ background-color: #f1ede7; padding: 20px; text-align: center; font-size: 12px; color: #888888; border-top: 1px solid #e5dec9; }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="header">
                    <h1>☕ The COFFEE LAN</h1>
                    <p>Control y Comprobantes de Renta</p>
                </div>
                <div class="body-content">
                    <div class="greeting">¡Hola, {nombre_cliente}!</div>
                    <p style="color: #666; font-size: 14px; line-height: 1.5;">
                        Esperamos que hayas disfrutado de tu tiempo en <strong>The COFFEE LAN</strong>. Adjuntamos en este correo tu comprobante en formato <strong>PDF</strong>.
                    </p>
                    
                    <div class="info-box">
                        <strong>Comprobante:</strong> #R-{renta.renta_id} &nbsp;|&nbsp; 
                        <strong>Fecha:</strong> {fecha_str} &nbsp;|&nbsp; 
                        <strong>Atendido por:</strong> {cajero_str}
                    </div>

                    <table>
                        <thead>
                            <tr>
                                <th>Equipo / Servicio</th>
                                <th class="text-center">Tiempo Total</th>
                                <th class="text-right">Subtotal</th>
                            </tr>
                        </thead>
                        <tbody>
                            {detalles_html}
                        </tbody>
                    </table>

                    <div style="border-top: 2px solid #6F4E37; margin-top: 10px; display: flex; justify-content: space-between; align-items: center; padding: 10px 0;">
                        <span style="font-size: 16px; font-weight: bold; color: #2C1E16;">TOTAL COBRADO:</span>
                        <span class="total-destacado">{total_str}</span>
                    </div>

                    <div class="adjunto-notice">
                        📎 <strong>Archivo Adjunto:</strong> Hemos anexado tu comprobante <code>{nombre_adjunto}</code> listo para descargar o imprimir.
                    </div>
                </div>
                <div class="footer">
                    <p style="margin: 0 0 5px 0;"><strong>The COFFEE LAN</strong> - El mejor café y la mejor conexión</p>
                    <p style="margin: 0;">Enviado desde: <a href="mailto:thecoffeelan@gmail.com" style="color: #6F4E37; text-decoration: none;">thecoffeelan@gmail.com</a></p>
                </div>
            </div>
        </body>
        </html>
        """

        # 5. Envío
        conexion, es_simulado = _obtener_conexion_email()
        msg = EmailMultiAlternatives(
            subject=asunto,
            body=texto_plano,
            from_email=REMITENTE_DEFAULT,
            to=[email_destino],
            connection=conexion
        )
        msg.attach_alternative(html_contenido, "text/html")
        msg.attach(nombre_adjunto, pdf_bytes, 'application/pdf')
        msg.send(fail_silently=False)

        if es_simulado:
            return False, "La configuración de correo no está activa. No se pudo enviar el mensaje."
        
        return True, f"Comprobante enviado exitosamente a {email_destino}."

    except Exception as e:
        logger.exception("Error al enviar comprobante de renta por correo: %s", e)
        return False, "Ocurrió un error al enviar el correo. Inténtalo de nuevo más tarde."
