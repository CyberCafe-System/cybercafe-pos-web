from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.decorators import cajero_o_admin_required
from .forms import ClienteForm
from .models import Cliente


@login_required
@cajero_o_admin_required
def cliente_list(request):
    clientes = Cliente.objects.all().order_by('cliente_id')
    return render(request, 'clientes/clientes.html', {'clientes': clientes})


@login_required
@cajero_o_admin_required
def cliente_create(request):
    if request.method == 'POST':
        form = ClienteForm(request.POST)
        if form.is_valid():
            cliente = form.save()
            messages.success(request, f'Cliente {cliente.nombre} {cliente.apellido} registrado exitosamente.')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('clientes')


@login_required
@cajero_o_admin_required
def cliente_edit(request):
    if request.method == 'POST':
        cliente = get_object_or_404(Cliente, pk=request.POST.get('cliente_id'))
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            messages.success(request, f'Cliente {cliente.nombre} {cliente.apellido} actualizado correctamente.')
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text().lstrip('* '))
    return redirect('clientes')

