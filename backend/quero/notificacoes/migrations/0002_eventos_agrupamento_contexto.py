import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("notificacoes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificacao",
            name="contexto",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddConstraint(
            model_name="notificacao",
            constraint=models.UniqueConstraint(
                condition=Q(agrupamento__gt=""),
                fields=("usuario", "agrupamento"),
                name="notificacao_agrupamento_unico",
            ),
        ),
        migrations.CreateModel(
            name="EventoNotificacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chave_evento", models.CharField(max_length=180)),
                ("contexto", models.JSONField(blank=True, default=dict)),
                ("criada_em", models.DateTimeField(auto_now_add=True)),
                (
                    "notificacao",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="eventos",
                        to="notificacoes.notificacao",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="eventos_notificacao",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("criada_em", "pk")},
        ),
        migrations.AddConstraint(
            model_name="eventonotificacao",
            constraint=models.UniqueConstraint(
                fields=("usuario", "chave_evento"),
                name="evento_notificacao_chave_unica",
            ),
        ),
    ]
