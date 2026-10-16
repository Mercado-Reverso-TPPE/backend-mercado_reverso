# Backend Quero.

API REST do marketplace Quero., organizada em MVC com camadas. Este repositório contém somente o backend e sua infraestrutura de desenvolvimento: Django REST Framework, PostgreSQL/PostGIS e pgAdmin.

## Executar

1. Copie `.env.example` para `.env` e ajuste as credenciais locais.
2. Execute `docker compose up --build` na raiz do repositório.
3. A API fica em `http://localhost:8000/api/v1/` e o pgAdmin em `http://localhost:5050`.

No pgAdmin, conecte ao host `db`, porta `5432`, banco e usuário configurados no `.env`.

Para uma plataforma com proxy HTTPS, use `DJANGO_SETTINGS_MODULE=quero.settings.prod` e configure `SECRET_KEY`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` e `CSRF_TRUSTED_ORIGINS`. SMTP, geocodificador e URLs de confirmação/reset também são configuráveis pelo ambiente; consulte `.env.example`.

## Release 1 — backend

- Cadastro, login JWT, renovação e encerramento de sessão; bloqueio temporário após falhas consecutivas configurável.
- Recuperação de senha por e-mail, com token de uso único e prazo configurável.
- Consulta e atualização do perfil/localização; troca de e-mail mediante confirmação. Atualizar a localização recalcula o centro geográfico dos anúncios ativos e pausados.
- Geocodificação de CEP/cidade para coordenadas, com cache no banco. O serviço padrão é o Nominatim público do OpenStreetMap, configurável por `GEOCODER_URL` e `GEOCODER_USER_AGENT`.
- Catálogo de categorias, anúncios de procura, feed por alcance/distância, gerenciamento de status e contagem de ofertas.
- Envio, consulta, edição e retirada de ofertas; histórico de preços e restrição de visibilidade para impedir que vendedores vejam ofertas concorrentes.

## Rotas principais

Todas as rotas abaixo usam o prefixo `/api/v1`.

| Método | Rota | Uso |
| --- | --- | --- |
| POST | `/usuarios` | Criar conta; localização pode ser informada por coordenadas ou CEP/cidade |
| POST / DELETE | `/sessoes` | Entrar / encerrar sessão (envie o refresh token no DELETE) |
| POST | `/sessoes/renovar` | Renovar access token |
| POST | `/senha/redefinir` | Solicitar recuperação de senha (resposta genérica) |
| POST | `/senha/redefinir/confirmar` | Definir nova senha com UID e token recebidos |
| GET / PATCH | `/perfil` | Consultar/atualizar perfil e localização |
| POST | `/perfil/email` | Solicitar troca de e-mail |
| POST | `/perfil/email/confirmar` | Confirmar troca usando token recebido por e-mail |
| GET | `/categorias` | Listar categorias ativas |
| GET / POST | `/anuncios` | Consultar feed geográfico / criar anúncio de procura |
| GET | `/anuncios/meus` | Listar anúncios próprios |
| GET / PATCH | `/anuncios/{id}` | Consultar/editar anúncio próprio |
| PATCH | `/anuncios/{id}/status` | Pausar, reativar ou encerrar anúncio |
| GET / POST | `/anuncios/{id}/ofertas` | Listar ofertas visíveis / enviar oferta |
| GET | `/ofertas/meus` | Listar ofertas enviadas |
| PATCH / DELETE | `/ofertas/{id}` | Editar / retirar oferta ainda não aceita |

O Nominatim público exige identificação no `User-Agent`, uso moderado e atribuição ao OpenStreetMap. A interface deve exibir “© OpenStreetMap contributors” quando apresentar resultados de geocodificação. Para maior volume, configure um provedor apropriado em vez do serviço público.

As regras de negócio ficam em `services.py`; os modelos representam os dados, serializers validam entrada e saída, e views tratam HTTP e autorização. Migrações existentes preservam os dados dos anúncios já cadastrados ao introduzir o catálogo de categorias.

## Testes

Os testes parametrizados ficam em `backend/tests` e usam `pytest-django`. Com os serviços iniciados, execute `docker compose exec backend pytest`. A suíte usa banco PostGIS de teste criado pelo Django; chamadas ao serviço externo de geocodificação são substituídas por respostas simuladas.

Este compose é para desenvolvimento local. Troque as credenciais padrão antes de expor os serviços fora da máquina local.
