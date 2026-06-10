# Generated manually — 2026-06-10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_add_watchlist"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="preferred_currency",
            field=models.CharField(
                choices=[
                    ("usd", "Dólar Estadounidense (USD)"),
                    ("eur", "Euro (EUR)"),
                    ("gbp", "Libra Esterlina (GBP)"),
                ],
                default="usd",
                help_text="Moneda fiat de referencia para mostrar precios.",
                max_length=3,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="notify_price_alerts",
            field=models.BooleanField(
                default=True,
                help_text="Recibir emails cuando se dispare una alerta de precio.",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="notify_market_digest",
            field=models.BooleanField(
                default=False,
                help_text="Recibir resúmenes periódicos del estado del mercado.",
            ),
        ),
    ]
