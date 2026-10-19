from io import BytesIO

from django.utils import timezone
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

COFFEE = colors.HexColor('#6f4e37')
SUAVE = colors.HexColor('#f5f0eb')
GRIS = colors.HexColor('#777777')


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
    nota = ParagraphStyle(
        'nota', parent=styles['Normal'], fontSize=8,
        textColor=GRIS, alignment=TA_CENTER, leading=12,
    )

    elementos = [
        Paragraph(EMPRESA, titulo),
        Paragraph(LEMA, subtitulo),
        Spacer(1, 6 * mm),
    ]

    fecha = timezone.localtime(renta.fecha).strftime('%d/%m/%Y %H:%M')
    cliente = renta.cliente
    nombre_cliente = f'{cliente.nombre} {cliente.apellido}' if cliente else 'Cliente General'
    atendido = renta.usuario.nombre if renta.usuario else 'Sistema'

    info = [
        [
            Paragraph('Factura de Renta', etiqueta), Paragraph(f'#{renta.renta_id:06d}', seccion),
            Paragraph('Fecha', etiqueta), Paragraph(fecha, seccion),
        ],
        [
            Paragraph('Cliente', etiqueta), Paragraph(nombre_cliente, seccion),
            Paragraph('Atendido por', etiqueta), Paragraph(atendido, seccion),
        ],
        [
            Paragraph('Estado de Pago', etiqueta), Paragraph(renta.get_estado_de_pago_display(), seccion),
            Paragraph('', etiqueta), Paragraph('', seccion),
        ],
    ]
    info_tabla = Table(info, colWidths=[28 * mm, 47 * mm, 25 * mm, 45 * mm])
    info_tabla.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, SUAVE),
    ]))
    elementos.append(info_tabla)
    elementos.append(Spacer(1, 6 * mm))

    filas = [[
        'Equipo', 'Inicio', 'Fin', 'T. Contratado',
        'T. Agregado', 'T. Total', 'Tarifa/hr', 'Subtotal',
    ]]
    total = 0
    for detalle in renta.detalles.select_related('equipo'):
        equipo_nom = detalle.equipo.nombre if detalle.equipo else 'Equipo'
        inicio = timezone.localtime(detalle.hora_inicio).strftime('%d/%m/%Y %H:%M') if detalle.hora_inicio else '--'
        fin = timezone.localtime(detalle.hora_fin).strftime('%d/%m/%Y %H:%M') if detalle.hora_fin else '--'
        tiempo_total = (detalle.tiempo_de_renta or 0) + (detalle.tiempo_agregado or 0)
        tarifa = detalle.equipo.tarifa_por_hora if detalle.equipo else 0
        total += detalle.subtotal
        filas.append([
            equipo_nom,
            inicio,
            fin,
            _minutos_a_texto(detalle.tiempo_de_renta),
            _minutos_a_texto(detalle.tiempo_agregado),
            _minutos_a_texto(tiempo_total),
            _money(tarifa),
            _money(detalle.subtotal),
        ])

    items_tabla = Table(
        filas,
        colWidths=[30 * mm, 26 * mm, 26 * mm, 20 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm],
        repeatRows=1,
    )
    items_tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COFFEE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SUAVE]),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
    ]))
    elementos.append(items_tabla)
    elementos.append(Spacer(1, 4 * mm))

    total_tabla = Table([['Total', _money(total)]], colWidths=[40 * mm, 35 * mm], hAlign='RIGHT')
    total_tabla.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEABOVE', (0, 0), (-1, 0), 0.75, COFFEE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (-1, 0), COFFEE),
    ]))
    elementos.append(total_tabla)
    elementos.append(Spacer(1, 8 * mm))
    elementos.append(Paragraph(
        'El equipo queda pendiente de revisión técnica antes de volver a estar disponible.',
        nota,
    ))
    elementos.append(Spacer(1, 2 * mm))
    elementos.append(Paragraph('¡Gracias por su preferencia!', subtitulo))

    doc.build(elementos)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
