# Generated manually — 2026-06-11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_two_factor_recovery_codes"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="pending_email",
            field=models.EmailField(
                blank=True,
                help_text=(
                    "Nueva dirección solicitada por el usuario, a la espera de "
                    "confirmación. Solo sustituye a email cuando el usuario "
                    "verifica el enlace enviado a la nueva dirección."
                ),
                max_length=254,
                null=True,
            ),
        ),
    ]
