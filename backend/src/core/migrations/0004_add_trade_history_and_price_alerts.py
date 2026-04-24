# Generated manually — 2026-04-24

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_add_portfolio_and_expand_market_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="TradeHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "trade_type",
                    models.CharField(
                        choices=[("BUY", "Compra"), ("SELL", "Venta")],
                        max_length=4,
                    ),
                ),
                (
                    "quantity",
                    models.DecimalField(decimal_places=18, max_digits=38),
                ),
                (
                    "price_usd",
                    models.DecimalField(decimal_places=8, max_digits=20),
                ),
                (
                    "total_usd",
                    models.DecimalField(decimal_places=8, max_digits=38),
                ),
                (
                    "notes",
                    models.CharField(blank=True, default="", max_length=500),
                ),
                ("executed_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trades",
                        to="core.cryptoasset",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trades",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Operación",
                "verbose_name_plural": "Historial de Operaciones",
                "db_table": "trade_history",
                "ordering": ["-executed_at"],
            },
        ),
        migrations.CreateModel(
            name="PriceAlert",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "condition",
                    models.CharField(
                        choices=[("ABOVE", "Por encima de"), ("BELOW", "Por debajo de")],
                        max_length=5,
                    ),
                ),
                (
                    "threshold_price",
                    models.DecimalField(decimal_places=8, max_digits=20),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("is_triggered", models.BooleanField(default=False)),
                ("triggered_at", models.DateTimeField(blank=True, null=True)),
                (
                    "notes",
                    models.CharField(blank=True, default="", max_length=500),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_alerts",
                        to="core.cryptoasset",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_alerts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Alerta de Precio",
                "verbose_name_plural": "Alertas de Precio",
                "db_table": "price_alerts",
                "ordering": ["-created_at"],
            },
        ),
    ]
