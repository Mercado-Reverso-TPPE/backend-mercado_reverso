from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver

from quero.negociacao.models import Negociacao

from .models import Produto
from .services import alterar_status_produto

STATUS_DO_PRODUTO_POR_NEGOCIACAO = {
    Negociacao.Status.EM_ANDAMENTO: Produto.Status.RESERVADO,
    Negociacao.Status.CONCLUIDA: Produto.Status.VENDIDO,
    Negociacao.Status.CANCELADA: Produto.Status.DISPONIVEL,
}


@receiver(post_save, sender=Negociacao, dispatch_uid="catalogo_sincronizar_status_produto")
def sincronizar_status_do_produto(sender, instance, created, **kwargs):
    """Mantém o produto ofertado reservado durante a negociação e vendido após a conclusão.

    Quem cria ou altera a negociação deve fazê-lo em transação, para que a recusa da reserva
    desfaça também a negociação.
    """
    produto = instance.oferta.produto
    if produto is None:
        return
    novo_status = STATUS_DO_PRODUTO_POR_NEGOCIACAO[instance.status]
    produto.refresh_from_db(fields=["status"])
    if created and novo_status == Produto.Status.RESERVADO and produto.status != Produto.Status.DISPONIVEL:
        raise ValidationError("O produto desta oferta não está mais disponível.")
    if produto.status == novo_status:
        return
    if novo_status == Produto.Status.DISPONIVEL and produto.status != Produto.Status.RESERVADO:
        return
    alterar_status_produto(produto=produto, novo_status=novo_status)
