from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("moderacao", "0001_initial"),
        ("reputacao", "0001_initial"),
    ]

    operations = [
        # 1. Ampliar o campo tipo para acomodar o novo valor.
        migrations.AlterField(
            model_name="acaomoderacao",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("denuncia_conversa", "Denúncia de conversa"),
                    ("denuncia_avaliacao", "Denúncia de avaliação"),
                    ("bloqueio_usuario", "Bloqueio de usuário"),
                ],
                max_length=24,
            ),
        ),
        # 2. Adicionar FK opcional para Avaliacao.
        migrations.AddField(
            model_name="acaomoderacao",
            name="avaliacao",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="denuncias",
                to="reputacao.avaliacao",
            ),
        ),
        # 3. Substituir o CheckConstraint de compatibilidade pelo novo que inclui denuncia_avaliacao.
        migrations.RemoveConstraint(
            model_name="acaomoderacao",
            name="moderacao_alvo_compativel",
        ),
        migrations.AddConstraint(
            model_name="acaomoderacao",
            constraint=models.CheckConstraint(
                condition=(
                    Q(tipo="bloqueio_usuario", oferta__isnull=True, evento__isnull=True, avaliacao__isnull=True)
                    | Q(tipo="denuncia_conversa", oferta__isnull=False, avaliacao__isnull=True)
                    | Q(tipo="denuncia_avaliacao", avaliacao__isnull=False, oferta__isnull=True)
                ),
                name="moderacao_alvo_compativel",
            ),
        ),
        # 4. Unique constraint: denúncia de avaliação aberta por (autor, avaliacao).
        migrations.AddConstraint(
            model_name="acaomoderacao",
            constraint=models.UniqueConstraint(
                fields=("autor", "avaliacao"),
                condition=Q(tipo="denuncia_avaliacao", estado="aberta"),
                name="denuncia_avaliacao_aberta_unica",
            ),
        ),
    ]
