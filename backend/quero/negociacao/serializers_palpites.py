from decimal import Decimal

from rest_framework import serializers


class PalpiteSerializer(serializers.Serializer):
    valor = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )


class EstimativaPrecoSerializer(serializers.Serializer):
    disponivel = serializers.BooleanField()
    minimo = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    media = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    maximo = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    diverge_da_faixa_solicitada = serializers.BooleanField(allow_null=True, required=False)
