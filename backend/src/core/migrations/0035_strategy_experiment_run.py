"""
0035 — Registro append-only de las ejecuciones del generador (G8).

Sin este registro, el número de configuraciones probadas sobre un activo se
perdía al terminar cada ejecución: solo sobrevivían las estrategias que
salieron bien. Eso subestima la multiplicidad y, con ella, la deflación del
Sharpe — el sesgo de selección clásico.

Se guarda una fila por ejecución (no por genoma): un preset profundo evalúa
miles de specs y la reoptimización nocturna corre sobre muchos activos, así que
por genoma serían millones de filas al mes. El dato de gobernanza —cuántas
pruebas lleva este activo— se conserva sumando `evaluations`.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0034_live_order_manual_audit"),
    ]

    operations = [
        migrations.CreateModel(
            name="StrategyExperimentRun",
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
                ("asset_symbol", models.CharField(db_index=True, max_length=20)),
                ("interval", models.CharField(default="1d", max_length=10)),
                ("seed", models.IntegerField(blank=True, null=True)),
                ("preset", models.CharField(blank=True, default="", max_length=20)),
                (
                    "optimizer",
                    models.CharField(blank=True, default="single", max_length=10),
                ),
                (
                    "catalog_version",
                    models.CharField(blank=True, default="", max_length=32),
                ),
                ("candles", models.PositiveIntegerField(default=0)),
                ("data_start", models.DateTimeField(blank=True, null=True)),
                ("data_end", models.DateTimeField(blank=True, null=True)),
                ("evaluations", models.PositiveIntegerField(default=0)),
                ("effective_trials", models.PositiveIntegerField(default=0)),
                ("expected_max_sharpe", models.FloatField(blank=True, null=True)),
                ("candidates_gated", models.PositiveIntegerField(default=0)),
                ("passed_gating", models.PositiveIntegerField(default=0)),
                ("best_fitness", models.FloatField(blank=True, null=True)),
                ("best_deflated_sharpe", models.FloatField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "asset",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="experiment_runs",
                        to="core.cryptoasset",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ejecución del generador (registro)",
                "verbose_name_plural": "Ejecuciones del generador (registro)",
                "db_table": "strategy_experiment_runs",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["asset_symbol", "interval", "-created_at"],
                        name="strategy_ex_asset_s_318508_idx",
                    )
                ],
            },
        ),
    ]
