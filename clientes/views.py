from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.decorators import cajero_o_admin_required
from .forms import ClienteForm
from .models import Cliente


@login_required
@cajero_o_admin_required
def cliente_list(request):
    clientes_qs = Cliente.objects.all().order_by('cliente_id')
    paginator = Paginator(clientes_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(
        request,
        'clientes/clientes.html',
        {
            'clientes': page_obj,
            'page_obj': page_obj,
        },
    )


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
            except Exception as e:
                error_msg = f'Error al registrar el cliente: {e}'
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
            except Exception as e:
                error_msg = f'Error al actualizar el cliente: {e}'
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


