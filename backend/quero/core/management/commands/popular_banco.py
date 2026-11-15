# ruff: noqa: E501 — os textos dos anúncios e produtos são dados; quebrá-los só piora a leitura.
"""
Popula o banco de homologação com dados realistas.

Pessoas fictícias (nomes comuns, e-mails em example.com) em bairros reais de
capitais brasileiras, pedidos de compra e produtos com preços de mercado, e o
ciclo completo de negociação: ofertas, contrapropostas, conversa, conclusão e
avaliações. Tudo passa pelos serviços do domínio, então notificações,
histórico e reputação ficam coerentes com as regras do backend.

Uso:
    python manage.py popular_banco             # acrescenta os dados; não mexe no que já existe
    python manage.py popular_banco --recriar   # apaga TODO o banco (inclusive contas) e popula de novo

Só roda com DEBUG ligado: nunca deve tocar um banco de produção.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from quero.anuncios.models import Anuncio, Categoria
from quero.catalogo.models import Produto
from quero.contas.models import Usuario
from quero.negociacao.services import (
    confirmar_conclusao,
    enviar_mensagem,
    negociacao_da_oferta,
    solicitar_conclusao,
)
from quero.ofertas.models import Oferta
from quero.ofertas.services import aceitar_oferta, enviar_contraproposta, enviar_oferta
from quero.reputacao.services import criar_avaliacao

SENHA = "quero-homologacao-2026"
CONTA_DE_TESTE = "voce@example.com"

CATEGORIAS = [
    ("casa-jardim", "Casa & Jardim"),
    ("eletronicos", "Eletrônicos"),
    ("esportes", "Esportes"),
    ("games", "Games"),
    ("informatica", "Informática"),
    ("instrumentos", "Instrumentos"),
    ("outros", "Outros"),
    ("veiculos", "Veículos"),
]

# (bairro, cidade, UF, latitude, longitude)
BAIRROS = {
    "pinheiros": ("Pinheiros", "São Paulo", "SP", -23.5667, -46.6919),
    "vila-mariana": ("Vila Mariana", "São Paulo", "SP", -23.5891, -46.6345),
    "moema": ("Moema", "São Paulo", "SP", -23.6009, -46.6627),
    "tatuape": ("Tatuapé", "São Paulo", "SP", -23.5404, -46.5763),
    "santana": ("Santana", "São Paulo", "SP", -23.5022, -46.6253),
    "perdizes": ("Perdizes", "São Paulo", "SP", -23.5360, -46.6770),
    "butanta": ("Butantã", "São Paulo", "SP", -23.5719, -46.7085),
    "ipiranga": ("Ipiranga", "São Paulo", "SP", -23.5891, -46.6056),
    "lapa": ("Lapa", "São Paulo", "SP", -23.5276, -46.7058),
    "brooklin": ("Brooklin", "São Paulo", "SP", -23.6108, -46.6942),
    "cambui": ("Cambuí", "Campinas", "SP", -22.8931, -47.0510),
    "barao-geraldo": ("Barão Geraldo", "Campinas", "SP", -22.8227, -47.0846),
    "copacabana": ("Copacabana", "Rio de Janeiro", "RJ", -22.9711, -43.1822),
    "tijuca": ("Tijuca", "Rio de Janeiro", "RJ", -22.9254, -43.2361),
    "botafogo": ("Botafogo", "Rio de Janeiro", "RJ", -22.9519, -43.1842),
    "savassi": ("Savassi", "Belo Horizonte", "MG", -19.9385, -43.9347),
    "pampulha": ("Pampulha", "Belo Horizonte", "MG", -19.8579, -43.9709),
    "batel": ("Batel", "Curitiba", "PR", -25.4422, -49.2899),
    "agua-verde": ("Água Verde", "Curitiba", "PR", -25.4523, -49.2775),
    "asa-sul": ("Asa Sul", "Brasília", "DF", -15.8170, -47.9019),
    "asa-norte": ("Asa Norte", "Brasília", "DF", -15.7633, -47.8822),
    "moinhos": ("Moinhos de Vento", "Porto Alegre", "RS", -30.0256, -51.2032),
    "boa-viagem": ("Boa Viagem", "Recife", "PE", -8.1197, -34.9024),
    "barra-salvador": ("Barra", "Salvador", "BA", -13.0094, -38.5311),
}

# (chave, nome, bairro, telefone)
PESSOAS = [
    ("voce", "Você (conta de teste)", "pinheiros", "(11) 98000-0000"),
    ("mariana", "Mariana Oliveira Santos", "vila-mariana", "(11) 98412-3307"),
    ("rafael", "Rafael Costa Almeida", "moema", "(11) 99231-4410"),
    ("juliana", "Juliana Ferreira Lima", "tatuape", "(11) 97654-1288"),
    ("lucas", "Lucas Pereira Rocha", "santana", "(11) 98877-0912"),
    ("camila", "Camila Rodrigues Souza", "perdizes", "(11) 99102-5576"),
    ("gabriel", "Gabriel Martins Ribeiro", "butanta", "(11) 97321-8840"),
    ("beatriz", "Beatriz Carvalho Gomes", "ipiranga", "(11) 98543-2219"),
    ("thiago", "Thiago Araújo Barbosa", "lapa", "(11) 99678-3301"),
    ("larissa", "Larissa Mendes Teixeira", "brooklin", "(11) 98765-4432"),
    ("felipe", "Felipe Nascimento Dias", "pinheiros", "(11) 99014-7765"),
    ("ana", "Ana Clara Moreira", "vila-mariana", "(11) 97412-0098"),
    ("bruno", "Bruno Cardoso Freitas", "tatuape", "(11) 98321-6654"),
    ("patricia", "Patrícia Lopes Vieira", "moema", "(11) 99555-1203"),
    ("rodrigo", "Rodrigo Azevedo Pinto", "perdizes", "(11) 98234-7781"),
    ("fernanda", "Fernanda Castro Monteiro", "cambui", "(19) 99187-3320"),
    ("diego", "Diego Batista Correia", "barao-geraldo", "(19) 98876-4417"),
    ("isabela", "Isabela Duarte Farias", "copacabana", "(21) 99432-8810"),
    ("pedro", "Pedro Henrique Cunha", "tijuca", "(21) 98123-5546"),
    ("leticia", "Letícia Ramos Nogueira", "botafogo", "(21) 97765-2231"),
    ("gustavo", "Gustavo Melo Fonseca", "savassi", "(31) 99654-7712"),
    ("amanda", "Amanda Rezende Prado", "pampulha", "(31) 98543-1167"),
    ("marcelo", "Marcelo Tavares Brito", "batel", "(41) 99876-3345"),
    ("vanessa", "Vanessa Kowalski Andrade", "agua-verde", "(41) 98712-6690"),
    ("eduardo", "Eduardo Siqueira Campos", "asa-sul", "(61) 99345-2278"),
    ("carolina", "Carolina Bezerra Lima", "asa-norte", "(61) 98234-9901"),
    ("henrique", "Henrique Schmidt Lopes", "moinhos", "(51) 99123-4456"),
    ("renata", "Renata Cavalcanti Melo", "boa-viagem", "(81) 99876-1123"),
    ("caio", "Caio Santana Brandão", "barra-salvador", "(71) 98654-3378"),
]

# Pedidos de compra: (comprador, categoria, título, descrição, preço mín, preço máx, raio km, dias atrás)
ANUNCIOS = [
    (
        "voce",
        "eletronicos",
        "iPhone 13 128GB",
        "Procuro iPhone 13 de 128GB, bateria acima de 85%, sem trincos na tela. Pode ter marcas leves de uso. Preferência por cor azul ou preta.",
        "2300",
        "2900",
        15,
        2,
    ),
    (
        "voce",
        "esportes",
        "Bicicleta aro 29 para trilha",
        "Quero uma MTB aro 29, quadro tamanho 17 ou 19, freio a disco hidráulico e câmbio 2x9 ou 1x12. Caloi Explorer, Oggi Big Wheel ou similar.",
        "1500",
        "3200",
        20,
        5,
    ),
    (
        "voce",
        "casa-jardim",
        "Sofá retrátil de 3 lugares",
        "Sofá retrátil e reclinável de 3 lugares, até 2,20 m de largura, tecido suede ou linho. Retiro em São Paulo.",
        "800",
        "1600",
        12,
        9,
    ),
    (
        "mariana",
        "informatica",
        "MacBook Air M1 8GB/256GB",
        "Busco MacBook Air M1 com 8GB de RAM e 256GB de SSD, ciclos de bateria abaixo de 300. Com carregador original.",
        "3500",
        "4300",
        25,
        1,
    ),
    (
        "mariana",
        "casa-jardim",
        "Geladeira frost free duplex",
        "Geladeira frost free duplex, de 400 a 480 litros, inox ou branca. Brastemp, Electrolux ou Consul. 110V.",
        "1800",
        "2800",
        15,
        6,
    ),
    (
        "rafael",
        "games",
        "PlayStation 5 com leitor de disco",
        "Procuro PS5 versão com leitor, de preferência com dois controles. Aceito modelo Slim.",
        "2800",
        "3500",
        20,
        3,
    ),
    (
        "rafael",
        "esportes",
        "Esteira ergométrica dobrável",
        "Esteira dobrável com velocidade até 14 km/h e inclinação. Até 150 kg de capacidade.",
        "1200",
        "2500",
        15,
        12,
    ),
    (
        "juliana",
        "eletronicos",
        "Smart TV 55 polegadas 4K",
        'Smart TV 55" 4K, de 2021 em diante. Samsung, LG ou TCL. Com controle e base originais.',
        "1800",
        "2600",
        20,
        4,
    ),
    (
        "juliana",
        "instrumentos",
        "Violão Yamaha C40 ou similar",
        "Violão clássico para iniciante, cordas de nylon. Yamaha C40, Giannini ou Di Giorgio.",
        "350",
        "700",
        10,
        7,
    ),
    (
        "lucas",
        "veiculos",
        "Honda CG 160 Fan",
        "Procuro CG 160 Fan de 2019 a 2022, até 40 mil km, documento em dia e sem leilão.",
        "11000",
        "15500",
        40,
        8,
    ),
    (
        "lucas",
        "games",
        "Nintendo Switch OLED",
        "Switch OLED desbloqueado não. Quero o original com dock e Joy-Cons funcionando sem drift.",
        "1600",
        "2100",
        20,
        2,
    ),
    (
        "camila",
        "informatica",
        "Monitor 27 polegadas QHD",
        'Monitor 27" QHD (2560x1440), IPS, 75Hz ou mais. LG, Dell ou AOC.',
        "900",
        "1500",
        15,
        3,
    ),
    (
        "camila",
        "casa-jardim",
        "Máquina de lavar 12kg",
        "Lavadora de 12 kg, abertura superior, com menos de 4 anos de uso. Retiro de carro.",
        "900",
        "1700",
        15,
        10,
    ),
    (
        "gabriel",
        "eletronicos",
        "Câmera Canon EOS Rebel T7",
        "Canon T7 ou T6i com lente 18-55. Contagem de cliques abaixo de 20 mil.",
        "1800",
        "2600",
        25,
        6,
    ),
    (
        "gabriel",
        "esportes",
        "Prancha de surf 6'2\"",
        "Prancha 6'2\" para intermediário, com quilhas FCS. Aceito com pequenos reparos.",
        "700",
        "1400",
        30,
        15,
    ),
    (
        "beatriz",
        "casa-jardim",
        "Mesa de jantar 6 lugares",
        "Mesa de madeira maciça para 6 pessoas, com ou sem cadeiras. Até 1,80 m.",
        "700",
        "1800",
        15,
        5,
    ),
    (
        "beatriz",
        "outros",
        "Carrinho de bebê travel system",
        "Travel system com bebê conforto. Burigotto, Galzerano ou Chicco. Bem conservado.",
        "500",
        "1100",
        15,
        2,
    ),
    (
        "thiago",
        "informatica",
        "Placa de vídeo RTX 3060 12GB",
        "RTX 3060 12GB, sem uso em mineração, com nota ou caixa. Gigabyte, Asus ou MSI.",
        "1300",
        "1800",
        30,
        1,
    ),
    (
        "thiago",
        "games",
        "Cadeira gamer ergonômica",
        "Cadeira gamer ou de escritório com apoio lombar e braço regulável. Até 120 kg.",
        "500",
        "1100",
        15,
        11,
    ),
    (
        "larissa",
        "eletronicos",
        "AirPods Pro 2ª geração",
        "AirPods Pro 2 originais, com estojo MagSafe. Com nota fiscal de preferência.",
        "900",
        "1400",
        15,
        3,
    ),
    (
        "larissa",
        "esportes",
        "Kit halteres e anilhas",
        "Kit com barra, halteres ajustáveis e anilhas até 40 kg no total.",
        "300",
        "700",
        15,
        8,
    ),
    (
        "felipe",
        "instrumentos",
        "Guitarra Fender Squier Stratocaster",
        "Squier Strato (Affinity ou Classic Vibe). Pode vir com amplificador pequeno.",
        "1200",
        "2800",
        20,
        4,
    ),
    (
        "felipe",
        "informatica",
        "Notebook Dell Inspiron i5 16GB",
        "Notebook i5 de 11ª geração ou mais, 16GB de RAM e SSD de 512GB. Para trabalho.",
        "2500",
        "3600",
        20,
        2,
    ),
    (
        "ana",
        "casa-jardim",
        "Cafeteira Nespresso",
        "Cafeteira Nespresso Essenza ou Inissia, 110V. Funcionando perfeitamente.",
        "250",
        "450",
        10,
        1,
    ),
    (
        "ana",
        "outros",
        "Bicicleta infantil aro 16",
        "Bicicleta aro 16 com rodinhas, para criança de 5 anos.",
        "200",
        "450",
        10,
        6,
    ),
    (
        "bruno",
        "veiculos",
        "Pneus aro 15 seminovos",
        "Jogo de 4 pneus 185/60 R15 com pelo menos 60% de borracha.",
        "600",
        "1100",
        15,
        9,
    ),
    (
        "bruno",
        "games",
        "Controle Xbox Series",
        "Controle original do Xbox Series, qualquer cor, sem drift.",
        "250",
        "380",
        15,
        1,
    ),
    (
        "patricia",
        "eletronicos",
        "Kindle Paperwhite",
        "Kindle Paperwhite 11ª geração com luz ajustável. Com capa se possível.",
        "450",
        "750",
        15,
        4,
    ),
    (
        "patricia",
        "casa-jardim",
        "Ar-condicionado split 12.000 BTUs",
        "Split inverter 12.000 BTUs, 220V, com menos de 3 anos. Sem a instalação.",
        "1500",
        "2400",
        20,
        13,
    ),
    (
        "rodrigo",
        "esportes",
        "Bicicleta speed alumínio",
        "Speed de alumínio, tamanho 54 ou 56, grupo Shimano Claris ou Sora.",
        "1800",
        "3500",
        25,
        7,
    ),
    (
        "fernanda",
        "informatica",
        "iPad 9ª geração 64GB",
        "iPad 9 de 64GB, Wi-Fi, para estudos. Com carregador.",
        "1500",
        "2100",
        20,
        3,
    ),
    (
        "diego",
        "instrumentos",
        "Teclado Yamaha PSR-E373",
        "Teclado de 61 teclas sensíveis ao toque, com fonte e suporte.",
        "800",
        "1300",
        25,
        5,
    ),
    (
        "isabela",
        "eletronicos",
        "Samsung Galaxy S22",
        "Galaxy S22 de 128GB, desbloqueado, sem marcas na tela.",
        "1500",
        "2200",
        15,
        2,
    ),
    (
        "pedro",
        "games",
        "Xbox Series S 512GB",
        "Series S com controle e fonte, de preferência na caixa.",
        "1500",
        "2000",
        20,
        4,
    ),
    (
        "leticia",
        "casa-jardim",
        "Guarda-roupa casal 6 portas",
        "Guarda-roupa de 6 portas com espelho, desmontado para transporte.",
        "600",
        "1400",
        15,
        8,
    ),
    (
        "gustavo",
        "veiculos",
        "Bagageiro de teto universal",
        "Rack de teto com barras transversais para carro hatch.",
        "300",
        "700",
        20,
        6,
    ),
    (
        "amanda",
        "informatica",
        "Impressora multifuncional tanque de tinta",
        "Epson EcoTank ou HP Smart Tank, Wi-Fi.",
        "600",
        "1100",
        20,
        3,
    ),
    (
        "marcelo",
        "esportes",
        "Barraca de camping 4 pessoas",
        "Barraca para 4 pessoas com sobreteto e coluna d'água acima de 2000 mm.",
        "300",
        "800",
        30,
        10,
    ),
    ("vanessa", "eletronicos", "Caixa de som JBL Charge 5", "JBL Charge 5 original, com cabo.", "550", "900", 20, 2),
    (
        "eduardo",
        "informatica",
        "Teclado mecânico switch marrom",
        "Teclado mecânico ABNT2, switch marrom, com fio ou sem fio.",
        "200",
        "500",
        20,
        1,
    ),
    ("carolina", "casa-jardim", "Air fryer 5 litros", "Air fryer de 4 a 5,5 litros, 127V.", "250", "500", 15, 5),
    (
        "henrique",
        "instrumentos",
        "Bateria eletrônica Roland",
        "Roland TD-1K ou TD-07, com banco e pedal.",
        "2500",
        "4500",
        30,
        9,
    ),
    ("renata", "eletronicos", "Apple Watch SE 44mm", "Apple Watch SE (2ª geração) 44mm, GPS.", "1100", "1600", 20, 3),
    ("caio", "esportes", "Stand up paddle inflável", "SUP inflável com remo, bomba e mochila.", "900", "1800", 30, 6),
]

# Produtos à venda: (vendedor, categoria, nome, descrição, estado, preço, dias atrás)
PRODUTOS = [
    (
        "felipe",
        "eletronicos",
        "iPhone 13 128GB azul",
        "Bateria em 88%, sempre com capinha e película. Acompanha caixa e cabo.",
        "usado_bom",
        "2650",
        3,
    ),
    (
        "felipe",
        "informatica",
        "Mouse Logitech MX Master 3S",
        "Usado por 6 meses, funcionando perfeitamente. Com receptor Bolt.",
        "seminovo",
        "480",
        5,
    ),
    (
        "ana",
        "esportes",
        "Bicicleta Caloi Explorer aro 29",
        "Quadro 17, freio a disco hidráulico, 2x9 Shimano Alivio. Revisada mês passado.",
        "usado_bom",
        "2400",
        2,
    ),
    (
        "ana",
        "casa-jardim",
        "Sofá retrátil 3 lugares cinza",
        "2,10 m, tecido suede, retrátil e reclinável. Sem rasgos ou manchas.",
        "usado_bom",
        "1250",
        6,
    ),
    (
        "bruno",
        "games",
        "PlayStation 5 com leitor + 2 controles",
        "Comprado em 2023, com caixa e nota. Dois controles DualSense.",
        "seminovo",
        "3200",
        1,
    ),
    (
        "bruno",
        "games",
        "Nintendo Switch OLED branco",
        "Joy-Cons sem drift, tela sem riscos. Acompanha dock e capa.",
        "seminovo",
        "1850",
        4,
    ),
    (
        "patricia",
        "eletronicos",
        'Smart TV LG 55" 4K UHD',
        "Modelo 2022, com controle Smart Magic e base original.",
        "usado_bom",
        "2200",
        3,
    ),
    (
        "patricia",
        "casa-jardim",
        "Geladeira Brastemp frost free 443L inox",
        "Duplex, 110V, 4 anos de uso. Funcionando muito bem.",
        "usado_marcas",
        "2300",
        8,
    ),
    (
        "rodrigo",
        "informatica",
        "MacBook Air M1 8GB 256GB",
        "142 ciclos de bateria, sem marcas. Carregador original.",
        "seminovo",
        "4100",
        2,
    ),
    (
        "rodrigo",
        "informatica",
        'Monitor LG 27" QHD IPS 75Hz',
        "Sem dead pixel, com cabo HDMI e DisplayPort.",
        "usado_bom",
        "1150",
        5,
    ),
    (
        "mariana",
        "eletronicos",
        "Canon EOS Rebel T7 + 18-55",
        "12 mil cliques, com bolsa, bateria extra e cartão de 64GB.",
        "seminovo",
        "2350",
        4,
    ),
    (
        "mariana",
        "instrumentos",
        "Violão Yamaha C40",
        "Pouquíssimo uso, cordas novas. Acompanha capa.",
        "seminovo",
        "560",
        7,
    ),
    (
        "rafael",
        "esportes",
        "Esteira Movement dobrável",
        "Velocidade até 16 km/h, inclinação manual. Pouco usada.",
        "usado_bom",
        "1900",
        9,
    ),
    (
        "rafael",
        "informatica",
        "Placa de vídeo RTX 3060 12GB Gigabyte",
        "Usada só para jogos, nunca minerou. Com caixa.",
        "usado_bom",
        "1550",
        2,
    ),
    (
        "juliana",
        "casa-jardim",
        "Mesa de jantar madeira maciça 6 lugares",
        "Mesa de 1,60 m em madeira de demolição, sem cadeiras.",
        "usado_marcas",
        "1100",
        6,
    ),
    (
        "juliana",
        "outros",
        "Travel system Burigotto Ecco",
        "Carrinho e bebê conforto, usado por um filho. Lavado.",
        "usado_bom",
        "850",
        3,
    ),
    (
        "lucas",
        "veiculos",
        "Honda CG 160 Fan 2020",
        "31 mil km, revisões na concessionária, documento 2026 pago.",
        "usado_bom",
        "13900",
        10,
    ),
    (
        "lucas",
        "games",
        "Controle Xbox Series preto",
        "Original, sem drift, com pilhas recarregáveis.",
        "usado_bom",
        "290",
        1,
    ),
    (
        "camila",
        "eletronicos",
        "AirPods Pro 2 com MagSafe",
        "Com nota fiscal, garantia até março. Pontas extras.",
        "seminovo",
        "1250",
        2,
    ),
    (
        "camila",
        "esportes",
        "Kit halteres ajustáveis 40kg",
        "Barra, dois halteres e anilhas de 1 a 5 kg.",
        "usado_bom",
        "520",
        7,
    ),
    (
        "gabriel",
        "instrumentos",
        "Squier Classic Vibe Stratocaster 60s",
        "Com bag e cabo. Regulada recentemente.",
        "usado_bom",
        "2600",
        4,
    ),
    (
        "gabriel",
        "informatica",
        "Notebook Dell Inspiron 15 i5 16GB 512GB",
        "11ª geração, bateria boa, Windows 11 original.",
        "usado_bom",
        "3100",
        3,
    ),
    (
        "beatriz",
        "casa-jardim",
        "Nespresso Inissia 110V",
        "Funcionando perfeitamente, com 20 cápsulas.",
        "usado_bom",
        "330",
        1,
    ),
    (
        "beatriz",
        "outros",
        "Bicicleta infantil aro 16 com rodinhas",
        "Rosa, com cestinha. Pneus novos.",
        "usado_bom",
        "290",
        5,
    ),
    ("thiago", "veiculos", "Jogo de 4 pneus 185/60 R15", "Pirelli P400, 70% de borracha.", "usado_bom", "880", 9),
    (
        "thiago",
        "games",
        "Cadeira gamer ThunderX3",
        "Apoio lombar e de pescoço, braço 2D. Sem rasgos.",
        "usado_marcas",
        "650",
        11,
    ),
    (
        "larissa",
        "eletronicos",
        "Kindle Paperwhite 11ª geração",
        "Com capa original. Tela perfeita.",
        "seminovo",
        "590",
        4,
    ),
    (
        "larissa",
        "casa-jardim",
        "Split inverter Samsung 12.000 BTUs 220V",
        "2 anos de uso, retirado por mudança. Sem instalação.",
        "usado_bom",
        "1950",
        12,
    ),
    (
        "voce",
        "esportes",
        "Bicicleta speed Caloi Strada tamanho 56",
        "Grupo Shimano Claris, alumínio. Pneus novos.",
        "usado_bom",
        "2900",
        5,
    ),
    ("voce", "eletronicos", "Kindle 10ª geração", "Com capa, pouco uso.", "usado_bom", "380", 3),
    (
        "fernanda",
        "informatica",
        "iPad 9ª geração 64GB Wi-Fi",
        "Com capa e película. Bateria em 91%.",
        "usado_bom",
        "1800",
        3,
    ),
    (
        "diego",
        "instrumentos",
        "Teclado Yamaha PSR-E373 com suporte",
        "Com fonte original e suporte em X.",
        "usado_bom",
        "1100",
        5,
    ),
    ("isabela", "eletronicos", "Galaxy S22 128GB verde", "Sem marcas, com carregador rápido.", "usado_bom", "1900", 2),
    ("pedro", "games", "Xbox Series S 512GB na caixa", "Com controle e cabo HDMI.", "seminovo", "1750", 4),
    (
        "leticia",
        "casa-jardim",
        "Guarda-roupa casal 6 portas com espelho",
        "Desmontado e etiquetado para montar.",
        "usado_marcas",
        "950",
        8,
    ),
    ("gustavo", "veiculos", "Rack de teto Thule para hatch", "Barras transversais e chave.", "usado_bom", "520", 6),
    ("amanda", "informatica", "Epson EcoTank L3250 Wi-Fi", "Com tintas pela metade.", "usado_bom", "850", 3),
    (
        "marcelo",
        "esportes",
        "Barraca Nautika 4 pessoas",
        "Coluna d'água 2500 mm, usada 3 vezes.",
        "usado_bom",
        "520",
        10,
    ),
    ("vanessa", "eletronicos", "JBL Charge 5 azul", "Com cabo USB-C, sem marcas.", "seminovo", "720", 2),
    (
        "eduardo",
        "informatica",
        "Redragon Kumara switch marrom",
        "ABNT2, todas as teclas funcionando.",
        "usado_bom",
        "230",
        1,
    ),
    ("carolina", "casa-jardim", "Air fryer Mondial 5L 127V", "Cesto sem descascar.", "usado_bom", "320", 5),
    ("henrique", "instrumentos", "Roland TD-07KV", "Com banco, pedal e baqueta.", "usado_bom", "4200", 9),
    ("renata", "eletronicos", "Apple Watch SE 2 44mm", "Bateria 96%, com pulseira extra.", "seminovo", "1400", 3),
    ("caio", "esportes", "SUP inflável 10'6\" com remo", "Completo, sem furos.", "usado_bom", "1350", 6),
]

AVALIACOES = [
    (5, "Negociação tranquila, produto exatamente como descrito. Recomendo!"),
    (5, "Muito atencioso e pontual na entrega. Tudo certo."),
    (4, "Deu tudo certo, só atrasou um pouco para responder."),
    (5, "Pessoa honesta, combinamos rápido e foi tudo como o combinado."),
    (4, "Produto em bom estado, com algumas marcas que já tinham sido avisadas."),
    (5, "Excelente! Comprador educado e pagamento na hora."),
]


class Command(BaseCommand):
    help = "Popula o banco de homologação com dados realistas (pessoas, anúncios, produtos e negociações)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--recriar",
            action="store_true",
            help="Apaga TODOS os dados do banco, inclusive contas criadas à mão, antes de popular.",
        )

    def handle(self, *args, recriar=False, **options):
        if not settings.DEBUG:
            raise CommandError("popular_banco só roda com DEBUG ligado: nunca use em produção.")

        if recriar:
            call_command("flush", interactive=False, verbosity=0)
        else:
            emails = [CONTA_DE_TESTE] + [f"{chave}@example.com" for chave, *_ in PESSOAS if chave != "voce"]
            if Usuario.objects.filter(email__in=emails).exists():
                raise CommandError("O banco já foi populado. Use --recriar para apagar TODO o banco e popular de novo.")

        random.seed(2026)
        with transaction.atomic():
            categorias = self._categorias()
            pessoas = self._pessoas()
            anuncios = self._anuncios(pessoas, categorias)
            produtos = self._produtos(pessoas, categorias)
            self._negociacoes(pessoas, anuncios, produtos)

        self.stdout.write(self.style.SUCCESS("Banco populado."))
        self.stdout.write(
            f"  {Usuario.objects.count()} pessoas, {Anuncio.objects.count()} anúncios, "
            f"{Produto.objects.count()} produtos, {Oferta.objects.count()} ofertas."
        )
        self.stdout.write(f"  Conta de teste: {CONTA_DE_TESTE} / {SENHA} (Pinheiros, São Paulo)")
        self.stdout.write("  Todas as outras contas usam a mesma senha, ex.: mariana@example.com")

    # ── Etapas ──────────────────────────────────────────────────────────────

    def _categorias(self):
        for slug, nome in CATEGORIAS:
            Categoria.objects.get_or_create(slug=slug, defaults={"nome": nome})
        return {categoria.slug: categoria for categoria in Categoria.objects.all()}

    def _pessoas(self):
        pessoas = {}
        hoje = timezone.now()
        for indice, (chave, nome, bairro, telefone) in enumerate(PESSOAS):
            _, cidade, uf, latitude, longitude = BAIRROS[bairro]
            # Espalha as pessoas do mesmo bairro em algumas quadras (~300 m).
            latitude += random.uniform(-0.003, 0.003)
            longitude += random.uniform(-0.003, 0.003)
            usuario = Usuario.objects.create_user(
                email=CONTA_DE_TESTE if chave == "voce" else f"{chave}@example.com",
                password=SENHA,
                nome=nome,
            )
            usuario.telefone = telefone
            usuario.cidade = cidade
            usuario.uf = uf
            usuario.ponto = Point(longitude, latitude, srid=4326)
            usuario.date_joined = hoje - timedelta(days=400 - indice * 9)
            usuario.save()
            pessoas[chave] = usuario
        return pessoas

    def _anuncios(self, pessoas, categorias):
        anuncios = {}
        agora = timezone.now()
        for comprador, categoria, titulo, descricao, minimo, maximo, raio_km, dias in ANUNCIOS:
            anuncio = Anuncio.objects.create(
                comprador=pessoas[comprador],
                categoria=categorias[categoria],
                titulo=titulo,
                descricao=descricao,
                preco_min=Decimal(minimo),
                preco_max=Decimal(maximo),
                raio_m=raio_km * 1000,
            )
            quando = agora - timedelta(days=dias, hours=random.randint(0, 20), minutes=random.randint(0, 59))
            Anuncio.objects.filter(pk=anuncio.pk).update(criado_em=quando, atualizado_em=quando)
            anuncios[titulo] = anuncio
        return anuncios

    def _produtos(self, pessoas, categorias):
        produtos = {}
        agora = timezone.now()
        for vendedor, categoria, nome, descricao, estado, preco, dias in PRODUTOS:
            produto = Produto.objects.create(
                vendedor=pessoas[vendedor],
                categoria=categorias[categoria],
                nome=nome,
                descricao=descricao,
                estado_conservacao=estado,
                preco=Decimal(preco),
            )
            quando = agora - timedelta(days=dias, hours=random.randint(0, 20))
            Produto.objects.filter(pk=produto.pk).update(criado_em=quando, atualizado_em=quando)
            produtos[nome] = produto
        return produtos

    def _ofertar(self, vendedor, anuncio, *, produto=None, preco=None, descricao="", estado="usado_bom"):
        dados = {"produto_id": produto.pk} if produto else {}
        if preco is not None:
            dados["preco"] = Decimal(preco)
        if descricao:
            dados["descricao"] = descricao
        if not produto:
            dados["estado_conservacao"] = estado
        return enviar_oferta(vendedor=vendedor, anuncio_id=anuncio.pk, dados=dados)

    def _concluir(self, oferta, comprador, vendedor, *, notas):
        aceitar_oferta(oferta_id=oferta.pk, comprador=comprador)
        negociacao = negociacao_da_oferta(Oferta.objects.get(pk=oferta.pk))
        enviar_mensagem(oferta=oferta, autor=comprador, texto="Combinado! Posso retirar no sábado de manhã?")
        enviar_mensagem(oferta=oferta, autor=vendedor, texto="Pode sim, te mando o endereço por aqui.")
        solicitar_conclusao(negociacao=negociacao, usuario=vendedor)
        confirmar_conclusao(negociacao=negociacao, usuario=comprador)
        nota_comprador, nota_vendedor = notas
        criar_avaliacao(
            autor=comprador, negociacao_id=negociacao.pk, nota=nota_comprador[0], comentario=nota_comprador[1]
        )
        criar_avaliacao(autor=vendedor, negociacao_id=negociacao.pk, nota=nota_vendedor[0], comentario=nota_vendedor[1])

    def _negociacoes(self, p, a, prod):
        # Ofertas recebidas pela conta de teste, para comparar e negociar.
        o1 = self._ofertar(p["felipe"], a["iPhone 13 128GB"], produto=prod["iPhone 13 128GB azul"])
        self._ofertar(
            p["rodrigo"],
            a["iPhone 13 128GB"],
            preco="2450",
            descricao="iPhone 13 128GB preto, bateria 84%, tela trocada na assistência autorizada.",
        )
        self._ofertar(
            p["camila"],
            a["iPhone 13 128GB"],
            preco="2790",
            estado="seminovo",
            descricao="iPhone 13 128GB rosa, 1 ano de uso, com nota fiscal e caixa.",
        )
        enviar_mensagem(
            oferta=o1, autor=p["felipe"], texto="Oi! A bateria está em 88% e mando foto da saúde da bateria se quiser."
        )
        enviar_mensagem(oferta=o1, autor=p["voce"], texto="Opa, manda sim! Aceita 2.450?")
        enviar_contraproposta(
            oferta_id=o1.pk, autor=p["voce"], preco=Decimal("2450"), texto="Consigo pagar à vista no Pix."
        )

        self._ofertar(p["ana"], a["Bicicleta aro 29 para trilha"], produto=prod["Bicicleta Caloi Explorer aro 29"])
        self._ofertar(
            p["gabriel"],
            a["Bicicleta aro 29 para trilha"],
            preco="1900",
            descricao="Oggi Big Wheel 7.0 tamanho 19, 2x9, freio hidráulico. Algumas marcas no quadro.",
            estado="usado_marcas",
        )
        self._ofertar(p["ana"], a["Sofá retrátil de 3 lugares"], produto=prod["Sofá retrátil 3 lugares cinza"])

        # Ofertas enviadas pela conta de teste, como vendedora.
        oferta_speed = self._ofertar(
            p["voce"], a["Bicicleta speed alumínio"], produto=prod["Bicicleta speed Caloi Strada tamanho 56"]
        )
        enviar_mensagem(oferta=oferta_speed, autor=p["rodrigo"], texto="Ela tem algum risco no quadro?")
        enviar_mensagem(oferta=oferta_speed, autor=p["voce"], texto="Só um pequeno no pedivela, mando foto.")
        self._ofertar(p["voce"], a["Kindle Paperwhite"], produto=prod["Kindle 10ª geração"], preco="420")

        # Negociação em andamento da conta de teste (venda aceita, falta concluir).
        oferta_halteres = self._ofertar(
            p["voce"],
            a["Kit halteres e anilhas"],
            preco="450",
            descricao="Barra W, dois halteres e anilhas de 2 a 5 kg, total de 36 kg.",
        )
        aceitar_oferta(oferta_id=oferta_halteres.pk, comprador=p["larissa"])
        enviar_mensagem(oferta=oferta_halteres, autor=p["larissa"], texto="Fechado! Pode ser quinta à noite?")

        # Vendas concluídas e avaliadas: dão histórico e reputação a várias pessoas.
        concluidas = [
            ("bruno", "rafael", "PlayStation 5 com leitor de disco", "PlayStation 5 com leitor + 2 controles"),
            ("rodrigo", "mariana", "MacBook Air M1 8GB/256GB", "MacBook Air M1 8GB 256GB"),
            ("patricia", "juliana", "Smart TV 55 polegadas 4K", 'Smart TV LG 55" 4K UHD'),
            ("rafael", "thiago", "Placa de vídeo RTX 3060 12GB", "Placa de vídeo RTX 3060 12GB Gigabyte"),
            ("mariana", "gabriel", "Câmera Canon EOS Rebel T7", "Canon EOS Rebel T7 + 18-55"),
            ("felipe", "camila", "Monitor 27 polegadas QHD", None),
            ("camila", "larissa", "AirPods Pro 2ª geração", "AirPods Pro 2 com MagSafe"),
            ("gabriel", "felipe", "Notebook Dell Inspiron i5 16GB", "Notebook Dell Inspiron 15 i5 16GB 512GB"),
            ("beatriz", "ana", "Cafeteira Nespresso", "Nespresso Inissia 110V"),
        ]
        for indice, (vendedor, comprador, titulo, produto) in enumerate(concluidas):
            if produto:
                oferta = self._ofertar(p[vendedor], a[titulo], produto=prod[produto])
            else:
                oferta = self._ofertar(
                    p[vendedor],
                    a[titulo],
                    preco="1200",
                    descricao='Dell S2721DGF 27" QHD 165Hz, sem dead pixel.',
                )
            notas = (AVALIACOES[indice % len(AVALIACOES)], AVALIACOES[(indice + 3) % len(AVALIACOES)])
            self._concluir(oferta, p[comprador], p[vendedor], notas=notas)

        # Algumas ofertas abertas entre outras pessoas, para o feed parecer vivo.
        for vendedor, titulo, produto in [
            ("bruno", "Nintendo Switch OLED", "Nintendo Switch OLED branco"),
            ("thiago", "Pneus aro 15 seminovos", "Jogo de 4 pneus 185/60 R15"),
            ("lucas", "Controle Xbox Series", "Controle Xbox Series preto"),
            ("juliana", "Carrinho de bebê travel system", "Travel system Burigotto Ecco"),
            ("mariana", "Violão Yamaha C40 ou similar", "Violão Yamaha C40"),
        ]:
            self._ofertar(p[vendedor], a[titulo], produto=prod[produto])
