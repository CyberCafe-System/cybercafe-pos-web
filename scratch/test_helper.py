import json

def formatear_valor(clave, valor):
    if valor is None:
        return '—'
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    if clave in ('precio_venta', 'precio_compra', 'tarifa', 'total', 'subtotal', 'iva', 'costo'):
        try:
            return f"${float(valor):.2f}"
        except Exception:
            return str(valor)
    if clave == 'rol_id':
        roles = {1: 'Administrador', 2: 'Cajero', 3: 'Asistente'}
        return roles.get(int(valor) if str(valor).isdigit() else valor, f"Rol #{valor}")
    if 'password' in clave.lower():
        return '••••••••'
    return str(valor)

print("Helper defined ok")

