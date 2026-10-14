from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ClienteForm
from .models import Cliente


@login_required
def cliente_list(request):
    clientes = Cliente.objects.all().order_by('cliente_id')
    return render(request, 'clientes/clientes.html', {'clientes': clientes})


@login_required
def cliente_create(request):
    if request.method == 'POST':
        form = ClienteForm(request.POST)
        if form.is_valid():
            form.save()
    return redirect('clientes')


@login_required
def cliente_edit(request):
    if request.method == 'POST':
        cliente = get_object_or_404(Cliente, pk=request.POST.get('cliente_id'))
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
    return redirect('clientes')
