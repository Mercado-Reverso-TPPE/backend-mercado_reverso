import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("ofertas", "0002_oferta_catalogo_buscas_y_eventos"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AcaoModeracao",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tipo", models.CharField(
                    choices=[
                        ("denuncia_conversa", "Denúncia de conversa"),
                        ("bloqueio_usuario", "Bloqueio de usuário"),
                    ],
                    max_length=24,
                )),
                ("estado", models.CharField(
                    choices=[
                        ("aberta", "Aberta"),
                        ("resolvida", "Resolvida"),
                        ("descartada", "Descartada"),
                        ("ativa", "Ativa"),
                        ("revogada", "Revogada"),
                    ],
                    max_length=12,
                )),
                ("motivo", models.TextField(blank=True, max_length=2000)),
                ("criada_em", models.DateTimeField(auto_now_add=True)),
                ("atualizada_em", models.DateTimeField(auto_now=True)),
                ("alvo", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="acoes_moderacao_recebidas",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("autor", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="acoes_moderacao_criadas",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("evento", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="acoes_moderacao",
                    to="ofertas.eventonegociacao",
                )),
                ("oferta", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="acoes_moderacao",
                    to="ofertas.oferta",
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="acaomoderacao",
            constraint=models.CheckConstraint(
                condition=~Q(autor=models.F("alvo")),
                name="moderacao_entre_usuarios",
            ),
        ),
        migrations.AddConstraint(
            model_name="acaomoderacao",
            constraint=models.CheckConstraint(
                condition=(
                    Q(tipo="bloqueio_usuario", oferta__isnull=True, evento__isnull=True)
                    | Q(tipo="denuncia_conversa", oferta__isnull=False)
                ),
                name="moderacao_alvo_compativel",
            ),
        ),
        migrations.AddConstraint(
            model_name="acaomoderacao",
            constraint=models.UniqueConstraint(
                condition=Q(tipo="bloqueio_usuario", estado="ativa"),
                fields=("autor", "alvo"),
                name="bloqueio_ativo_unico_por_par",
            ),
        ),
        migrations.AddConstraint(
            model_name="acaomoderacao",
            constraint=models.UniqueConstraint(
                condition=Q(tipo="denuncia_conversa", estado="aberta"),
                fields=("autor", "oferta"),
                name="denuncia_aberta_unica_por_conversa",
            ),
        ),
        migrations.AddIndex(
            model_name="acaomoderacao",
            index=models.Index(
                fields=["tipo", "estado", "-criada_em"],
                name="moderacao_fila_idx",
            ),
        ),
    ]
