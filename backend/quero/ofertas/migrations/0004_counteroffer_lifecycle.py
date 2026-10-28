from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("ofertas", "0003_alter_eventonegociacao_tipo_evento"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="oferta",
            name="uma_oferta_ativa_por_vendedor_anuncio",
        ),
        migrations.AddConstraint(
            model_name="oferta",
            constraint=models.UniqueConstraint(
                condition=Q(status__in=("enviada", "em_negociacao")),
                fields=("anuncio", "vendedor"),
                name="uma_oferta_ativa_por_vendedor_anuncio",
            ),
        ),
        migrations.AlterField(
            model_name="eventonegociacao",
            name="tipo_evento",
            field=models.CharField(
                choices=[
                    ("enviada", "Oferta enviada"),
                    ("editada", "Oferta editada"),
                    ("retirada", "Oferta retirada"),
                    ("contraproposta", "Contraproposta enviada"),
                    ("contraposta_aceita", "Contraproposta aceita"),
                    ("contraposta_recusada", "Contraproposta recusada"),
                    ("contraposta_expirada", "Contraproposta expirada"),
                    ("contraposta_substituida", "Contraproposta substituída"),
                    ("aceita", "Oferta aceita"),
                    ("recusada", "Oferta recusada"),
                    ("negociacao_cancelada", "Negociação cancelada"),
                    ("mensagem", "Mensagem"),
                ],
                default="enviada",
                max_length=24,
            ),
        ),
    ]
