from django.db import migrations, models
from django.db.utils import NotSupportedError


USERNAME_CONSTRAINT = models.UniqueConstraint(
    fields=("username",),
    name="usuarios_username_unique",
)


def add_username_constraint(apps, schema_editor):
    usuario = apps.get_model("usuarios", "Usuario")
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
        if usuario._meta.db_table not in tables:
            raise RuntimeError(
                "La tabla existente 'usuarios' debe estar creada antes de "
                "aplicar esta migración."
            )
        constraints = connection.introspection.get_constraints(
            cursor,
            usuario._meta.db_table,
        )

    if USERNAME_CONSTRAINT.name in constraints or any(
        constraint.get("unique")
        and constraint.get("columns") == ["username"]
        for constraint in constraints.values()
    ):
        return

    if connection.vendor not in ("mysql", "sqlite"):
        raise NotSupportedError(
            "La migración de unicidad de usuarios solo admite MySQL y SQLite."
        )

    quote_name = schema_editor.quote_name
    schema_editor.execute(
        f"CREATE UNIQUE INDEX {quote_name(USERNAME_CONSTRAINT.name)} "
        f"ON {quote_name(usuario._meta.db_table)} "
        f"({quote_name('username')})"
    )


def remove_username_constraint(apps, schema_editor):
    usuario = apps.get_model("usuarios", "Usuario")
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(
            cursor,
            usuario._meta.db_table,
        )

    if USERNAME_CONSTRAINT.name not in constraints:
        return

    quote_name = schema_editor.quote_name
    if connection.vendor == "mysql":
        schema_editor.execute(
            f"DROP INDEX {quote_name(USERNAME_CONSTRAINT.name)} "
            f"ON {quote_name(usuario._meta.db_table)}"
        )
    elif connection.vendor == "sqlite":
        schema_editor.execute(
            f"DROP INDEX {quote_name(USERNAME_CONSTRAINT.name)}"
        )
    else:
        raise NotSupportedError(
            "La reversión de unicidad de usuarios solo admite MySQL y SQLite."
        )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("usuarios", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            add_username_constraint,
            remove_username_constraint,
        ),
    ]
