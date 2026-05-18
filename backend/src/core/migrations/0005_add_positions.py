# Generated manually — 2026-06-XX

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_add_trade_history_and_price_alerts"),
    ]

    operations = [
        # ── Tabla positions ──────────────────────────────────────────
        migrations.CreateModel(
            name="Position",
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
                    "direction",
                    models.CharField(
                        choices=[("LONG", "Long"), ("SHORT", "Short")],
                        max_length=5,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("OPEN", "Abierta"), ("CLOSED", "Cerrada")],
                        default="OPEN",
                        max_length=6,
                    ),
                ),
                (
                    "label",
                    models.CharField(blank=True, default="", max_length=200),
                ),
                (
                    "avg_entry_price",
                    models.DecimalField(decimal_places=8, default=0, max_digits=20),
                ),
                (
                    "open_quantity",
                    models.DecimalField(decimal_places=18, default=0, max_digits=38),
                ),
                (
                    "initial_quantity",
                    models.DecimalField(decimal_places=18, default=0, max_digits=38),
                ),
                (
                    "realized_pnl",
                    models.DecimalField(decimal_places=8, default=0, max_digits=38),
                ),
                ("opened_at", models.DateTimeField()),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="positions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="positions",
                        to="core.cryptoasset",
                    ),
                ),
            ],
            options={
                "verbose_name": "Posición",
                "verbose_name_plural": "Posiciones",
                "db_table": "positions",
                "ordering": ["-opened_at"],
            },
        ),
        # ── Nuevos campos en trade_history ───────────────────────────
        migrations.AddField(
            model_name="tradehistory",
            name="position",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="trades",
                to="core.position",
            ),
        ),
        migrations.AddField(
            model_name="tradehistory",
            name="trade_intent",
            field=models.CharField(
                blank=True,
                choices=[
                    ("OPEN", "Apertura"),
                    ("ADD", "Ampliación"),
                    ("CLOSE", "Cierre"),
                ],
                max_length=5,
                null=True,
            ),
        ),
    ]
