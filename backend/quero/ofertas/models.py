import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.core.validators import MinValueValidator


class Oferta(models.Model):
    class EstadoConservacao(models.TextChoices):
        NOVO = "novo", "Novo"
        SEMINOVO = "seminovo", "Seminovo"
        USADO_BOM = "usado_bom", "Usado — bom estado"
        USADO_MARCAS = "usado_marcas", "Usado — com marcas"
        PECAS = "pecas", "Para peças"

    class Status(models.TextChoices):
        ENVIADA = "enviada", "Enviada"
        EM_NEGOCIACAO = "em_negociacao", "Em negociação"
        ACEITA = "aceita", "Aceita"
        RECUSADA = "recusada", "Recusada"
        RETIRADA = "retirada", "Retirada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    anuncio = models.ForeignKey("anuncios.Anuncio", on_delete=models.PROTECT, related_name="ofertas")
    vendedor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ofertas_enviadas")
    produto = models.ForeignKey(
        "catalogo.Produto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ofertas",
    )
    nome_produto_snapshot = models.CharField(max_length=160, blank=True)
    foto_produto_snapshot = models.CharField(max_length=255, blank=True)
    descricao = models.TextField()
    estado_conservacao = models.CharField(max_length=16, choices=EstadoConservacao.choices)
    preco = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ENVIADA)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-criada_em",)
        constraints = [
            models.UniqueConstraint(
                fields=("anuncio", "vendedor"),
                condition=Q(status__in=("enviada", "em_negociacao")),
                name="uma_oferta_ativa_por_vendedor_anuncio",
            ),
        ]

    def __str__(self):
        return f"Oferta de {self.vendedor} para {self.anuncio}"


class EventoNegociacao(models.Model):
    class TipoEvento(models.TextChoices):
        ENVIADA = "enviada", "Oferta enviada"
        EDITADA = "editada", "Oferta editada"
        RETIRADA = "retirada", "Oferta retirada"
        CONTRAPROPOSTA = "contraproposta", "Contraproposta enviada"
        CONTRAPROPOSTA_ACEITA = "contraposta_aceita", "Contraproposta aceita"
        CONTRAPROPOSTA_RECUSADA = "contraposta_recusada", "Contraproposta recusada"
        CONTRAPROPOSTA_EXPIRADA = "contraposta_expirada", "Contraproposta expirada"
        CONTRAPROPOSTA_SUBSTITUIDA = "contraposta_substituida", "Contraproposta substituída"
        ACEITA = "aceita", "Oferta aceita"
        RECUSADA = "recusada", "Oferta recusada"
        NEGOCIACAO_CANCELADA = "negociacao_cancelada", "Negociação cancelada"
        MENSAGEM = "mensagem", "Mensagem"

    class Resultado(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        ACEITA = "aceita", "Aceita"
        RECUSADA = "recusada", "Recusada"
        EXPIRADA = "expirada", "Expirada"
        SUBSTITUIDA = "substituida", "Substituída"

    oferta = models.ForeignKey(Oferta, on_delete=models.PROTECT, related_name="eventos")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventos_negociacao")
    preco = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Oferta.Status.choices)
    tipo_evento = models.CharField(
        max_length=24,
        choices=TipoEvento.choices,
        default=TipoEvento.ENVIADA,
    )
    justificativa = models.TextField(blank=True)
    texto = models.TextField(max_length=5000, blank=True)
    rodada = models.PositiveSmallIntegerField(default=0)
    expira_em = models.DateTimeField(null=True, blank=True)
    respondida_em = models.DateTimeField(null=True, blank=True)
    lida_em = models.DateTimeField(null=True, blank=True)
    resultado = models.CharField(
        max_length=12,
        choices=Resultado.choices,
        null=True,
        blank=True,
    )
    registrado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("registrado_em", "pk")
        constraints = [
            models.CheckConstraint(
                condition=~Q(tipo_evento="contraproposta") | Q(expira_em__isnull=False),
                name="contraproposta_com_prazo",
            ),
            models.CheckConstraint(
                condition=~Q(tipo_evento="mensagem") | ~Q(texto=""),
                name="mensagem_negociacao_com_texto",
            ),
            models.UniqueConstraint(
                fields=("oferta",),
                condition=Q(tipo_evento="contraproposta", respondida_em__isnull=True),
                name="uma_contraproposta_aberta_por_oferta",
            ),
        ]
        indexes = [
            models.Index(fields=("oferta", "rodada"), name="oferta_hist_rodada_idx"),
            models.Index(fields=("tipo_evento", "expira_em"), name="oferta_hist_expira_idx"),
        ]


class BuscaSalva(models.Model):
    class Ordenacao(models.TextChoices):
        DISTANCIA = "distancia", "Distância"
        RECENTES = "recentes", "Mais recentes"
        PRECO_MINIMO = "preco_minimo", "Menor orçamento"
        PRECO_MAXIMO = "preco_maximo", "Maior orçamento"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="buscas_salvas",
    )
    nome = models.CharField(max_length=100)
    termo = models.CharField(max_length=160, blank=True)
    categoria = models.ForeignKey(
        "anuncios.Categoria",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buscas_salvas",
    )
    preco_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    preco_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    distancia_max_km = models.PositiveIntegerField(null=True, blank=True)
    ordenacao = models.CharField(
        max_length=16,
        choices=Ordenacao.choices,
        default=Ordenacao.DISTANCIA,
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("usuario", "nome"), name="busca_salva_nome_por_usuario"),
            models.CheckConstraint(
                condition=Q(preco_min__isnull=True)
                | Q(preco_max__isnull=True)
                | Q(preco_min__lte=models.F("preco_max")),
                name="busca_salva_faixa_preco_valida",
            ),
        ]
        indexes = [models.Index(fields=("usuario", "-atualizada_em"), name="busca_salva_usuario_idx")]
