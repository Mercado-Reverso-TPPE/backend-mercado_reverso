import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class AcaoModeracao(models.Model):
    class Tipo(models.TextChoices):
        DENUNCIA_CONVERSA = "denuncia_conversa", "Denúncia de conversa"
        BLOQUEIO_USUARIO = "bloqueio_usuario", "Bloqueio de usuário"

    class Estado(models.TextChoices):
        ABERTA = "aberta", "Aberta"
        RESOLVIDA = "resolvida", "Resolvida"
        DESCARTADA = "descartada", "Descartada"
        ATIVA = "ativa", "Ativa"
        REVOGADA = "revogada", "Revogada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="acoes_moderacao_criadas",
    )
    alvo = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="acoes_moderacao_recebidas",
    )
    tipo = models.CharField(max_length=24, choices=Tipo.choices)
    estado = models.CharField(max_length=12, choices=Estado.choices)
    oferta = models.ForeignKey(
        "ofertas.Oferta",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="acoes_moderacao",
    )
    evento = models.ForeignKey(
        "ofertas.EventoNegociacao",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acoes_moderacao",
    )
    motivo = models.TextField(max_length=2000, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(autor=models.F("alvo")),
                name="moderacao_entre_usuarios",
            ),
            models.CheckConstraint(
                condition=(
                    Q(tipo="bloqueio_usuario", oferta__isnull=True, evento__isnull=True)
                    | Q(tipo="denuncia_conversa", oferta__isnull=False)
                ),
                name="moderacao_alvo_compativel",
            ),
            models.UniqueConstraint(
                fields=("autor", "alvo"),
                condition=Q(tipo="bloqueio_usuario", estado="ativa"),
                name="bloqueio_ativo_unico_por_par",
            ),
            models.UniqueConstraint(
                fields=("autor", "oferta"),
                condition=Q(tipo="denuncia_conversa", estado="aberta"),
                name="denuncia_aberta_unica_por_conversa",
            ),
        ]
        indexes = [
            models.Index(fields=("tipo", "estado", "-criada_em"), name="moderacao_fila_idx"),
        ]
