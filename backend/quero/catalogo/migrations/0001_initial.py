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
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Produto",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("nome", models.CharField(max_length=160)),
                ("descricao", models.TextField()),
                ("estado_conservacao", models.CharField(
                    choices=[
                        ("novo", "Novo"),
                        ("seminovo", "Seminovo"),
                        ("usado_bom", "Usado — bom estado"),
                        ("usado_marcas", "Usado — com marcas"),
                        ("pecas", "Para peças"),
                    ],
                    max_length=16,
                )),
                ("preco", models.DecimalField(
                    decimal_places=2,
                    max_digits=10,
                    validators=[MinValueValidator(0.01)],
                )),
                ("status", models.CharField(
                    choices=[
                        ("disponivel", "Disponível"),
                        ("reservado", "Reservado"),
                        ("vendido", "Vendido"),
                    ],
                    default="disponivel",
                    max_length=12,
                )),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("categoria", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="produtos",
                    to="anuncios.categoria",
                )),
                ("vendedor", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="produtos",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ("-criado_em",)},
        ),
        migrations.AddConstraint(
            model_name="produto",
            constraint=models.CheckConstraint(condition=Q(preco__gt=0), name="produto_preco_positivo"),
        ),
        migrations.AddIndex(
            model_name="produto",
            index=models.Index(fields=["vendedor", "status"], name="produto_vendedor_status_idx"),
        ),
        migrations.AddIndex(
            model_name="produto",
            index=models.Index(fields=["status", "categoria"], name="produto_status_categoria_idx"),
        ),
        migrations.CreateModel(
            name="FotoProduto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("arquivo", models.ImageField(upload_to="produtos/%Y/%m/")),
                ("ordem", models.PositiveSmallIntegerField()),
                ("criada_em", models.DateTimeField(auto_now_add=True)),
                ("produto", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="fotos",
                    to="catalogo.produto",
                )),
            ],
            options={"ordering": ("ordem", "pk")},
        ),
        migrations.AddConstraint(
            model_name="fotoproduto",
            constraint=models.UniqueConstraint(
                fields=("produto", "ordem"),
                name="foto_produto_ordem_unica",
            ),
        ),
    ]
