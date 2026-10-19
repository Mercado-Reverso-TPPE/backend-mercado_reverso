import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("anuncios", "0003_raio_por_localizacao_de_referencia"),
        ("catalogo", "0001_initial"),
        ("ofertas", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="oferta",
            name="produto",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ofertas",
                to="catalogo.produto",
            ),
        ),
        migrations.AddField(
            model_name="oferta",
            name="nome_produto_snapshot",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="oferta",
            name="foto_produto_snapshot",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="oferta",
            name="status",
            field=models.CharField(
                choices=[
                    ("enviada", "Enviada"),
                    ("em_negociacao", "Em negociação"),
                    ("aceita", "Aceita"),
                    ("recusada", "Recusada"),
                    ("retirada", "Retirada"),
                ],
                default="enviada",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="oferta",
            name="estado_conservacao",
            field=models.CharField(
                choices=[
                    ("novo", "Novo"),
                    ("seminovo", "Seminovo"),
                    ("usado_bom", "Usado — bom estado"),
                    ("usado_marcas", "Usado — com marcas"),
                    ("pecas", "Para peças"),
                ],
                max_length=16,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="oferta",
            name="uma_oferta_ativa_por_vendedor_anuncio",
        ),
        migrations.AddConstraint(
            model_name="oferta",
            constraint=models.UniqueConstraint(
                condition=Q(status__in=("enviada", "em_negociacao", "aceita")),
                fields=("anuncio", "vendedor"),
                name="uma_oferta_ativa_por_vendedor_anuncio",
            ),
        ),
        migrations.AlterField(
            model_name="historicooferta",
            name="status",
            field=models.CharField(
                choices=[
                    ("enviada", "Enviada"),
                    ("em_negociacao", "Em negociação"),
                    ("aceita", "Aceita"),
                    ("recusada", "Recusada"),
                    ("retirada", "Retirada"),
                ],
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="historicooferta",
            name="tipo_evento",
            field=models.CharField(
                choices=[
                    ("enviada", "Oferta enviada"),
                    ("editada", "Oferta editada"),
                    ("retirada", "Oferta retirada"),
                    ("contraproposta", "Contraproposta enviada"),
                    ("contraposta_aceita", "Contraproposta aceita"),
                    ("contraposta_recusada", "Contraproposta recusada"),
                    ("contraproposta_expirada", "Contraproposta expirada"),
                    ("aceita", "Oferta aceita"),
                    ("recusada", "Oferta recusada"),
                    ("mensagem", "Mensagem"),
                ],
                default="enviada",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="historicooferta",
            name="justificativa",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="historicooferta",
            name="texto",
            field=models.TextField(blank=True, max_length=5000),
        ),
        migrations.AddField(
            model_name="historicooferta",
            name="rodada",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="historicooferta",
            name="expira_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicooferta",
            name="respondida_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicooferta",
            name="lida_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicooferta",
            name="resultado",
            field=models.CharField(
                choices=[
                    ("pendente", "Pendente"),
                    ("aceita", "Aceita"),
                    ("recusada", "Recusada"),
                    ("expirada", "Expirada"),
                    ("substituida", "Substituída"),
                ],
                blank=True,
                max_length=12,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="historicooferta",
            name="preco",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddConstraint(
            model_name="historicooferta",
            constraint=models.CheckConstraint(
                condition=~Q(tipo_evento="contraproposta") | Q(expira_em__isnull=False),
                name="contraproposta_com_prazo",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicooferta",
            constraint=models.CheckConstraint(
                condition=~Q(tipo_evento="mensagem") | ~Q(texto=""),
                name="mensagem_negociacao_com_texto",
            ),
        ),
        migrations.AddConstraint(
            model_name="historicooferta",
            constraint=models.UniqueConstraint(
                condition=Q(tipo_evento="contraproposta", respondida_em__isnull=True),
                fields=("oferta",),
                name="uma_contraproposta_aberta_por_oferta",
            ),
        ),
        migrations.AddIndex(
            model_name="historicooferta",
            index=models.Index(fields=["oferta", "rodada"], name="oferta_hist_rodada_idx"),
        ),
        migrations.AddIndex(
            model_name="historicooferta",
            index=models.Index(fields=["tipo_evento", "expira_em"], name="oferta_hist_expira_idx"),
        ),
        migrations.AlterModelOptions(
            name="historicooferta",
            options={"ordering": ("registrado_em", "pk")},
        ),
        migrations.RenameModel(
            old_name="HistoricoOferta",
            new_name="EventoNegociacao",
        ),
        migrations.AlterField(
            model_name="eventonegociacao",
            name="autor",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="eventos_negociacao",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="eventonegociacao",
            name="oferta",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="eventos",
                to="ofertas.oferta",
            ),
        ),
        migrations.CreateModel(
            name="BuscaSalva",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("nome", models.CharField(max_length=100)),
                ("termo", models.CharField(blank=True, max_length=160)),
                ("preco_min", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("preco_max", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("distancia_max_km", models.PositiveIntegerField(blank=True, null=True)),
                ("ordenacao", models.CharField(
                    choices=[
                        ("distancia", "Distância"),
                        ("recentes", "Mais recentes"),
                        ("preco_minimo", "Menor orçamento"),
                        ("preco_maximo", "Maior orçamento"),
                    ],
                    default="distancia",
                    max_length=16,
                )),
                ("criada_em", models.DateTimeField(auto_now_add=True)),
                ("atualizada_em", models.DateTimeField(auto_now=True)),
                ("categoria", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="buscas_salvas",
                    to="anuncios.categoria",
                )),
                ("usuario", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="buscas_salvas",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="buscasalva",
            constraint=models.UniqueConstraint(
                fields=("usuario", "nome"),
                name="busca_salva_nome_por_usuario",
            ),
        ),
        migrations.AddConstraint(
            model_name="buscasalva",
            constraint=models.CheckConstraint(
                condition=Q(preco_min__isnull=True)
                | Q(preco_max__isnull=True)
                | Q(preco_min__lte=models.F("preco_max")),
                name="busca_salva_faixa_preco_valida",
            ),
        ),
        migrations.AddIndex(
            model_name="buscasalva",
            index=models.Index(fields=["usuario", "-atualizada_em"], name="busca_salva_usuario_idx"),
        ),
    ]
