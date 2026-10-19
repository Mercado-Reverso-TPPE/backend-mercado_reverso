import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("negociacao", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Avaliacao",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("nota", models.PositiveSmallIntegerField(
                    validators=[MinValueValidator(1), MaxValueValidator(5)],
                )),
                ("comentario", models.TextField(blank=True, max_length=2000)),
                ("resposta", models.TextField(blank=True, max_length=2000)),
                ("respondida_em", models.DateTimeField(blank=True, null=True)),
                ("criada_em", models.DateTimeField(auto_now_add=True)),
                ("publicada_em", models.DateTimeField(blank=True, null=True)),
                ("autor", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="avaliacoes_escritas",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("avaliado", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="avaliacoes_recebidas",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("negociacao", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="avaliacoes",
                    to="negociacao.negociacao",
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="avaliacao",
            constraint=models.UniqueConstraint(
                fields=("negociacao", "autor"),
                name="uma_avaliacao_por_parte_negociacao",
            ),
        ),
        migrations.AddConstraint(
            model_name="avaliacao",
            constraint=models.CheckConstraint(
                condition=~Q(autor=models.F("avaliado")),
                name="avaliacao_entre_partes",
            ),
        ),
        migrations.AddConstraint(
            model_name="avaliacao",
            constraint=models.CheckConstraint(
                condition=Q(nota__gte=1) & Q(nota__lte=5),
                name="avaliacao_nota_1_a_5",
            ),
        ),
        migrations.AddIndex(
            model_name="avaliacao",
            index=models.Index(fields=["avaliado", "publicada_em"], name="avaliacao_reputacao_idx"),
        ),
    ]
