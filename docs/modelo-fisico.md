# Modelo físico do banco

Banco: **PostgreSQL 16 + PostGIS 3.4**. O DDL completo das tabelas da aplicação (colunas, tipos, chaves, índices, `CHECK` e chaves estrangeiras) está em [`schema.sql`](schema.sql), gerado a partir do banco após aplicar todas as migrations.

## Diagrama entidade-relacionamento

Tabelas próprias da aplicação. As tabelas internas do Django (`auth_*`, `django_*`, `token_blacklist_*`) e as tabelas de junção `contas_usuario_groups` e `contas_usuario_user_permissions` não aparecem no diagrama.

```mermaid
erDiagram
    contas_usuario {
        varchar password
        timestamp_with_time_zone last_login
        boolean is_superuser
        varchar first_name
        varchar last_name
        boolean is_staff
        boolean is_active
        timestamp_with_time_zone date_joined
        uuid id PK
        varchar email UK
        varchar nome
        varchar telefone
        varchar foto
        geography ponto
        varchar cep
        varchar cidade
        varchar uf
        timestamp_with_time_zone localizacao_atualizada_em
    }
    anuncios_categoria {
        bigint id PK
        varchar nome UK
        varchar slug UK
        boolean ativa
    }
    anuncios_anuncio {
        uuid id PK
        uuid comprador_id FK
        varchar titulo
        bigint categoria_id FK
        text descricao
        numeric preco_min
        numeric preco_max
        integer raio_m
        geography alcance
        varchar status
        timestamp_with_time_zone criado_em
        timestamp_with_time_zone atualizado_em
    }
    ofertas_oferta {
        uuid id PK
        uuid anuncio_id FK
        uuid vendedor_id FK
        uuid produto_id FK
        varchar nome_produto_snapshot
        varchar foto_produto_snapshot
        text descricao
        varchar estado_conservacao
        numeric preco
        varchar status
        timestamp_with_time_zone criada_em
        timestamp_with_time_zone atualizada_em
    }
    ofertas_eventonegociacao {
        bigint id PK
        uuid oferta_id FK
        uuid autor_id FK
        numeric preco
        varchar status
        varchar tipo_evento
        text justificativa
        text texto
        smallint rodada
        timestamp_with_time_zone expira_em
        timestamp_with_time_zone respondida_em
        timestamp_with_time_zone lida_em
        varchar resultado
        timestamp_with_time_zone registrado_em
    }
    ofertas_buscasalva {
        uuid id PK
        uuid usuario_id FK
        varchar nome
        varchar termo
        bigint categoria_id FK
        numeric preco_min
        numeric preco_max
        integer distancia_max_km
        varchar ordenacao
        timestamp_with_time_zone criada_em
        timestamp_with_time_zone atualizada_em
    }
    catalogo_produto {
        uuid id PK
        uuid vendedor_id FK
        bigint categoria_id FK
        varchar nome
        text descricao
        varchar estado_conservacao
        numeric preco
        varchar status
        timestamp_with_time_zone criado_em
        timestamp_with_time_zone atualizado_em
    }
    catalogo_fotoproduto {
        bigint id PK
        uuid produto_id FK
        varchar arquivo
        smallint ordem
        timestamp_with_time_zone criada_em
    }
    negociacao_palpite {
        uuid id PK
        uuid anuncio_id FK
        uuid vendedor_id FK
        numeric valor
        timestamp_with_time_zone criado_em
        timestamp_with_time_zone atualizado_em
    }
    negociacao_negociacao {
        uuid id PK
        uuid oferta_id FK
        numeric valor_final
        varchar status
        timestamp_with_time_zone conclusao_solicitada_em
        timestamp_with_time_zone confirmada_em
        timestamp_with_time_zone concluida_em
        timestamp_with_time_zone cancelada_em
        timestamp_with_time_zone criada_em
        timestamp_with_time_zone atualizada_em
    }
    descoberta_recomendacao {
        uuid id PK
        uuid anuncio_id FK
        uuid produto_id FK
        numeric pontuacao
        varchar estado
        timestamp_with_time_zone calculada_em
    }
    notificacoes_notificacao {
        uuid id PK
        uuid usuario_id FK
        varchar tipo
        varchar titulo
        text mensagem
        uuid anuncio_id FK
        uuid oferta_id FK
        uuid negociacao_id FK
        varchar agrupamento
        timestamp_with_time_zone criada_em
        timestamp_with_time_zone lida_em
    }
    notificacoes_preferencianotificacao {
        bigint id PK
        uuid usuario_id FK
        varchar tipo
        varchar canal
        boolean habilitada
        timestamp_with_time_zone atualizada_em
    }
    reputacao_avaliacao {
        uuid id PK
        uuid negociacao_id FK
        uuid autor_id FK
        uuid avaliado_id FK
        smallint nota
        text comentario
        text resposta
        timestamp_with_time_zone respondida_em
        timestamp_with_time_zone criada_em
        timestamp_with_time_zone publicada_em
    }
    moderacao_acaomoderacao {
        uuid id PK
        uuid autor_id FK
        uuid alvo_id FK
        varchar tipo
        varchar estado
        uuid oferta_id FK
        bigint evento_id FK
        uuid avaliacao_id FK
        text motivo
        timestamp_with_time_zone criada_em
        timestamp_with_time_zone atualizada_em
    }
    contas_usuario ||--o{ anuncios_anuncio : "comprador_id"
    anuncios_categoria ||--o{ anuncios_anuncio : "categoria_id"
    anuncios_anuncio ||--o{ ofertas_oferta : "anuncio_id"
    contas_usuario ||--o{ ofertas_oferta : "vendedor_id"
    catalogo_produto ||--o{ ofertas_oferta : "produto_id"
    ofertas_oferta ||--o{ ofertas_eventonegociacao : "oferta_id"
    contas_usuario ||--o{ ofertas_eventonegociacao : "autor_id"
    contas_usuario ||--o{ ofertas_buscasalva : "usuario_id"
    anuncios_categoria ||--o{ ofertas_buscasalva : "categoria_id"
    contas_usuario ||--o{ catalogo_produto : "vendedor_id"
    anuncios_categoria ||--o{ catalogo_produto : "categoria_id"
    catalogo_produto ||--o{ catalogo_fotoproduto : "produto_id"
    anuncios_anuncio ||--o{ negociacao_palpite : "anuncio_id"
    contas_usuario ||--o{ negociacao_palpite : "vendedor_id"
    ofertas_oferta ||--o| negociacao_negociacao : "oferta_id"
    anuncios_anuncio ||--o{ descoberta_recomendacao : "anuncio_id"
    catalogo_produto ||--o{ descoberta_recomendacao : "produto_id"
    contas_usuario ||--o{ notificacoes_notificacao : "usuario_id"
    anuncios_anuncio ||--o{ notificacoes_notificacao : "anuncio_id"
    ofertas_oferta ||--o{ notificacoes_notificacao : "oferta_id"
    negociacao_negociacao ||--o{ notificacoes_notificacao : "negociacao_id"
    contas_usuario ||--o{ notificacoes_preferencianotificacao : "usuario_id"
    negociacao_negociacao ||--o{ reputacao_avaliacao : "negociacao_id"
    contas_usuario ||--o{ reputacao_avaliacao : "autor_id"
    contas_usuario ||--o{ reputacao_avaliacao : "avaliado_id"
    contas_usuario ||--o{ moderacao_acaomoderacao : "autor_id"
    contas_usuario ||--o{ moderacao_acaomoderacao : "alvo_id"
    ofertas_oferta ||--o{ moderacao_acaomoderacao : "oferta_id"
    ofertas_eventonegociacao ||--o{ moderacao_acaomoderacao : "evento_id"
    reputacao_avaliacao ||--o{ moderacao_acaomoderacao : "avaliacao_id"
```

