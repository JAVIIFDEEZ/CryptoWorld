# Generated manually — 2026-05-20

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_add_positions"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserWatchlist",
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
                    "added_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="watchlist_entries",
                        to="core.cryptoasset",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="watchlist_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Watchlist",
                "verbose_name_plural": "Watchlists",
                "db_table": "user_watchlist",
                "ordering": ["-added_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="userwatchlist",
            constraint=models.UniqueConstraint(
                fields=["user", "asset"],
                name="uq_watchlist_user_asset",
            ),
        ),
    ]
