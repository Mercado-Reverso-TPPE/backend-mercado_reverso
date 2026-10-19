import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("anuncios", "0003_raio_por_localizacao_de_referencia"),
        ("ofertas", "0002_oferta_catalogo_buscas_y_eventos"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Palpite",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("valor", models.DecimalField(
                    decimal_places=2,
                    max_digits=10,
                    validators=[MinValueValidator(0.01)],
                )),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("anuncio", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="palpites",
                    to="anuncios.anuncio",
                )),
                ("vendedor", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="palpites",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="palpite",
            constraint=models.UniqueConstraint(
                fields=("anuncio", "vendedor"),
                name="um_palpite_por_vendedor_anuncio",
            ),
        ),
        migrations.AddConstraint(
            model_name="palpite",
            constraint=models.CheckConstraint(condition=Q(valor__gt=0), name="palpite_valor_positivo"),
        ),
        migrations.AddIndex(
            model_name="palpite",
            index=models.Index(fields=["anuncio", "criado_em"], name="palpite_anuncio_criado_idx"),
        ),
        migrations.CreateModel(
            name="Negociacao",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("valor_final", models.DecimalField(
                    decimal_places=2,
                    max_digits=10,
                    validators=[MinValueValidator(0.01)],
                )),
                ("status", models.CharField(
                    choices=[
                        ("em_andamento", "Em andamento"),
                        ("concluida", "Concluída"),
                        ("cancelada", "Cancelada"),
                    ],
                    default="em_andamento",
                    max_length=14,
                )),
                ("conclusao_solicitada_em", models.DateTimeField(blank=True, null=True)),
                ("confirmada_em", models.DateTimeField(blank=True, null=True)),
                ("concluida_em", models.DateTimeField(blank=True, null=True)),
                ("cancelada_em", models.DateTimeField(blank=True, null=True)),
                ("criada_em", models.DateTimeField(auto_now_add=True)),
                ("atualizada_em", models.DateTimeField(auto_now=True)),
                ("oferta", models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="negociacao",
                    to="ofertas.oferta",
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="negociacao",
            constraint=models.CheckConstraint(
                condition=Q(valor_final__gt=0),
                name="negociacao_valor_final_positivo",
            ),
        ),
        migrations.AddIndex(
            model_name="negociacao",
            index=models.Index(fields=["status", "atualizada_em"], name="neg_status_atual_idx"),
        ),
    ]
