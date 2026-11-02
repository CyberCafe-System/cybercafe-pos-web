from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Verifica y convierte todas las tablas de la base de datos MySQL al motor transaccional InnoDB.'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLE STATUS")
            cols = [col[0] for col in cursor.description]
            name_idx = cols.index('Name')
            engine_idx = cols.index('Engine')
            convertidas = 0
            for row in cursor.fetchall():
                table_name = row[name_idx]
                engine = row[engine_idx]
                if engine and engine.upper() != 'INNODB':
                    cursor.execute(f"ALTER TABLE `{table_name}` ENGINE=InnoDB")
                    convertidas += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"Tabla '{table_name}' convertida de {engine} a InnoDB.")
                    )
            if convertidas == 0:
                self.stdout.write(
                    self.style.SUCCESS("Todas las tablas ya utilizan el motor transaccional InnoDB.")
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"Total de tablas convertidas a InnoDB: {convertidas}")
                )

