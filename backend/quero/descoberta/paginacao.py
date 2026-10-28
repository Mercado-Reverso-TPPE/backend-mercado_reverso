import base64
import binascii
import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param

from .services import ORDENACOES


class PaginacaoPorChave:
    """Paginação por chave (seek): cada página continua a partir dos valores do último item.

    Diferente de offset, inserções e remoções entre requisições não duplicam nem pulam registros,
    e diferente do CursorPagination do DRF, a posição usa todos os campos da ordenação.
    """

    parametro_cursor = "cursor"
    parametro_tamanho = "tamanho"
    tamanho_padrao = 20
    tamanho_maximo = 50

    def paginar(self, queryset, request, ordenacao):
        campos = ORDENACOES[ordenacao]
        tamanho = self._tamanho(request)
        total = queryset.count()
        cursor = request.query_params.get(self.parametro_cursor)
        if cursor:
            valores = self._decodificar(cursor, ordenacao, len(campos))
            try:
                queryset = queryset.filter(self._apos(campos, valores))
            except (DjangoValidationError, ValueError, TypeError) as exc:
                raise ValidationError({"cursor": "Cursor inválido para esta busca."}) from exc

        itens = list(queryset[: tamanho + 1])
        self.tem_proxima = len(itens) > tamanho
        self.itens = itens[:tamanho]
        self.total = total
        self.proximo_cursor = None
        if self.tem_proxima:
            ultimo = self.itens[-1]
            valores = [self._serializar_valor(getattr(ultimo, campo)) for campo, _ in campos]
            self.proximo_cursor = self._codificar(ordenacao, valores)
        self.request = request
        return self.itens

    def resposta(self, dados):
        proxima = None
        if self.proximo_cursor:
            proxima = replace_query_param(self.request.build_absolute_uri(), self.parametro_cursor, self.proximo_cursor)
        return Response({"count": self.total, "next": proxima, "results": dados})

    def _tamanho(self, request):
        bruto = request.query_params.get(self.parametro_tamanho)
        if bruto is None:
            return self.tamanho_padrao
        try:
            tamanho = int(bruto)
        except ValueError as exc:
            raise ValidationError({self.parametro_tamanho: "Informe um número inteiro."}) from exc
        if not 1 <= tamanho <= self.tamanho_maximo:
            raise ValidationError({self.parametro_tamanho: f"Use um valor entre 1 e {self.tamanho_maximo}."})
        return tamanho

    @staticmethod
    def _apos(campos, valores):
        # (a, b, c) > (va, vb, vc) em ordem lexicográfica, respeitando a direção de cada campo.
        condicao = Q(pk__in=[])
        iguais = Q()
        for (campo, decrescente), valor in zip(campos, valores, strict=False):
            operador = "lt" if decrescente else "gt"
            condicao |= iguais & Q(**{f"{campo}__{operador}": valor})
            iguais &= Q(**{campo: valor})
        return condicao

    @staticmethod
    def _serializar_valor(valor):
        if isinstance(valor, datetime):
            return valor.isoformat()
        if isinstance(valor, (Decimal, UUID)):
            return str(valor)
        return valor

    @staticmethod
    def _codificar(ordenacao, valores):
        conteudo = json.dumps({"o": ordenacao, "v": valores}, separators=(",", ":"))
        return base64.urlsafe_b64encode(conteudo.encode()).decode()

    @staticmethod
    def _decodificar(cursor, ordenacao, quantidade):
        try:
            conteudo = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            valores = conteudo["v"]
            valido = conteudo["o"] == ordenacao and isinstance(valores, list) and len(valores) == quantidade
        except (binascii.Error, ValueError, KeyError, TypeError, UnicodeDecodeError):
            valido = False
        if not valido:
            raise ValidationError({"cursor": "Cursor inválido para esta busca."})
        return valores
