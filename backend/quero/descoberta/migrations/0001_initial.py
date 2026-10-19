import uuid

from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("anuncios", "0003_raio_por_localizacao_de_referencia"),
        ("catalogo", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Recomendacao",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("pontuacao", models.DecimalField(decimal_places=2, max_digits=5)),
                ("estado", models.CharField(
                    choices=[
                        ("ativa", "Ativa"),
                        ("descartada", "Descartada"),
                        ("convite_enviado", "Convite enviado"),
                    ],
                    default="ativa",
                    max_length=16,
                )),
                ("calculada_em", models.DateTimeField(auto_now=True)),
                ("anuncio", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="recomendacoes",
                    to="anuncios.anuncio",
                )),
                ("produto", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="recomendacoes",
                    to="catalogo.produto",
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="recomendacao",
            constraint=models.UniqueConstraint(
                fields=("anuncio", "produto"),
                name="recomendacao_unica_anuncio_produto",
            ),
        ),
        migrations.AddConstraint(
            model_name="recomendacao",
            constraint=models.CheckConstraint(
                condition=Q(pontuacao__gte=0) & Q(pontuacao__lte=100),
                name="recomendacao_pontuacao_0_a_100",
            ),
        ),
        migrations.AddIndex(
            model_name="recomendacao",
            index=models.Index(fields=["anuncio", "estado", "-pontuacao"], name="recomendacao_feed_idx"),
        ),
    ]