## Tabelas

| Tabela | Conteúdo |
| --- | --- |
| `contas_usuario` | Usuário (login por e-mail) e localização de referência (`ponto` em `geography`) |
| `anuncios_categoria` | Catálogo de categorias |
| `anuncios_anuncio` | Anúncio de procura do comprador; `alcance` materializa o raio para indexação GiST |
| `ofertas_oferta` | Oferta de um vendedor para um anúncio |
| `ofertas_eventonegociacao` | Histórico de preço, contrapropostas e mensagens de uma oferta |
| `ofertas_buscasalva` | Filtros de busca salvos pelo usuário |
| `catalogo_produto` / `catalogo_fotoproduto` | Catálogo do vendedor e suas fotos |
| `negociacao_negociacao` | Negociação aberta a partir de uma oferta aceita (1:1) |
| `negociacao_palpite` | Palpite de preço de um vendedor sobre um anúncio |
| `descoberta_recomendacao` | Recomendação de produto para anúncio |
| `notificacoes_notificacao` / `notificacoes_preferencianotificacao` | Notificações e preferências por usuário |
| `reputacao_avaliacao` | Avaliação entre as partes após a negociação |
| `moderacao_acaomoderacao` | Denúncias e ações de moderação |

## Índices espaciais

- `contas_usuario.ponto` — GiST
- `anuncios_anuncio.alcance` — GiST

## Regenerar

Com os containers em execução:

```sh
docker compose exec -T db sh -c 'pg_dump -U quero -d quero --schema-only --no-owner --no-privileges $(for p in contas anuncios catalogo descoberta moderacao negociacao notificacoes ofertas reputacao; do printf -- "-t public.%s_* " $p; done)' | sed '/^\\restrict /d;/^\\unrestrict /d' > docs/schema.sql
```
