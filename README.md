# Backend Quero.

API REST do marketplace Quero., organizada em MVC com camadas. Este repositório contém somente o backend e sua infraestrutura de desenvolvimento: Django REST Framework, PostgreSQL/PostGIS e pgAdmin.

## Executar

1. Copie `.env.example` para `.env` e ajuste as credenciais locais.
2. Execute `docker compose up --build` na raiz do repositório.
3. A API fica em `http://localhost:8000/api/v1/` e o pgAdmin em `http://localhost:5050`.

No pgAdmin, conecte ao host `db`, porta `5432`, banco e usuário configurados no `.env`.

Para uma plataforma com proxy HTTPS, use `DJANGO_SETTINGS_MODULE=quero.settings.prod` e configure `SECRET_KEY`, `REDIS_URL`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` e `CSRF_TRUSTED_ORIGINS`. O cache compartilhado é usado para controle de tentativas de login e cache/limitação de geocodificação. SMTP, geocodificador e URLs de confirmação/reset também são configuráveis pelo ambiente; consulte `.env.example`.

## Release 1 — backend

- Cadastro, login JWT, renovação e encerramento de sessão; bloqueio temporário após falhas consecutivas configurável.
- Recuperação de senha por e-mail, com token de uso único e prazo configurável.
- Consulta e atualização do perfil/localização; troca de e-mail mediante confirmação. Atualizar a localização recalcula o centro geográfico dos anúncios ativos e pausados.
- Geocodificação de CEP/cidade para coordenadas, com cache configurável (em memória no desenvolvimento e Redis compartilhado em produção). O serviço padrão é o Nominatim público do OpenStreetMap, configurável por `GEOCODER_URL` e `GEOCODER_USER_AGENT`.
- Catálogo de categorias, anúncios de procura, feed por alcance/distância, gerenciamento de status e contagem de ofertas.
- Envio, consulta, edição e retirada de ofertas; histórico de preços e restrição de visibilidade para impedir que vendedores vejam ofertas concorrentes.
- Catálogo do vendedor: CRUD de produtos restrito ao proprietário, upload de fotos com limites de quantidade, tamanho e formato (`PRODUTO_FOTOS_MAXIMO`, `PRODUTO_FOTO_TAMANHO_MAXIMO_MB`; JPEG, PNG ou WEBP) e status disponível/reservado/vendido. O produto fica reservado enquanto há negociação em andamento, volta a ficar disponível se ela for cancelada e passa a vendido quando é concluída. Ofertas podem usar um produto disponível do catálogo; nome, descrição, estado, preço e foto de capa são copiados para a oferta, e alterações ou exclusões posteriores do produto não alteram ofertas já enviadas.
- Chat de negociação: cada oferta é a conversa entre o comprador do anúncio e o vendedor. Mensagens são imutáveis, consultadas por polling (`?apos=<id>`), com contagem e marcação de não lidas. A conversa fica somente leitura quando a oferta é retirada/recusada, o anúncio é encerrado ou a negociação termina.
- Denúncia de conversa e bloqueio/desbloqueio de usuários. Um bloqueio ativo, em qualquer sentido, impede novas mensagens e novas ofertas entre as duas pessoas, sem apagar o histórico.
- Conclusão bilateral: o vendedor solicita e o comprador confirma ou recusa dentro de `NEGOCIACAO_PRAZO_CONFIRMACAO_HORAS` (padrão 72 h); vencido o prazo, a conclusão é confirmada automaticamente. Concluir encerra o anúncio, marca o produto ofertado como vendido, torna a negociação imutável e convida as partes a avaliar.
- Histórico pessoal somente leitura das negociações concluídas e canceladas, com filtros por papel e status.

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
| GET / POST | `/anuncios` | Buscar no feed geográfico (ver [Busca](#busca-de-anúncios)) / criar anúncio de procura |
| GET | `/anuncios/meus` | Listar anúncios próprios |
| GET / PATCH | `/anuncios/{id}` | Consultar/editar anúncio próprio |
| PATCH | `/anuncios/{id}/status` | Pausar, reativar ou encerrar anúncio |
| GET / POST | `/anuncios/{id}/ofertas` | Listar ofertas visíveis / enviar oferta (opcionalmente com `produto_id` do catálogo) |
| GET | `/ofertas/meus` | Listar ofertas enviadas |
| PATCH / DELETE | `/ofertas/{id}` | Editar / retirar oferta ainda não aceita |
| GET / POST | `/produtos` | Listar (filtro opcional `?status=`) / cadastrar produtos do catálogo próprio |
| GET / PATCH / DELETE | `/produtos/{id}` | Consultar / editar / excluir produto próprio |
| PATCH | `/produtos/{id}/status` | Marcar produto como disponível, reservado ou vendido fora de negociação |
| POST | `/produtos/{id}/fotos` | Enviar fotos (multipart, campo `fotos` repetido); o lote é aceito por inteiro ou rejeitado |
| DELETE | `/produtos/{id}/fotos/{foto_id}` | Remover foto |
| GET / POST | `/buscas-salvas` | Listar / criar buscas salvas próprias |
| GET / PATCH / PUT / DELETE | `/buscas-salvas/{id}` | Consultar / editar / remover busca salva própria |
| GET | `/buscas-salvas/{id}/anuncios` | Executar a busca salva (mesma resposta e paginação da busca) |
| GET | `/conversas` | Listar conversas do usuário, com não lidas e indicador de somente leitura |
| GET | `/conversas/nao-lidas` | Total de mensagens não lidas |
| GET / POST | `/conversas/{oferta_id}/mensagens` | Listar (paginado, `?apos=<id>` para polling) / enviar mensagem |
| POST | `/conversas/{oferta_id}/leitura` | Marcar mensagens recebidas como lidas |
| POST | `/conversas/{oferta_id}/denuncias` | Denunciar a conversa (`motivo`, `mensagem_id` opcional) |
| GET / POST | `/bloqueios` | Listar / bloquear usuário (`usuario_id`, `motivo` opcional) |
| DELETE | `/bloqueios/{usuario_id}` | Desbloquear usuário |
| GET | `/negociacoes/{id}` | Consultar negociação em que o usuário é parte |
| POST | `/negociacoes/{id}/conclusao` | Vendedor solicita a conclusão |
| POST | `/negociacoes/{id}/conclusao/confirmacao` | Comprador confirma a conclusão |
| POST | `/negociacoes/{id}/conclusao/recusa` | Comprador recusa a conclusão; a negociação continua em andamento |
| GET | `/historico` | Negociações concluídas/canceladas (`?papel=comprador\|vendedor`, `?status=concluida\|cancelada`) |
| GET | `/historico/{id}` | Detalhe com valores negociados e mensagens |

### Busca de anúncios

`GET /anuncios` só considera anúncios **ativos** cujo raio alcança a localização do usuário autenticado; pausados, encerrados e em negociação nunca aparecem, e nenhum parâmetro amplia esse conjunto. Usuários sem localização recebem lista vazia. Todos os parâmetros são opcionais e combináveis:

| Parâmetro | Descrição |
| --- | --- |
| `q` | Palavras buscadas em título ou descrição, sem diferenciar maiúsculas; todas as palavras precisam aparecer |
| `categoria` | Slug de uma categoria ativa |
| `preco_min`, `preco_max` | Faixa de preço do vendedor; retorna anúncios cujo orçamento se sobrepõe a ela (limites ausentes no anúncio não restringem) |
| `distancia_max_km` | Distância máxima até o comprador, de 1 a `RAIO_MAXIMO_KM` |
| `ordenacao` | `distancia` (padrão), `recentes`, `preco_minimo` ou `preco_maximo` (orçamento = `preco_max`, ou `preco_min` na falta dele; anúncios sem orçamento ficam por último). Empates são desfeitos pelos mais recentes e depois pelo id |
| `tamanho` | Itens por página, de 1 a 50 (padrão 20) |
| `cursor` | Valor opaco recebido em `next` |

Resposta: `{"count": <total que atende aos filtros>, "next": <URL da próxima página ou null>, "results": [...]}`. A paginação é por chave: cada página continua após os valores de ordenação do último item, então inserções ou remoções entre requisições não duplicam nem pulam registros. O cursor vale apenas para a ordenação em que foi gerado. Parâmetros ou cursores inválidos retornam 400 indicando o campo.

Buscas salvas guardam `nome` (único por usuário), `termo`, `categoria`, `preco_min`, `preco_max`, `distancia_max_km` e `ordenacao`. Cada usuário só vê e altera as próprias; as de terceiros respondem 404. `/anuncios?meus=true` e `/anuncios/meus` continuam listando os anúncios do próprio comprador em qualquer status.

O Nominatim público exige identificação no `User-Agent`, uso moderado e atribuição ao OpenStreetMap. A interface deve exibir “© OpenStreetMap contributors” quando apresentar resultados de geocodificação. Para maior volume, configure um provedor apropriado em vez do serviço público.

Cada app segue MVC com camadas: `models.py` (Model) representa os dados; `views.py` (View) contém os serializers que validam a entrada e formatam a saída; `controllers.py` (Controller) trata HTTP e autorização; e `services.py` concentra as regras de negócio. Migrações existentes preservam os dados dos anúncios já cadastrados ao introduzir o catálogo de categorias.

O schema de domínio tem no máximo 15 modelos/tabelas próprios, com dados relacionais normalizados; tabelas internas do Django e tabelas auxiliares do PostgreSQL/PostGIS não entram nessa contagem. Localização de referência é atributo 1:1 do usuário, eventos de negociação reúnem histórico de preço, contrapropostas e mensagens, e o alcance geográfico é materializado apenas para indexação GiST.

A confirmação automática é aplicada ao consultar negociações e histórico; para que ocorra também sem acesso, agende `python manage.py concluir_negociacoes_expiradas` (por exemplo, a cada 15 minutos via cron).

O modelo físico (diagrama entidade-relacionamento e DDL) está em [`docs_backend/modelo-fisico.md`](docs_backend/modelo-fisico.md) e [`docs_backend/schema.sql`](docs_backend/schema.sql).

## Testes

Os testes parametrizados ficam em `backend/tests` e usam `pytest-django`. Com os serviços iniciados, execute `docker compose exec backend pytest`. A suíte usa banco PostGIS de teste criado pelo Django; chamadas ao serviço externo de geocodificação são substituídas por respostas simuladas.

## Lint

O lint e a formatação usam o [ruff](https://docs.astral.sh/ruff/), configurado em `backend/pyproject.toml`. O CI falha se houver aviso ou arquivo fora do padrão.

```sh
docker compose exec backend ruff check .          # lint
docker compose exec backend ruff format .         # formata o código
```

Este compose é para desenvolvimento local. Troque as credenciais padrão antes de expor os serviços fora da máquina local.
