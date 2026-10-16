import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True
    dependencies = [("anuncios", "0002_categoria_e_cidade"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Oferta",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("descricao", models.TextField()),
                ("estado_conservacao", models.CharField(choices=[("novo", "Novo"), ("seminovo", "Seminovo"), ("usado", "Usado")], max_length=12)),
                ("preco", models.DecimalField(decimal_places=2, max_digits=10, validators=[MinValueValidator(0.01)])),
                ("status", models.CharField(choices=[("enviada", "Enviada"), ("aceita", "Aceita"), ("recusada", "Recusada"), ("retirada", "Retirada")], default="enviada", max_length=12)),
                ("criada_em", models.DateTimeField(auto_now_add=True)),
                ("atualizada_em", models.DateTimeField(auto_now=True)),
                ("anuncio", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ofertas", to="anuncios.anuncio")),
                ("vendedor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ofertas_enviadas", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-criada_em",)},
        ),
        migrations.AddConstraint(
            model_name="oferta",
            constraint=models.UniqueConstraint(condition=Q(status__in=("enviada", "aceita")), fields=("anuncio", "vendedor"), name="uma_oferta_ativa_por_vendedor_anuncio"),
        ),
        migrations.CreateModel(
            name="HistoricoOferta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("preco", models.DecimalField(decimal_places=2, max_digits=10)),
                ("status", models.CharField(choices=[("enviada", "Enviada"), ("aceita", "Aceita"), ("recusada", "Recusada"), ("retirada", "Retirada")], max_length=12)),
                ("registrado_em", models.DateTimeField(auto_now_add=True)),
                ("autor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="alteracoes_ofertas", to=settings.AUTH_USER_MODEL)),
                ("oferta", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="historico", to="ofertas.oferta")),
            ],
            options={"ordering": ("registrado_em",)},
        ),
    ]
