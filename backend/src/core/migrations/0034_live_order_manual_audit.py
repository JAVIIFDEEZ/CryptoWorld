"""
0034 — La auditoría de órdenes reales pasa a cubrir también las manuales.

Hasta ahora `LiveOrderRecord` solo existía para la promoción paper→real, y por
eso colgaba obligatoriamente de una `PaperTradingAccount`. Las órdenes lanzadas
a mano contra el exchange real no dejaban ningún rastro auditable.

Cambios:
  · `owner` — dueño de la orden, clave de consulta canónica. Se rellena desde
    `account.owner` para todo lo ya registrado.
  · `account` pasa a ser opcional: una orden manual no nace de ninguna cartera.
  · `source` — distingue `mirror` (promoción) de `manual`. Lo existente es, por
    definición, `mirror`.
  · `order_type` y `client_order_id` — tipo de orden y clave de idempotencia,
    con restricción única por dueño para que dos peticiones simultáneas no
    puedan enviar dos veces la misma orden real.
  · nuevo estado `pending` — el intento se reserva ANTES de llamar al exchange,
    de modo que sea la restricción única de la base de datos, y no una
    comprobación en memoria, la que arbitre las peticiones concurrentes.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_owner(apps, schema_editor):
    """Rellena `owner` desde la cartera de paper de cada registro histórico."""
    LiveOrderRecord = apps.get_model("core", "LiveOrderRecord")
    PaperTradingAccount = apps.get_model("core", "PaperTradingAccount")

    LiveOrderRecord.objects.filter(owner__isnull=True, account__isnull=False).update(
        owner_id=models.Subquery(
            PaperTradingAccount.objects
            .filter(pk=models.OuterRef("account_id"))
            .values("owner_id")[:1]
        )
    )


def noop(apps, schema_editor):
    """Marcha atrás: `owner` desaparece con la columna, no hay nada que revertir."""


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0033_quantalert_quantalertfiring"),
    ]

    operations = [
        migrations.AddField(
            model_name="liveorderrecord",
            name="owner",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="live_orders",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="liveorderrecord",
            name="source",
            field=models.CharField(
                choices=[("mirror", "Promoción paper→real"), ("manual", "Orden manual")],
                db_index=True, default="mirror", max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="liveorderrecord",
            name="order_type",
            field=models.CharField(default="market", max_length=10),
        ),
        migrations.AddField(
            model_name="liveorderrecord",
            name="client_order_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        # `pending` reserva el intento antes de llamar al exchange, para que la
        # restricción de idempotencia se aplique antes de mover dinero.
        migrations.AlterField(
            model_name="liveorderrecord",
            name="status",
            field=models.CharField(
                choices=[("pending", "En curso"), ("sent", "Enviada"),
                         ("failed", "Fallida"), ("blocked", "Bloqueada")],
                db_index=True, max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="liveorderrecord",
            name="account",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="live_orders",
                to="core.papertradingaccount",
            ),
        ),
        migrations.RunPython(backfill_owner, noop),
        migrations.AddIndex(
            model_name="liveorderrecord",
            index=models.Index(fields=["owner", "-created_at"], name="live_order_owner_created_idx"),
        ),
        migrations.AddConstraint(
            model_name="liveorderrecord",
            constraint=models.UniqueConstraint(
                condition=models.Q(("client_order_id", ""), _negated=True),
                fields=("owner", "client_order_id"),
                name="uniq_live_order_client_id_per_owner",
            ),
        ),
    ]
