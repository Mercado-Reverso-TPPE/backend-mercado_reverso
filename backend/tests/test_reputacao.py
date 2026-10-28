"""
Testes do fluxo de avaliações — QRO-18.

Coberturas:
- Avaliação prematura (negociação não concluída)
- Duplicidade (segundo envio da mesma parte)
- Partes incorretas (terceiro tenta avaliar)
- Publicação simultânea quando ambas as partes avaliam
- Publicação via prazo (publicar_avaliacoes_vencidas)
- Privacidade (avaliação oculta antes do gatilho)
- Resposta única e imutável pelo avaliado
- Denúncia de avaliação + fila de moderação
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status

from quero.contas.models import Usuario
from quero.moderacao.models import AcaoModeracao
from quero.negociacao.models import Negociacao
from quero.ofertas.models import Oferta
from quero.reputacao.models import Avaliacao
from quero.reputacao.services import (
    PRAZO_PUBLICACAO_DIAS,
    criar_avaliacao,
    denunciar_avaliacao,
    publicar_avaliacoes_vencidas,
    responder_avaliacao,
)

# ---------------------------------------------------------------------------
# Fixtures auxiliares
# ---------------------------------------------------------------------------


@pytest.fixture
def comprador(db):
    return Usuario.objects.create_user(
        email="comprador@example.com",
        password="Senha-forte-123!",
        nome="Comprador Teste",
    )


@pytest.fixture
def vendedor(db):
    return Usuario.objects.create_user(
        email="vendedor@example.com",
        password="Senha-forte-123!",
        nome="Vendedor Teste",
    )


@pytest.fixture
def terceiro(db):
    return Usuario.objects.create_user(
        email="terceiro@example.com",
        password="Senha-forte-123!",
        nome="Terceiro",
    )


@pytest.fixture
def negociacao_concluida(db, comprador, vendedor, categoria):
    """Cria uma Negociacao concluída com a estrutura mínima necessária."""
    from django.contrib.gis.geos import Point

    from quero.anuncios.models import Anuncio

    comprador.ponto = Point(-46.6333, -23.5505, srid=4326)
    comprador.cidade = "São Paulo"
    comprador.uf = "SP"
    comprador.save(update_fields=["ponto", "cidade", "uf"])

    anuncio = Anuncio.objects.create(
        comprador=comprador,
        titulo="Procuro notebook",
        categoria=categoria,
        descricao="Para testes",
        raio_m=20_000,
    )
    oferta = Oferta.objects.create(
        anuncio=anuncio,
        vendedor=vendedor,
        descricao="Notebook barato",
        estado_conservacao=Oferta.EstadoConservacao.SEMINOVO,
        preco="800.00",
        status=Oferta.Status.ACEITA,
    )
    negociacao = Negociacao.objects.create(
        oferta=oferta,
        valor_final="800.00",
        status=Negociacao.Status.CONCLUIDA,
        concluida_em=timezone.now(),
    )
    return negociacao


@pytest.fixture
def negociacao_em_andamento(negociacao_concluida):
    # Negociacao.save bloqueia alterações em concluídas; update() contorna só no preparo do teste.
    Negociacao.objects.filter(pk=negociacao_concluida.pk).update(
        status=Negociacao.Status.EM_ANDAMENTO, concluida_em=None
    )
    negociacao_concluida.refresh_from_db()
    return negociacao_concluida


# ---------------------------------------------------------------------------
# Testes de criação — regras de acesso e estado
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_avaliacao_requer_negociacao_concluida(comprador, negociacao_em_andamento):
    with pytest.raises(ValidationError, match="concluída"):
        criar_avaliacao(autor=comprador, negociacao_id=negociacao_em_andamento.pk, nota=5)


@pytest.mark.django_db
def test_terceiro_nao_pode_avaliar(terceiro, negociacao_concluida):
    with pytest.raises(ValidationError, match="não participou"):
        criar_avaliacao(autor=terceiro, negociacao_id=negociacao_concluida.pk, nota=4)


@pytest.mark.django_db
def test_duplicidade_bloqueada(comprador, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=5)
    with pytest.raises(ValidationError, match="já avaliou"):
        criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=3)


# ---------------------------------------------------------------------------
# Testes de privacidade antes do gatilho
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_avaliacao_fica_oculta_enquanto_so_uma_parte_avaliou(comprador, negociacao_concluida):
    avaliacao = criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=5)
    assert avaliacao.publicada_em is None


@pytest.mark.django_db
def test_reputacao_nao_computa_avaliacao_nao_publicada(comprador, vendedor, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=1)
    # Só o comprador avaliou → avaliação do vendedor não publicada → reputação zero
    assert vendedor.reputacao == 0


# ---------------------------------------------------------------------------
# Testes de publicação simultânea
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_publicacao_simultanea_quando_ambas_as_partes_avaliam(comprador, vendedor, negociacao_concluida):
    av1 = criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=5)
    av2 = criar_avaliacao(autor=vendedor, negociacao_id=negociacao_concluida.pk, nota=4)

    av1.refresh_from_db()
    av2.refresh_from_db()

    assert av1.publicada_em is not None
    assert av2.publicada_em is not None
    # Ambas publicadas no mesmo instante (ou muito próximas)
    assert abs((av1.publicada_em - av2.publicada_em).total_seconds()) < 1


@pytest.mark.django_db
def test_reputacao_calculada_apos_publicacao(comprador, vendedor, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=4)
    criar_avaliacao(autor=vendedor, negociacao_id=negociacao_concluida.pk, nota=5)

    vendedor.refresh_from_db()
    comprador.refresh_from_db()

    assert vendedor.reputacao == 4.0
    assert comprador.reputacao == 5.0


# ---------------------------------------------------------------------------
# Testes de publicação por prazo
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_publicar_avaliacoes_vencidas_libera_pendente_apos_prazo(comprador, negociacao_concluida):
    avaliacao = criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=3)
    assert avaliacao.publicada_em is None

    # Simula a passagem do prazo retroagindo criada_em
    Avaliacao.objects.filter(pk=avaliacao.pk).update(
        criada_em=timezone.now() - timedelta(days=PRAZO_PUBLICACAO_DIAS + 1)
    )

    count, _ = publicar_avaliacoes_vencidas()
    assert count == 1

    avaliacao.refresh_from_db()
    assert avaliacao.publicada_em is not None


@pytest.mark.django_db
def test_publicar_avaliacoes_vencidas_nao_afeta_avaliacao_recente(comprador, negociacao_concluida):
    avaliacao = criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=3)

    count, _ = publicar_avaliacoes_vencidas()
    assert count == 0

    avaliacao.refresh_from_db()
    assert avaliacao.publicada_em is None


# ---------------------------------------------------------------------------
# Testes de resposta
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_avaliado_pode_responder_uma_vez(comprador, vendedor, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=3)
    criar_avaliacao(autor=vendedor, negociacao_id=negociacao_concluida.pk, nota=5)

    avaliacao_do_comprador = Avaliacao.objects.get(negociacao=negociacao_concluida, autor=comprador)
    assert avaliacao_do_comprador.publicada_em is not None

    avaliacao = responder_avaliacao(
        avaliado=vendedor,
        avaliacao_id=avaliacao_do_comprador.pk,
        resposta="Obrigado pelo feedback!",
    )
    assert avaliacao.resposta == "Obrigado pelo feedback!"
    assert avaliacao.respondida_em is not None


@pytest.mark.django_db
def test_resposta_e_imutavel(comprador, vendedor, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=3)
    criar_avaliacao(autor=vendedor, negociacao_id=negociacao_concluida.pk, nota=5)

    avaliacao_do_comprador = Avaliacao.objects.get(negociacao=negociacao_concluida, autor=comprador)
    responder_avaliacao(avaliado=vendedor, avaliacao_id=avaliacao_do_comprador.pk, resposta="Resposta inicial.")

    with pytest.raises(ValidationError, match="já foi respondida"):
        responder_avaliacao(avaliado=vendedor, avaliacao_id=avaliacao_do_comprador.pk, resposta="Tentativa de edição.")


@pytest.mark.django_db
def test_somente_avaliado_pode_responder(comprador, vendedor, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=3)
    criar_avaliacao(autor=vendedor, negociacao_id=negociacao_concluida.pk, nota=5)

    avaliacao_do_comprador = Avaliacao.objects.get(negociacao=negociacao_concluida, autor=comprador)
    with pytest.raises(ValidationError, match="não é o avaliado"):
        responder_avaliacao(avaliado=comprador, avaliacao_id=avaliacao_do_comprador.pk, resposta="Indevida.")


@pytest.mark.django_db
def test_resposta_exige_avaliacao_publicada(comprador, vendedor, negociacao_concluida):
    avaliacao = criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=3)
    assert avaliacao.publicada_em is None

    with pytest.raises(ValidationError, match="ainda não foi publicada"):
        responder_avaliacao(avaliado=vendedor, avaliacao_id=avaliacao.pk, resposta="Tentativa prematura.")


# ---------------------------------------------------------------------------
# Testes de denúncia e moderação
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_denuncia_cria_acao_moderacao_sem_alterar_avaliacao(comprador, vendedor, terceiro, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=2)
    criar_avaliacao(autor=vendedor, negociacao_id=negociacao_concluida.pk, nota=5)

    avaliacao = Avaliacao.objects.get(negociacao=negociacao_concluida, autor=comprador)
    acao = denunciar_avaliacao(denunciante=terceiro, avaliacao_id=avaliacao.pk, motivo="Comentário ofensivo.")

    assert acao.tipo == AcaoModeracao.Tipo.DENUNCIA_AVALIACAO
    assert acao.estado == AcaoModeracao.Estado.ABERTA
    assert acao.avaliacao == avaliacao

    # Avaliação permanece publicada e intacta
    avaliacao.refresh_from_db()
    assert avaliacao.publicada_em is not None
    assert avaliacao.comentario == ""  # não alterada


@pytest.mark.django_db
def test_denuncia_duplicada_aberta_e_bloqueada(comprador, vendedor, terceiro, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=2)
    criar_avaliacao(autor=vendedor, negociacao_id=negociacao_concluida.pk, nota=5)
    avaliacao = Avaliacao.objects.get(negociacao=negociacao_concluida, autor=comprador)

    denunciar_avaliacao(denunciante=terceiro, avaliacao_id=avaliacao.pk)
    with pytest.raises(ValidationError, match="já denunciou"):
        denunciar_avaliacao(denunciante=terceiro, avaliacao_id=avaliacao.pk)


@pytest.mark.django_db
def test_autor_nao_pode_denunciar_propria_avaliacao(comprador, vendedor, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=5)
    criar_avaliacao(autor=vendedor, negociacao_id=negociacao_concluida.pk, nota=5)

    avaliacao_do_comprador = Avaliacao.objects.get(negociacao=negociacao_concluida, autor=comprador)
    with pytest.raises(ValidationError, match="própria avaliação"):
        denunciar_avaliacao(denunciante=comprador, avaliacao_id=avaliacao_do_comprador.pk)


@pytest.mark.django_db
def test_denuncia_exige_avaliacao_publicada(comprador, vendedor, negociacao_concluida):
    avaliacao = criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=5)
    assert avaliacao.publicada_em is None

    with pytest.raises(ValidationError, match="publicadas"):
        denunciar_avaliacao(denunciante=vendedor, avaliacao_id=avaliacao.pk)


# ---------------------------------------------------------------------------
# Testes via HTTP (views)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_endpoint_criacao_avaliacao_retorna_201(cliente_api, comprador, negociacao_concluida):
    cliente_api.force_authenticate(user=comprador)
    resposta = cliente_api.post(
        f"/api/v1/negociacoes/{negociacao_concluida.pk}/avaliacoes",
        {"nota": 5, "comentario": "Ótimo!"},
        format="json",
    )
    assert resposta.status_code == status.HTTP_201_CREATED
    assert resposta.data["publicada_em"] is None


@pytest.mark.django_db
def test_endpoint_listagem_avaliacoes_nao_expoe_ocultas(cliente_api, comprador, vendedor, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=4)

    cliente_api.force_authenticate(user=comprador)
    resposta = cliente_api.get(f"/api/v1/usuarios/{vendedor.pk}/avaliacoes")
    assert resposta.status_code == status.HTTP_200_OK
    assert resposta.data["results"] == []


@pytest.mark.django_db
def test_endpoint_listagem_expoe_avaliacao_publicada(cliente_api, comprador, vendedor, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=4)
    criar_avaliacao(autor=vendedor, negociacao_id=negociacao_concluida.pk, nota=5)

    cliente_api.force_authenticate(user=comprador)
    resposta = cliente_api.get(f"/api/v1/usuarios/{vendedor.pk}/avaliacoes")
    assert resposta.status_code == status.HTTP_200_OK
    assert len(resposta.data["results"]) == 1
    assert resposta.data["results"][0]["nota"] == 4


@pytest.mark.django_db
def test_endpoint_resposta_impede_segunda_resposta(cliente_api, comprador, vendedor, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=3)
    criar_avaliacao(autor=vendedor, negociacao_id=negociacao_concluida.pk, nota=5)
    avaliacao = Avaliacao.objects.get(negociacao=negociacao_concluida, autor=comprador)

    cliente_api.force_authenticate(user=vendedor)
    r1 = cliente_api.post(f"/api/v1/avaliacoes/{avaliacao.pk}/resposta", {"resposta": "Primeira."}, format="json")
    assert r1.status_code == status.HTTP_200_OK

    r2 = cliente_api.post(f"/api/v1/avaliacoes/{avaliacao.pk}/resposta", {"resposta": "Segunda."}, format="json")
    assert r2.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_endpoint_denuncia_retorna_201(cliente_api, comprador, vendedor, terceiro, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=1)
    criar_avaliacao(autor=vendedor, negociacao_id=negociacao_concluida.pk, nota=5)
    avaliacao = Avaliacao.objects.get(negociacao=negociacao_concluida, autor=comprador)

    cliente_api.force_authenticate(user=terceiro)
    resposta = cliente_api.post(
        f"/api/v1/avaliacoes/{avaliacao.pk}/denuncias",
        {"motivo": "Ofensivo."},
        format="json",
    )
    assert resposta.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_fila_moderacao_exige_admin(cliente_api, comprador):
    cliente_api.force_authenticate(user=comprador)
    resposta = cliente_api.get("/api/v1/moderacao/avaliacoes")
    assert resposta.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_ve_fila_moderacao_e_pode_resolver(cliente_api, comprador, vendedor, terceiro, negociacao_concluida):
    criar_avaliacao(autor=comprador, negociacao_id=negociacao_concluida.pk, nota=1)
    criar_avaliacao(autor=vendedor, negociacao_id=negociacao_concluida.pk, nota=5)
    avaliacao = Avaliacao.objects.get(negociacao=negociacao_concluida, autor=comprador)
    denunciar_avaliacao(denunciante=terceiro, avaliacao_id=avaliacao.pk, motivo="Ofensivo.")

    admin = Usuario.objects.create_superuser(email="admin@example.com", password="Admin-forte-123!", nome="Admin")
    cliente_api.force_authenticate(user=admin)

    resposta = cliente_api.get("/api/v1/moderacao/avaliacoes")
    assert resposta.status_code == status.HTTP_200_OK
    assert len(resposta.data) == 1
    acao_id = resposta.data[0]["id"]

    patch = cliente_api.patch(f"/api/v1/moderacao/avaliacoes/{acao_id}", {"estado": "resolvida"}, format="json")
    assert patch.status_code == status.HTTP_200_OK
    assert patch.data["estado"] == "resolvida"
