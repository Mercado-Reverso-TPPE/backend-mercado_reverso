from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import BaseUserCreationForm, UserChangeForm

from quero.contas.models import Usuario


class UsuarioCreationForm(BaseUserCreationForm):
    class Meta:
        model = Usuario
        fields = ("email", "nome")

    def clean_email(self):
        email = Usuario.objects.normalize_email(self.cleaned_data["email"]).lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe um usuário com este e-mail.")
        return email


class UsuarioChangeForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = "__all__"
        field_classes = {"email": forms.EmailField}


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    list_display = ("email", "nome", "cidade", "uf", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser", "uf")
    search_fields = ("email", "nome", "cidade")
    ordering = ("email",)
    # A localização só muda pela API, que também recalcula o alcance dos anúncios do usuário.
    readonly_fields = ("ponto", "cep", "cidade", "uf", "localizacao_atualizada_em", "last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados pessoais", {"fields": ("nome", "telefone", "foto")}),
        ("Localização", {"fields": ("ponto", "cep", "cidade", "uf", "localizacao_atualizada_em")}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "nome", "password1", "password2")}),)
