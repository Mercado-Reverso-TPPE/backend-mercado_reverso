from django.db import models


class TipoNotificacao(models.TextChoices):
    ANUNCIO_COMPATIVEL = "anuncio_compativel", "Anúncio compatível na região"
    CONVITE_RECOMENDACAO = "convite_recomendacao", "Convite para enviar oferta"
    OFERTA_RECEBIDA = "oferta_recebida", "Oferta recebida"
    OFERTA_ATUALIZADA = "oferta_atualizada", "Oferta atualizada"
    CONTRAPROPOSTA_RECEBIDA = "contraproposta_recebida", "Contraproposta recebida"
    CONTRAPROPOSTA_VENCENDO = "contraproposta_vencendo", "Contraproposta perto do vencimento"
    MENSAGEM_RECEBIDA = "mensagem_recebida", "Mensagem recebida"
    NEGOCIACAO_ATUALIZADA = "negociacao_atualizada", "Negociação atualizada"
    NEGOCIACAO_CONCLUIDA = "negociacao_concluida", "Negociação concluída"
    AVALIACAO_RECEBIDA = "avaliacao_recebida", "Avaliação publicada"
    SEGURANCA_CONTA = "seguranca_conta", "Segurança da conta"


TIPOS_NOTIFICACAO = tuple(TipoNotificacao.values)
