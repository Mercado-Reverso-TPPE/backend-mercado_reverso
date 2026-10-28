from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .catalogo import TipoNotificacao
from .models import Notificacao, PreferenciaNotificacao
from .serializers import AtualizarPreferenciasSerializer, NotificacaoSerializer


class NotificacaoPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class NotificacoesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        notificacoes = Notificacao.objects.filter(usuario=request.user).order_by("-criada_em")
        paginator = NotificacaoPagination()
        pagina = paginator.paginate_queryset(notificacoes, request, view=self)
        return paginator.get_paginated_response(NotificacaoSerializer(pagina, many=True).data)


class ContagemNaoLidasView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        quantidade = Notificacao.objects.filter(
            usuario=request.user,
            lida_em__isnull=True,
        ).count()
        return Response({"nao_lidas": quantidade})


class MarcarNotificacaoLidaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, notificacao_id):
        notificacao = get_object_or_404(
            Notificacao,
            pk=notificacao_id,
            usuario=request.user,
        )
        if notificacao.lida_em is None:
            notificacao.lida_em = timezone.now()
            notificacao.save(update_fields=("lida_em",))
        return Response(NotificacaoSerializer(notificacao).data)


class PreferenciasNotificacaoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        armazenadas = {
            (preferencia.tipo, preferencia.canal): preferencia.habilitada
            for preferencia in PreferenciaNotificacao.objects.filter(usuario=request.user)
        }
        valores = [
            {
                "tipo": tipo,
                "canal": canal,
                "habilitada": (
                    True if tipo == TipoNotificacao.SEGURANCA_CONTA else armazenadas.get((tipo, canal), True)
                ),
            }
            for tipo in TipoNotificacao.values
            for canal in PreferenciaNotificacao.Canal.values
        ]
        return Response({"preferencias": valores})

    def patch(self, request):
        serializer = AtualizarPreferenciasSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            for item in serializer.validated_data["preferencias"]:
                PreferenciaNotificacao.objects.update_or_create(
                    usuario=request.user,
                    tipo=item["tipo"],
                    canal=item["canal"],
                    defaults={"habilitada": item["habilitada"]},
                )
        return self.get(request)
