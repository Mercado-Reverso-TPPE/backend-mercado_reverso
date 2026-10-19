import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("anuncios", "0003_raio_por_localizacao_de_referencia"),
        ("negociacao", "0001_initial"),
        ("ofertas", "0002_oferta_catalogo_buscas_y_eventos"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notificacao",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tipo", models.CharField(max_length=40)),
                ("titulo", models.CharField(max_length=160)),
                ("mensagem", models.TextField(max_length=2000)),
                ("agrupamento", models.CharField(blank=True, max_length=100)),
                ("criada_em", models.DateTimeField(auto_now_add=True)),
                ("lida_em", models.DateTimeField(blank=True, null=True)),
                ("anuncio", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="notificacoes",
                    to="anuncios.anuncio",
                )),
                ("negociacao", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="notificacoes",
                    to="negociacao.negociacao",
                )),
                ("oferta", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="notificacoes",
                    to="ofertas.oferta",
                )),
                ("usuario", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="notificacoes",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ("-criada_em",)},
        ),
        migrations.AddIndex(
            model_name="notificacao",
            index=models.Index(
                fields=["usuario", "lida_em", "-criada_em"],
                name="notificacao_usuario_leitura_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="notificacao",
            index=models.Index(
                fields=["usuario", "agrupamento"],
                name="notificacao_agrupamento_idx",
            ),
        ),
        migrations.CreateModel(
            name="PreferenciaNotificacao",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("tipo", models.CharField(max_length=40)),
                ("canal", models.CharField(
                    choices=[("aplicativo", "Aplicativo"), ("email", "E-mail")],
                    max_length=12,
                )),
                ("habilitada", models.BooleanField(default=True)),
                ("atualizada_em", models.DateTimeField(auto_now=True)),
                ("usuario", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="preferencias_notificacao",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="preferencianotificacao",
            constraint=models.UniqueConstraint(
                fields=("usuario", "tipo", "canal"),
                name="preferencia_notificacao_unica",
            ),
        ),
        migrations.AddConstraint(
            model_name="preferencianotificacao",
            constraint=models.CheckConstraint(
                condition=~Q(tipo="seguranca_conta") | Q(habilitada=True),
                name="avisos_seguranca_nao_desativaveis",
            ),
        ),
    ]
