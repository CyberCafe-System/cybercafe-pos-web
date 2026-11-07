import os
from io import BytesIO
from xml.sax.saxutils import escape as xml_escape

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
IVA_PORCENTAJE = 13

# Paleta de Colores Institucional
COFFEE = colors.HexColor('#2C1E16')
COBRE = colors.HexColor('#B06B05')
SUAVE = colors.HexColor('#F8F9FA')
GRIS = colors.HexColor('#555555')
ROJO = colors.HexColor('#C0392B')

LOGO_PATH = 'static/img/logo.png'


def _money(value):
    if value is None:
        value = 0
    return f'${float(value):,.2f}'


def generar_factura_pdf(venta):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f'Factura #{venta.venta_id}',
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

    elementos = []

    # Banner de Anulación si aplica
    if getattr(venta, 'estado', None) == 'ANULADA':
        anulada_style = ParagraphStyle(
            'anulada_banner', parent=styles['Normal'], fontSize=16,
            textColor=colors.white, alignment=TA_CENTER, fontName='Helvetica-Bold'
        )
        banner_table = Table([[Paragraph('*** FACTURA ANULADA ***', anulada_style)]], colWidths=[165 * mm])
        banner_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), ROJO),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elementos.append(banner_table)
        elementos.append(Spacer(1, 4 * mm))

    # ENCABEZADO CON LOGO
    header_data = []
    info_empresa = [Paragraph(EMPRESA, titulo), Paragraph(LEMA, subtitulo)]

    if os.path.exists(LOGO_PATH):
        try:
            logo = Image(LOGO_PATH, width=35 * mm, height=35 * mm)
            header_data.append([logo, info_empresa])
            header_table = Table(header_data, colWidths=[45 * mm, 120 * mm])
        except Exception:
            header_data.append([info_empresa])
            header_table = Table(header_data, colWidths=[165 * mm])
    else:
        header_data.append([info_empresa])
        header_table = Table(header_data, colWidths=[165 * mm])

    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
    ]))

    elementos.append(header_table)
    elementos.append(Spacer(1, 8 * mm))

    # INFORMACIÓN DE LA FACTURA
    fecha = timezone.localtime(venta.fecha).strftime('%d/%m/%Y %H:%M')
    cliente_txt = xml_escape(str(venta.cliente) if venta.cliente else 'Cliente General')
    cajero_txt = xml_escape(venta.usuario.nombre if venta.usuario else 'Sistema')
    info = [
        [
            Paragraph('FACTURA N°', etiqueta), Paragraph(f'#{venta.venta_id:06d}', seccion),
            Paragraph('FECHA', etiqueta), Paragraph(fecha, seccion),
        ],
        [
            Paragraph('CLIENTE', etiqueta), Paragraph(cliente_txt, seccion),
            Paragraph('ATENDIDO POR', etiqueta), Paragraph(cajero_txt, seccion),
        ],
    ]

    info_tabla = Table(info, colWidths=[25 * mm, 55 * mm, 30 * mm, 55 * mm])
    info_tabla.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, -1), SUAVE),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.white),
    ]))
    elementos.append(info_tabla)
    elementos.append(Spacer(1, 10 * mm))

    # TABLA DE PRODUCTOS
    filas = [['Producto', 'Cant.', 'P. Unitario', 'Subtotal']]
    for detalle in venta.detalles.select_related('producto'):
        filas.append([
            detalle.producto.nombre if detalle.producto else 'Producto',
            str(detalle.cantidad),
            _money(detalle.precio_unitario),
            _money(detalle.subtotal),
        ])
    items_tabla = Table(filas, colWidths=[80 * mm, 20 * mm, 32 * mm, 33 * mm], repeatRows=1)
    items_tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COFFEE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SUAVE]),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, COBRE),
    ]))
    elementos.append(items_tabla)
    elementos.append(Spacer(1, 6 * mm))

    # TOTALES (Incluyendo Efectivo Recibido y Cambio)
    totales = [
        ['Subtotal', _money(venta.subtotal)],
        [f'IVA ({IVA_PORCENTAJE}%)', _money(venta.iva)],
        ['TOTAL A PAGAR', _money(venta.total)],
    ]
    if getattr(venta, 'efectivo_recibido', None) is not None:
        totales.append(['Efectivo Recibido', _money(venta.efectivo_recibido)])
        totales.append(['Cambio', _money(venta.cambio or 0)])

    total_tabla = Table(totales, colWidths=[60 * mm, 40 * mm], hAlign='RIGHT')
    t_styles = [
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TEXTCOLOR', (0, 0), (-1, 1), GRIS),
        ('BACKGROUND', (0, 2), (-1, 2), COFFEE),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.white),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 2), (-1, 2), 13),
        ('TOPPADDING', (0, 2), (-1, 2), 6),
        ('BOTTOMPADDING', (0, 2), (-1, 2), 6),
    ]
    if len(totales) > 3:
        t_styles.extend([
            ('FONTNAME', (0, 3), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 3), (-1, -1), 10),
            ('TEXTCOLOR', (0, 3), (-1, -1), colors.HexColor('#2C1E16')),
            ('LINEABOVE', (0, 3), (-1, 3), 0.5, COBRE),
        ])
    total_tabla.setStyle(TableStyle(t_styles))
    elementos.append(total_tabla)
    elementos.append(Spacer(1, 12 * mm))

    # PIE DE PÁGINA
    nota_final = ParagraphStyle(
        'nota', parent=styles['Normal'], alignment=TA_CENTER,
        textColor=COBRE, fontName='Helvetica-Bold', fontSize=12
    )
    elementos.append(Paragraph('¡GRACIAS POR SU COMPRA!', nota_final))

    doc.build(elementos)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
