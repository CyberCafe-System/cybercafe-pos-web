from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

EMPRESA = 'The COFFEE LAN'
LEMA = 'Sistema de Punto de Venta'
IVA_PORCENTAJE = 13

COFFEE = colors.HexColor('#6f4e37')
SUAVE = colors.HexColor('#f5f0eb')
GRIS = colors.HexColor('#777777')


def _money(value):
    return f'${value:,.2f}'


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
        'titulo', parent=styles['Title'], textColor=COFFEE,
        fontSize=22, spaceAfter=0,
    )
    subtitulo = ParagraphStyle(
        'subtitulo', parent=styles['Normal'], alignment=TA_CENTER,
        textColor=GRIS, fontSize=10,
    )
    seccion = ParagraphStyle(
        'seccion', parent=styles['Normal'], fontSize=9,
        textColor=colors.HexColor('#333333'), leading=13,
    )
    etiqueta = ParagraphStyle(
        'etiqueta', parent=styles['Normal'], fontSize=8,
        textColor=colors.HexColor('#999999'),
    )

    elementos = [
        Paragraph(EMPRESA, titulo),
        Paragraph(LEMA, subtitulo),
        Spacer(1, 6 * mm),
    ]

    fecha = venta.fecha.strftime('%d/%m/%Y %H:%M')
    info = [
        [
            Paragraph('Factura', etiqueta), Paragraph(f'#{venta.venta_id:06d}', seccion),
            Paragraph('Fecha', etiqueta), Paragraph(fecha, seccion),
        ],
        [
            Paragraph('Cliente', etiqueta), Paragraph(str(venta.cliente), seccion),
            Paragraph('Atendido por', etiqueta), Paragraph(venta.usuario.nombre, seccion),
        ],
    ]
    info_tabla = Table(info, colWidths=[20 * mm, 55 * mm, 25 * mm, 45 * mm])
    info_tabla.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, SUAVE),
    ]))
    elementos.append(info_tabla)
    elementos.append(Spacer(1, 6 * mm))

    filas = [['Producto', 'Cant.', 'P. Unitario', 'Subtotal']]
    for detalle in venta.detalles.select_related('producto'):
        filas.append([
            detalle.producto.nombre,
            str(detalle.cantidad),
            _money(detalle.precio_unitario),
            _money(detalle.subtotal),
        ])
    items_tabla = Table(filas, colWidths=[83 * mm, 20 * mm, 32 * mm, 32 * mm], repeatRows=1)
    items_tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COFFEE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SUAVE]),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
    ]))
    elementos.append(items_tabla)
    elementos.append(Spacer(1, 4 * mm))

    totales = [
        ['Subtotal', _money(venta.subtotal)],
        [f'IVA ({IVA_PORCENTAJE}%)', _money(venta.iva)],
        ['Total', _money(venta.total)],
    ]
    total_tabla = Table(totales, colWidths=[40 * mm, 35 * mm], hAlign='RIGHT')
    total_tabla.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEABOVE', (0, 2), (-1, 2), 0.75, COFFEE),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 2), (-1, 2), COFFEE),
        ('FONTSIZE', (0, 2), (-1, 2), 12),
    ]))
    elementos.append(total_tabla)
    elementos.append(Spacer(1, 10 * mm))
    elementos.append(Paragraph('¡Gracias por su compra!', subtitulo))

    doc.build(elementos)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
