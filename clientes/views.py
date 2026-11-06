import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.decorators import admin_required, cajero_o_admin_required
from .forms import ClienteForm
from .models import Cliente

logger = logging.getLogger(__name__)


@login_required
@cajero_o_admin_required
def cliente_list(request):
    query = (request.GET.get('q') or '').strip()
    clientes_qs = Cliente.objects.all().order_by('cliente_id')
    if query:
        clientes_qs = clientes_qs.filter(
            Q(nombre__icontains=query)
            | Q(apellido__icontains=query)
            | Q(dui__icontains=query)
            | Q(telefono__icontains=query)
        )

    paginator = Paginator(clientes_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(
        request,
        'clientes/clientes.html',
        {
            'clientes': page_obj,
            'page_obj': page_obj,
            'query': query,
        },
    )


@login_required
@cajero_o_admin_required
def cliente_buscar_ajax(request):
    """
    Endpoint para autocompletado en el POS y módulo de rentas.
    Devuelve hasta 15 clientes activos que coincidan con nombre, apellido, DUI o teléfono.
    """
    q = (request.GET.get('q') or '').strip()
    if not q or len(q) < 2:
        return JsonResponse({'clientes': []})

    clientes = Cliente.objects.filter(
        Q(nombre__icontains=q)
        | Q(apellido__icontains=q)
        | Q(dui__icontains=q)
        | Q(telefono__icontains=q),
        activo=True,
    )[:15]

    data = [
        {
            'id': c.cliente_id,
            'nombre': f"{c.nombre} {c.apellido}",
            'dui': c.dui,
            'telefono': str(c.telefono),
            'correo': c.correo or '',
        }
        for c in clientes
    ]
    return JsonResponse({'clientes': data})


@login_required
@cajero_o_admin_required
def cliente_create(request):
    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )
    if request.method == 'POST':
        form = ClienteForm(request.POST)
        if form.is_valid():
            try:
                cliente = form.save()
                msg = f'Cliente {cliente.nombre} {cliente.apellido} registrado exitosamente.'
                messages.success(request, msg)
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': msg,
                        'cliente': {
                            'id': cliente.cliente_id,
                            'nombre': cliente.nombre,
                            'apellido': cliente.apellido,
                            'dui': cliente.dui,
                            'telefono': cliente.telefono,
                            'correo': cliente.correo or '',
                            'direccion': cliente.direccion,
                        },
                    })
                return redirect('clientes')
            except Exception:
                logger.exception('Error al registrar el cliente')
                error_msg = 'Ocurrió un error al registrar el cliente. Intenta nuevamente.'
                if is_ajax:
                    return JsonResponse({'success': False, 'errors': {'__all__': [error_msg]}}, status=400)
                messages.error(request, error_msg)
        else:
            if is_ajax:
                errors_dict = {}
                for field, error_list in form.errors.items():
                    errors_dict[field] = [err.strip('* ') for err in error_list]
                return JsonResponse({'success': False, 'errors': errors_dict}, status=400)
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('clientes')


@login_required
@cajero_o_admin_required
def cliente_edit(request):
    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )
    if request.method == 'POST':
        cliente = get_object_or_404(Cliente, pk=request.POST.get('cliente_id'))
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            try:
                cliente = form.save()
                msg = f'Cliente {cliente.nombre} {cliente.apellido} actualizado correctamente.'
                messages.success(request, msg)
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': msg,
                        'cliente': {
                            'id': cliente.cliente_id,
                            'nombre': cliente.nombre,
                            'apellido': cliente.apellido,
                            'dui': cliente.dui,
                            'telefono': cliente.telefono,
                            'correo': cliente.correo or '',
                            'direccion': cliente.direccion,
                        },
                    })
                return redirect('clientes')
            except Exception:
                logger.exception('Error al actualizar el cliente')
                error_msg = 'Ocurrió un error al actualizar el cliente. Intenta nuevamente.'
                if is_ajax:
                    return JsonResponse({'success': False, 'errors': {'__all__': [error_msg]}}, status=400)
                messages.error(request, error_msg)
        else:
            if is_ajax:
                errors_dict = {}
                for field, error_list in form.errors.items():
                    errors_dict[field] = [err.strip('* ') for err in error_list]
                return JsonResponse({'success': False, 'errors': errors_dict}, status=400)
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('clientes')


@login_required
@admin_required
def cliente_toggle(request):
    """Baja lógica y reactivación de clientes por parte del Administrador."""
    if request.method == 'POST':
        cliente = get_object_or_404(Cliente, pk=request.POST.get('cliente_id'))
        cliente.activo = not cliente.activo
        cliente.save(update_fields=['activo'])
        estado = "reactivado" if cliente.activo else "desactivado"
        messages.success(request, f'Cliente {cliente.nombre} {cliente.apellido} {estado} correctamente.')
    return redirect('clientes')
