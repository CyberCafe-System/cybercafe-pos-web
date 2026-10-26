import os
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    Image,
)

EMPRESA = 'The COFFEE LAN'
LEMA = 'Sistema de Punto de Venta'

# Paleta de Colores Institucional
COFFEE = colors.HexColor('#2C1E16')
COBRE = colors.HexColor('#B06B05')
SUAVE = colors.HexColor('#F8F9FA')
GRIS = colors.HexColor('#555555')

LOGO_PATH = 'static/img/logo.png'

def _money(value):
    return f'${value:,.2f}'

def _minutos_a_texto(minutos):
    minutos = int(minutos or 0)
    horas, resto = divmod(minutos, 60)
    if horas and resto:
        return f'{horas} h {resto} min'
    if horas:
        return f'{horas} h'
    return f'{resto} min'

def generar_factura_renta_pdf(renta):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f'Factura de Renta #{renta.renta_id}',
        author=EMPRESA,
    )

    styles = getSampleStyleSheet()
    titulo = ParagraphStyle(
        'titulo', parent=styles['Title'], textColor=COBRE,
        fontSize=24, spaceAfter=2, alignment=TA_LEFT, fontName='Helvetica-Bold'
    )
    subtitulo = ParagraphStyle(
        'subtitulo', parent=styles['Normal'], alignment=TA_LEFT,
        textColor=GRIS, fontSize=11,
    )
    seccion = ParagraphStyle(
        'seccion', parent=styles['Normal'], fontSize=10,
        textColor=colors.HexColor('#222222'), leading=14, fontName='Helvetica-Bold'
    )
    etiqueta = ParagraphStyle(
        'etiqueta', parent=styles['Normal'], fontSize=8,
        textColor=COBRE, fontName='Helvetica-Bold'
    )
    nota = ParagraphStyle(
        'nota', parent=styles['Normal'], fontSize=9,
        textColor=GRIS, alignment=TA_CENTER, leading=12,
    )

    elementos = []

    # ENCABEZADO
    header_data = []
    info_empresa = [Paragraph(EMPRESA, titulo), Paragraph(LEMA, subtitulo)]
    
    if os.path.exists(LOGO_PATH):
        logo = Image(LOGO_PATH, width=35*mm, height=35*mm)
        header_data.append([logo, info_empresa])
        header_table = Table(header_data, colWidths=[45*mm, 120*mm])
    else:
        header_data.append([info_empresa])
        header_table = Table(header_data, colWidths=[165*mm])
        
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
    ]))
    elementos.append(header_table)
    elementos.append(Spacer(1, 8 * mm))

    # INFORMACIÓN DE LA RENTA
    fecha = timezone.localtime(renta.fecha).strftime('%d/%m/%Y %H:%M')
    cliente = renta.cliente
    nombre_cliente = f'{cliente.nombre} {cliente.apellido}' if cliente else 'Cliente General'
    atendido = renta.usuario.nombre if renta.usuario else 'Sistema'

    info = [
        [
            Paragraph('TICKET RENTA N°', etiqueta), Paragraph(f'#{renta.renta_id:06d}', seccion),
            Paragraph('FECHA', etiqueta), Paragraph(fecha, seccion),
        ],
        [
            Paragraph('CLIENTE', etiqueta), Paragraph(nombre_cliente, seccion),
            Paragraph('ATENDIDO POR', etiqueta), Paragraph(atendido, seccion),
        ],
        [
            Paragraph('ESTADO', etiqueta), Paragraph(renta.get_estado_de_pago_display(), seccion),
            Paragraph('', etiqueta), Paragraph('', seccion),
        ],
    ]
    info_tabla = Table(info, colWidths=[35 * mm, 45 * mm, 30 * mm, 55 * mm])
    info_tabla.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,-1), SUAVE),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.white),
    ]))
    elementos.append(info_tabla)
    elementos.append(Spacer(1, 8 * mm))

    # TABLA DE EQUIPOS RENTADOS
    filas = [[
        'Equipo', 'Inicio', 'Fin', 'T. Contratado',
        'T. Agregado', 'T. Total', 'Tarifa/hr', 'Subtotal',
    ]]
    total = 0
    for detalle in renta.detalles.select_related('equipo'):
        equipo_nom = detalle.equipo.nombre if detalle.equipo else 'Equipo'
        inicio = timezone.localtime(detalle.hora_inicio).strftime('%H:%M') if detalle.hora_inicio else '--'
        fin = timezone.localtime(detalle.hora_fin).strftime('%H:%M') if detalle.hora_fin else '--'
        tiempo_total = (detalle.tiempo_de_renta or 0) + (detalle.tiempo_agregado or 0)
        tarifa = detalle.equipo.tarifa_por_hora if detalle.equipo else 0
        total += detalle.subtotal
        filas.append([
            equipo_nom, inicio, fin,
            _minutos_a_texto(detalle.tiempo_de_renta),
            _minutos_a_texto(detalle.tiempo_agregado),
            _minutos_a_texto(tiempo_total),
            _money(tarifa), _money(detalle.subtotal),
        ])

    items_tabla = Table(
        filas,
        colWidths=[28 * mm, 18 * mm, 18 * mm, 24 * mm, 22 * mm, 20 * mm, 18 * mm, 20 * mm],
        repeatRows=1,
    )
    items_tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COFFEE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SUAVE]),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, COBRE),
    ]))
    elementos.append(items_tabla)
    elementos.append(Spacer(1, 6 * mm))

    # TOTAL RENTA
    total_tabla = Table([['TOTAL A PAGAR', _money(total)]], colWidths=[50 * mm, 35 * mm], hAlign='RIGHT')
    total_tabla.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, 0), COFFEE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
    ]))
    elementos.append(total_tabla)
    elementos.append(Spacer(1, 10 * mm))
    
    # PIE DE PÁGINA
    elementos.append(Paragraph('El equipo queda pendiente de revisión técnica antes de volver a estar disponible.', nota))
    elementos.append(Spacer(1, 4 * mm))
    nota_final = ParagraphStyle('nota_final', parent=styles['Normal'], alignment=TA_CENTER, textColor=COBRE, fontName='Helvetica-Bold', fontSize=11)
    elementos.append(Paragraph('¡GRACIAS POR SU PREFERENCIA!', nota_final))

    doc.build(elementos)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf