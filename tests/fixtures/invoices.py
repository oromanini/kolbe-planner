"""Fixtures sintéticas de fatura, montadas a partir de três arquétipos de layout.

Não há faturas reais no repositório e não deve haver: são dados pessoais. Estes
textos foram escritos à mão reproduzindo as armadilhas observadas em faturas
reais de Itaú, Nubank e Neon:

* Itaú — um lançamento por linha, mais uma seção "Total para próximas faturas"
  que não pertence a esta fatura.
* Nubank — lançamento em bloco multilinha, com "Total a pagar" repetido com
  significados diferentes, parcelamento em que o valor desta fatura é a última
  linha do bloco, divergência de arredondamento de um centavo entre a
  explicação e o valor lançado, e estorno com menos Unicode (U+2212).
* Neon — texto corrido com valores rotulados.

Cada fixture carrega o texto de entrada e o documento que uma leitura correta
produz, no contrato de saída da IA. Os testes usam esse documento como resposta
mockada do Groq: o que está sob teste é o contrato e a conferência aritmética,
não o modelo.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class InvoiceFixture:
    name: str
    raw_text: str
    ai_document: dict
    anchor_label: str
    anchor_total: float
    # (descrição, valor) dos itens que devem virar gastos.
    expected_purchases: Tuple[Tuple[str, float], ...]
    expected_status: str
    # Valores que existem no documento mas não podem virar gasto.
    forbidden_amounts: Tuple[float, ...] = field(default=())


def format_brl(value: float) -> str:
    """Formata como o texto das faturas: 1584.5 -> "1.584,50"."""
    formatted = f"{abs(value):,.2f}"
    return formatted.replace(",", "@").replace(".", ",").replace("@", ".")


# --------------------------------------------------------------------------
# Arquétipo Itaú: uma linha por lançamento + seção de próximas faturas.
# --------------------------------------------------------------------------

ITAU_TEXT = """BANCO ITAÚ UNIBANCO S.A.
Fatura do cartão final 4321
Vencimento 10/08/2026

Total desta fatura R$ 426,80
Pagamento mínimo R$ 63,00

Lançamentos: compras e saques
24/07 AuroraApple    13/18 150,00
25/07 Padaria Central       80,30
26/07 Posto Avenida        196,50

Total para próximas faturas R$ 300,00
AuroraApple 14/18 150,00
AuroraApple 15/18 150,00
"""

ITAU_DOCUMENT = {
    "issuer": "Itaú",
    "doc_type": "fatura_cartao",
    "period": "2026-08",
    "due_date": "2026-08-10",
    "totals": [
        {"label_original": "Total desta fatura", "value": 426.80},
        {"label_original": "Pagamento mínimo", "value": 63.00},
        {"label_original": "Total para próximas faturas", "value": 300.00},
    ],
    "reconciliation_anchor": {
        "label_original": "Total desta fatura",
        "value": 426.80,
        "reason": "É o total dos lançamentos desta fatura; 'Total para próximas faturas' é de competências futuras.",
    },
    "items": [
        {
            "date": "2026-07-24",
            "description": "AuroraApple 13/18",
            "amount": 150.00,
            "type": "parcela",
        },
        {
            "date": "2026-07-25",
            "description": "Padaria Central",
            "amount": 80.30,
            "type": "compra",
        },
        {
            "date": "2026-07-26",
            "description": "Posto Avenida",
            "amount": 196.50,
            "type": "compra",
        },
    ],
    "confidence": 0.95,
    "summary": "parece ser uma fatura de cartão do Itaú com 3 lançamentos",
}

ITAU = InvoiceFixture(
    name="itau_linha_unica",
    raw_text=ITAU_TEXT,
    ai_document=ITAU_DOCUMENT,
    anchor_label="Total desta fatura",
    anchor_total=426.80,
    expected_purchases=(
        ("AuroraApple 13/18", 150.00),
        ("Padaria Central", 80.30),
        ("Posto Avenida", 196.50),
    ),
    expected_status="ok",
    forbidden_amounts=(300.00, 63.00),
)


# Mesma fatura, com a IA puxando junto as parcelas de "próximas faturas".
# O subset-sum precisa devolver o subconjunto que bate com a âncora.
ITAU_OVEREXTRACTED_DOCUMENT = {
    **ITAU_DOCUMENT,
    "items": ITAU_DOCUMENT["items"]
    + [
        {
            "date": "2026-08-24",
            "description": "AuroraApple 14/18",
            "amount": 150.00,
            "type": "parcela",
        },
        {
            "date": "2026-09-24",
            "description": "AuroraApple 15/18",
            "amount": 150.00,
            "type": "parcela",
        },
    ],
    "summary": "parece ser uma fatura de cartão do Itaú com 5 lançamentos",
}

ITAU_OVEREXTRACTED = InvoiceFixture(
    name="itau_com_proximas_faturas",
    raw_text=ITAU_TEXT,
    ai_document=ITAU_OVEREXTRACTED_DOCUMENT,
    anchor_label="Total desta fatura",
    anchor_total=426.80,
    expected_purchases=(
        ("AuroraApple 13/18", 150.00),
        ("Padaria Central", 80.30),
        ("Posto Avenida", 196.50),
    ),
    expected_status="adjusted",
    forbidden_amounts=(300.00,),
)


# --------------------------------------------------------------------------
# Arquétipo Nubank: bloco multilinha, "Total a pagar" ambíguo, parcelamento,
# arredondamento de um centavo e estorno com menos Unicode.
# --------------------------------------------------------------------------

NUBANK_TEXT = """NU PAGAMENTOS S.A. - Instituição de Pagamento
Fatura de agosto de 2026
Vencimento: 10 AGO 2026

Total a pagar
R$ 407,14

RESUMO
Fatura anterior
R$ 1.200,00
Pagamento em 05 JUL
−R$ 1.200,00
Total de compras de todos os cartões
R$ 452,14
Total a pagar
R$ 407,14

TRANSAÇÕES
01 AGO
 •••• 4321 Servico Online *Xy12ab34
USD 12.97
Conversão: USD 1 = R$ 5,28
R$ 68,49

11 JUL
 POSTO EXEMPLO
 Total a pagar: R$ 177,98 (valor da transação de R$ 156,90 + R$ 1,55 de IOF +
R$ 19,53 de juros).
R$ 177,98

05 AGO
 MERCADO SAO JOSE - Parcela 2 de 6
 Total a pagar: R$ 201,18 (valor da transação de R$ 195,00 + R$ 6,18 de juros).
R$ 33,53

07 AGO
 ASSINATURA STREAM
 Total a pagar: R$ 172,13 (valor da transação de R$ 168,00 + R$ 4,13 de IOF).
R$ 172,14

02 AGO
 ESTORNO LOJA DEZ
−R$ 45,00
"""

NUBANK_DOCUMENT = {
    "issuer": "Nubank",
    "doc_type": "fatura_cartao",
    "period": "2026-08",
    "due_date": "2026-08-10",
    "totals": [
        {"label_original": "Total a pagar", "value": 407.14},
        {"label_original": "Fatura anterior", "value": 1200.00},
        {"label_original": "Pagamento em 05 JUL", "value": -1200.00},
        {"label_original": "Total de compras de todos os cartões", "value": 452.14},
    ],
    "reconciliation_anchor": {
        "label_original": "Total de compras de todos os cartões",
        "value": 452.14,
        "reason": "'Total a pagar' já desconta o estorno; o total de compras é a soma dos lançamentos.",
    },
    "items": [
        {
            "date": "2026-08-01",
            "description": "Servico Online *Xy12ab34",
            "amount": 68.49,
            "type": "compra",
            "original_currency": "USD",
        },
        {
            # O valor lançado é a última linha do bloco, não os números da
            # explicação (156,90 + 1,55 + 19,53).
            "date": "2026-07-11",
            "description": "POSTO EXEMPLO",
            "amount": 177.98,
            "type": "compra",
        },
        {
            # Parcelamento: vale a parcela desta fatura, não o total de 201,18.
            "date": "2026-08-05",
            "description": "MERCADO SAO JOSE - Parcela 2 de 6",
            "amount": 33.53,
            "type": "parcela",
        },
        {
            # A explicação diz 172,13 e o valor lançado é 172,14: vale o lançado.
            "date": "2026-08-07",
            "description": "ASSINATURA STREAM",
            "amount": 172.14,
            "type": "compra",
        },
        {
            # Estorno escrito com U+2212, não com hífen ASCII.
            "date": "2026-08-02",
            "description": "ESTORNO LOJA DEZ",
            "amount": -45.00,
            "type": "estorno",
        },
    ],
    "confidence": 0.9,
    "summary": "parece ser uma fatura de cartão do Nubank com 4 compras e 1 estorno",
}

NUBANK = InvoiceFixture(
    name="nubank_bloco_multilinha",
    raw_text=NUBANK_TEXT,
    ai_document=NUBANK_DOCUMENT,
    anchor_label="Total de compras de todos os cartões",
    anchor_total=452.14,
    expected_purchases=(
        ("Servico Online *Xy12ab34", 68.49),
        ("POSTO EXEMPLO", 177.98),
        ("MERCADO SAO JOSE - Parcela 2 de 6", 33.53),
        ("ASSINATURA STREAM", 172.14),
    ),
    expected_status="ok",
    # Números que aparecem no texto mas são explicação, total a pagar ou crédito.
    forbidden_amounts=(407.14, 1200.00, 201.18, 195.00, 156.90, 172.13, 45.00),
)


# --------------------------------------------------------------------------
# Arquétipo Neon: texto corrido com valores rotulados.
# --------------------------------------------------------------------------

NEON_TEXT = """NEON PAGAMENTOS S.A.
Fatura do cartão final 9911 - competência 08/2026 - vencimento em 15/08/2026.
Total de compras feitas no cartão R$ 29,80
Encargos e IOF cobrados nesta fatura R$ 0,27
Total a pagar nesta fatura R$ 30,07
Lançamentos do período 24/07 UBER *TRIP R$ 12,48 25/07 HOSTINGER.COM R$ 7,59
26/07 PADARIA DO ZE R$ 9,73 28/07 IOF - HOSTINGER.COM R$ 0,27
Limite total do cartão R$ 2.500,00
"""

NEON_ITEMS = [
    {
        "date": "2026-07-24",
        "description": "UBER *TRIP",
        "amount": 12.48,
        "type": "compra",
    },
    {
        "date": "2026-07-25",
        "description": "HOSTINGER.COM",
        "amount": 7.59,
        "type": "compra",
    },
    {
        "date": "2026-07-26",
        "description": "PADARIA DO ZE",
        "amount": 9.73,
        "type": "compra",
    },
    {
        "date": "2026-07-28",
        "description": "IOF - HOSTINGER.COM",
        "amount": 0.27,
        "type": "iof",
    },
]

NEON_TOTALS = [
    {"label_original": "Total de compras feitas no cartão", "value": 29.80},
    {"label_original": "Encargos e IOF cobrados nesta fatura", "value": 0.27},
    {"label_original": "Total a pagar nesta fatura", "value": 30.07},
    {"label_original": "Limite total do cartão", "value": 2500.00},
]

NEON_DOCUMENT = {
    "issuer": "Neon",
    "doc_type": "fatura_cartao",
    "period": "2026-08",
    "due_date": "2026-08-15",
    "totals": NEON_TOTALS,
    "reconciliation_anchor": {
        "label_original": "Total de compras feitas no cartão",
        "value": 29.80,
        "reason": "É o total das compras; o total a pagar soma o IOF.",
    },
    "items": NEON_ITEMS,
    "confidence": 0.88,
    "summary": "parece ser uma fatura de cartão da Neon com 3 compras e 1 cobrança de IOF",
}

NEON = InvoiceFixture(
    name="neon_texto_corrido",
    raw_text=NEON_TEXT,
    ai_document=NEON_DOCUMENT,
    anchor_label="Total de compras feitas no cartão",
    anchor_total=29.80,
    expected_purchases=(
        ("UBER *TRIP", 12.48),
        ("HOSTINGER.COM", 7.59),
        ("PADARIA DO ZE", 9.73),
    ),
    expected_status="ok",
    forbidden_amounts=(30.07, 2500.00, 0.27),
)


# Mesma fatura com a âncora no total a pagar: as compras ficam 0,27 abaixo e o
# IOF explica exatamente a diferença.
NEON_GAP_DOCUMENT = {
    **NEON_DOCUMENT,
    "reconciliation_anchor": {
        "label_original": "Total a pagar nesta fatura",
        "value": 30.07,
        "reason": "Único total de lançamentos identificado no documento.",
    },
}

NEON_GAP = InvoiceFixture(
    name="neon_gap_coberto_por_iof",
    raw_text=NEON_TEXT,
    ai_document=NEON_GAP_DOCUMENT,
    anchor_label="Total a pagar nesta fatura",
    anchor_total=30.07,
    expected_purchases=(
        ("UBER *TRIP", 12.48),
        ("HOSTINGER.COM", 7.59),
        ("PADARIA DO ZE", 9.73),
    ),
    expected_status="gap_covered",
    forbidden_amounts=(2500.00, 30.07, 0.27),
)


ALL_FIXTURES: List[InvoiceFixture] = [
    ITAU,
    ITAU_OVEREXTRACTED,
    NUBANK,
    NEON,
    NEON_GAP,
]

FIXTURES_BY_NAME: Dict[str, InvoiceFixture] = {
    fixture.name: fixture for fixture in ALL_FIXTURES
}
