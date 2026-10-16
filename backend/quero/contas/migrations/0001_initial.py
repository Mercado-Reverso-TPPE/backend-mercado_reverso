import uuid
from django.conf import settings
from django.db import migrations, models
import django.contrib.gis.db.models.fields
import django.contrib.auth.models
import django.utils.timezone
import quero.contas.models

class Migration(migrations.Migration):
    initial = True
    dependencies = [("auth", "0012_alter_user_first_name_max_length"), ("core", "0001_enable_postgis")]
    operations = [
        migrations.CreateModel(name="Usuario", fields=[
            ("password", models.CharField(max_length=128, verbose_name="password")),
            ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
            ("is_superuser", models.BooleanField(default=False, help_text="Designates that this user has all permissions without explicitly assigning them.", verbose_name="superuser status")),
            ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
            ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("email", models.EmailField(max_length=254, unique=True)),
            ("nome", models.CharField(max_length=150)),
            ("telefone", models.CharField(blank=True, max_length=30)),
            ("foto", models.URLField(blank=True)),
            ("reputacao", models.DecimalField(decimal_places=2, default=0, max_digits=3)),
            ("is_staff", models.BooleanField(default=False, help_text="Designates whether the user can log into this admin site.", verbose_name="staff status")),
            ("is_active", models.BooleanField(default=True, help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.", verbose_name="active")),
            ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
            ("groups", models.ManyToManyField(blank=True, help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.", related_name="user_set", related_query_name="user", to="auth.group", verbose_name="groups")),
            ("user_permissions", models.ManyToManyField(blank=True, help_text="Specific permissions for this user.", related_name="user_set", related_query_name="user", to="auth.permission", verbose_name="user permissions")),
        ], options={"abstract": False}, managers=[("objects", quero.contas.models.UsuarioManager())]),
        migrations.CreateModel(name="Localizacao", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("ponto", django.contrib.gis.db.models.fields.PointField(srid=4326, geography=True)),
            ("cep", models.CharField(blank=True, max_length=9)), ("cidade", models.CharField(blank=True, max_length=120)),
            ("uf", models.CharField(blank=True, max_length=2)), ("atualizada_em", models.DateTimeField(auto_now=True)),
            ("usuario", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="localizacao", to=settings.AUTH_USER_MODEL)),
        ]),
    ]
