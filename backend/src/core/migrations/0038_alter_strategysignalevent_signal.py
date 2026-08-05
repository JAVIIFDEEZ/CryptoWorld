"""
Las señales dejan de ser dos.

Una estrategia corta emite SHORT (abrir) y COVER (cerrar). Meterlas en el molde
BUY/SELL no era una simplificación: SELL significa cerrar un largo, o sea justo
lo contrario de abrir un corto, y el historial de señales del usuario habría
registrado la operación invertida.

Solo cambia `choices`, así que no toca la columna: `max_length=8` ya daba de
sobra para las dos palabras nuevas.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0037_chain_metric_points"),
    ]

    operations = [
        migrations.AlterField(
            model_name="strategysignalevent",
            name="signal",
            field=models.CharField(
                choices=[
                    ("BUY", "Compra"),
                    ("SELL", "Venta"),
                    ("SHORT", "Apertura en corto"),
                    ("COVER", "Cierre de corto"),
                ],
                max_length=8,
            ),
        ),
    ]
