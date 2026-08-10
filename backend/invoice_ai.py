"""Motor de extração de documentos financeiros baseado em LLM (Groq).

Não há parsing por padrão de banco nem por emissor. O texto extraído do PDF vai
inteiro para o modelo, que classifica o documento e devolve uma estrutura; o
código valida o contrato e faz a conferência aritmética.

O documento pode ser uma fatura de cartão ou uma conta de cobrança única (luz,
água, gás, condomínio, internet/telefone, boleto). O ``doc_type`` decide o
regime de conciliação:

* ``fatura_cartao``  — muitos lançamentos; a âncora é o total de compras e a
  soma dos itens de compra tem que bater com ela.
* cobrança única     — existe um valor a pagar; a âncora é esse total e os
  componentes listados (consumo, iluminação pública, tributos, juros) têm que
  somar exatamente esse valor.

Nos dois regimes a conferência é aritmética, em centavos inteiros, e divergência
continua sendo divergência: quem materializa gasto é o chamador, e só quando o
status for conciliado.
"""

import os
import re
import unicodedata
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - depende de como o app é iniciado
    from backend import groq_client
except ImportError:  # o Dockerfile roda `uvicorn server:app` de dentro de backend/
    import groq_client


INVOICE_ITEM_TYPES = (
    "compra",
    "parcela",
    "componente",
    "iof",
    "juros",
    "anuidade",
    "pagamento",
    "estorno",
    "desconto",
    "ajuste",
)

# Itens que compõem o total de compras conciliado (regime de cartão).
PURCHASE_ITEM_TYPES = frozenset({"compra", "parcela"})
# Encargos que podem explicar a diferença entre compras e o total do documento.
CHARGE_ITEM_TYPES = frozenset({"iof", "juros", "anuidade", "ajuste"})
# Créditos: sempre negativos, nunca entram na conciliação de compras.
CREDIT_ITEM_TYPES = frozenset({"pagamento", "estorno", "desconto"})


# --------------------------------------------------------------------------
# Tipos de documento e regimes de conciliação
# --------------------------------------------------------------------------

DOC_TYPE_CARD = "fatura_cartao"
DOC_TYPE_OTHER = "outro"

DOC_TYPES = (
    DOC_TYPE_CARD,
    "conta_luz",
    "conta_agua",
    "conta_gas",
    "condominio",
    "internet_telefone",
    "boleto",
    DOC_TYPE_OTHER,
)

# Rótulos em português, usados no parecer e no nome do gasto materializado.
DOC_TYPE_LABELS = {
    DOC_TYPE_CARD: "Fatura de cartão",
    "conta_luz": "Conta de luz",
    "conta_agua": "Conta de água",
    "conta_gas": "Conta de gás",
    "condominio": "Condomínio",
    "internet_telefone": "Internet/telefone",
    "boleto": "Boleto",
    DOC_TYPE_OTHER: "Documento",
}

# Categoria de despesa usada quando a IA não sugere nenhuma.
DOC_TYPE_DEFAULT_CATEGORY = {
    "conta_luz": "Luz",
    "conta_agua": "Água",
    "conta_gas": "Gás",
    "condominio": "Condomínio",
    "internet_telefone": "Internet e telefone",
    "boleto": "Boletos",
    DOC_TYPE_OTHER: "Outros",
}

# O que a IA costuma responder quando escapa do vocabulário pedido.
DOC_TYPE_SYNONYMS = {
    "cartao": DOC_TYPE_CARD,
    "cartao_de_credito": DOC_TYPE_CARD,
    "fatura": DOC_TYPE_CARD,
    "fatura_de_cartao": DOC_TYPE_CARD,
    "fatura_de_cartao_de_credito": DOC_TYPE_CARD,
    "credit_card": DOC_TYPE_CARD,
    "luz": "conta_luz",
    "energia": "conta_luz",
    "conta_de_luz": "conta_luz",
    "conta_de_energia": "conta_luz",
    "conta_energia": "conta_luz",
    "energia_eletrica": "conta_luz",
    "agua": "conta_agua",
    "conta_de_agua": "conta_agua",
    "agua_e_esgoto": "conta_agua",
    "saneamento": "conta_agua",
    "gas": "conta_gas",
    "conta_de_gas": "conta_gas",
    "taxa_de_condominio": "condominio",
    "internet": "internet_telefone",
    "telefone": "internet_telefone",
    "telecom": "internet_telefone",
    "internet_e_telefone": "internet_telefone",
    "tv_internet_telefone": "internet_telefone",
    "boleto_avulso": "boleto",
    "boleto_bancario": "boleto",
}

# Regime "muitos lançamentos conciliados contra o total de compras".
REGIME_CARD = "fatura_cartao"
# Regime "um valor a pagar, com componentes que somam esse valor".
REGIME_SINGLE_CHARGE = "cobranca_unica"

# O free tier da Groq limita tokens por minuto; uma fatura em texto gasta
# ~1.700-2.900 tokens, então este teto é folgado e evita estourar o limite com
# PDFs anômalos.
DEFAULT_MAX_INVOICE_CHARS = 24000

INVOICE_SCHEMA_NAME = "documento_fatura"

INVOICE_DOCUMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "issuer": {"type": "string"},
        "doc_type": {"type": "string", "enum": list(DOC_TYPES)},
        "suggested_category": {"type": "string"},
        "period": {"type": "string"},
        "due_date": {"type": "string"},
        "totals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label_original": {"type": "string"},
                    "value": {"type": "number"},
                },
                "required": ["label_original", "value"],
                "additionalProperties": False,
            },
        },
        "reconciliation_anchor": {
            "type": "object",
            "properties": {
                "label_original": {"type": "string"},
                "value": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["label_original", "value", "reason"],
            "additionalProperties": False,
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                    "type": {"type": "string", "enum": list(INVOICE_ITEM_TYPES)},
                    "original_currency": {"type": "string"},
                },
                "required": ["date", "description", "amount", "type"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
    },
    "required": [
        "issuer",
        "doc_type",
        "suggested_category",
        "totals",
        "reconciliation_anchor",
        "items",
        "confidence",
        "summary",
    ],
    "additionalProperties": False,
}

INVOICE_SYSTEM_PROMPT = (
    "Você lê documentos financeiros brasileiros e devolve JSON estruturado. "
    "O documento pode ser uma fatura de cartão de crédito ou uma conta de "
    "cobrança única (luz, água, gás, condomínio, internet/telefone, boleto). "
    "Você não usa regras fixas por emissor: lê o documento como um humano "
    "leria, pelo texto e pelos rótulos que ele mesmo usa. Nunca invente valores."
)

INVOICE_USER_PROMPT_TEMPLATE = """Abaixo está o texto de um documento financeiro brasileiro extraído de um PDF, na ordem de leitura. Pode ser uma fatura de cartão de crédito, uma conta de luz, de água, de gás, de condomínio, de internet/telefone, ou um boleto avulso. Descubra pelo próprio texto qual é.

Responda apenas com um objeto JSON com estes campos:

- issuer: o emissor do documento, como ele se identifica (ex.: "Nubank", "CPFL", "Sabesp").
- doc_type: um de {doc_types}. Use "fatura_cartao" só quando o documento for mesmo uma fatura de cartão de crédito, com vários lançamentos de compras. Use "outro" apenas quando nenhum dos demais servir.
- suggested_category: a categoria de despesa em que este documento deve entrar no orçamento do usuário, em português e no singular (ex.: "Luz", "Água", "Condomínio", "Internet"). Para fatura de cartão, sugira a categoria pelo emissor.
- period: o período/competência do documento, se houver.
- due_date: a data de vencimento, se houver.
- totals: TODOS os totais que aparecerem no documento, cada um com label_original (o rótulo textual exato como está escrito) e value (número).
- reconciliation_anchor: o total contra o qual a soma dos items tem que fechar, com label_original, value e reason (por que é esse total). Veja as regras do tipo de documento abaixo.
- items: os itens do documento, com date, description, amount, type e, quando houver, original_currency.
- confidence: 0 a 1.
- summary: uma frase em português dizendo o que o documento parece ser, que será mostrada ao usuário para ele aprovar ou contestar (ex.: "parece ser uma fatura de luz da CPFL de julho, no valor de R$ 187,40").

Regras gerais de leitura:

1. O mesmo rótulo pode aparecer várias vezes com significados diferentes. Use o contexto ao redor, não a primeira ocorrência.
2. Sinal negativo pode vir como "-" ou como "−" (U+2212). Créditos (pagamentos, estornos, descontos) devem ter amount negativo.
3. type deve ser um de: {types}.
4. Não agrupe, não some e não deduplique itens: dois itens iguais são dois itens.
5. Nunca invente um valor que não esteja escrito no documento. Se não achar, deixe o campo de fora.
6. Ignore medições que não são dinheiro (kWh, m³), limites de crédito, histórico de meses anteriores e valores hipotéticos de "pagamento após o vencimento".

Se o documento for uma FATURA DE CARTÃO (doc_type = "fatura_cartao"):

7. items é um item por lançamento desta fatura.
8. A âncora de conciliação é o total das COMPRAS/LANÇAMENTOS desta fatura. NÃO use o "total a pagar" quando existir um total de compras separado: o total a pagar costuma incluir saldo anterior, encargos, pagamentos e estornos.
9. Um lançamento pode ocupar várias linhas (data, cartão, valor em moeda estrangeira, conversão, explicação e valor). O amount é o valor que efetivamente cai NESTA fatura, que costuma ser o último valor do bloco.
10. Texto explicativo dentro do bloco (ex.: "valor da transação de R$ ... + R$ ... de IOF + R$ ... de juros") descreve a composição do lançamento. Não transforme essas parcelas em itens separados e não use esses números como amount.
11. Em compras parceladas, o amount é o valor da parcela desta fatura, não o valor total da compra. Use type "parcela"; use "compra" para compra à vista.
12. Se a explicação e o valor lançado divergirem por centavos (arredondamento), vale o valor lançado.
13. Não inclua lançamentos de faturas futuras (seções como "próximas faturas", "parcelas a vencer", "lançamentos futuros") nem informações de limite, saldo devedor ou composição do pagamento mínimo.

Se o documento for uma CONTA DE COBRANÇA ÚNICA (qualquer outro doc_type: luz, água, gás, condomínio, internet/telefone, boleto):

14. Existe UM valor a pagar. A âncora de conciliação é esse valor a pagar total do documento — o que o usuário efetivamente paga nesta competência.
15. items é o detalhamento desse valor: consumo, iluminação pública, tributos, taxas, juros, multa, desconto. Use type "componente" para as linhas de composição da conta.
16. A soma dos items tem que ser exatamente igual à âncora. Se o documento não detalhar a composição, devolva um único item com o valor total e a descrição do serviço.
17. Não inclua na soma valores de outras competências, saldo anterior já pago, nem o valor com multa por atraso quando ele for uma alternativa ao valor a pagar.

Texto do documento:
---
{raw_text}
---
"""

INVOICE_FEEDBACK_TEMPLATE = """
ATENÇÃO — leitura anterior contestada pelo usuário.

Você já leu este documento e o usuário revisou o resultado e discordou. O que ele respondeu, na ordem em que respondeu:

{feedback}

A correção do usuário vale mais que a sua leitura anterior: ele está olhando o documento. Releia o texto do zero considerando o que ele disse — inclusive o doc_type, a categoria sugerida e a âncora de conciliação, se for o caso. Continue sem inventar valores que não estejam escritos no documento.
"""


def build_invoice_user_prompt(
    raw_text: str,
    *,
    max_chars: Optional[int] = None,
    feedback: Optional[List[str]] = None,
) -> str:
    limit = max_chars if max_chars is not None else get_max_invoice_chars()
    snippet = (raw_text or "")[:limit]
    prompt = INVOICE_USER_PROMPT_TEMPLATE.format(
        types=", ".join(INVOICE_ITEM_TYPES),
        doc_types=", ".join(DOC_TYPES),
        raw_text=snippet,
    )

    messages = [str(entry or "").strip() for entry in feedback or []]
    messages = [message for message in messages if message]
    if not messages:
        return prompt

    numbered = "\n".join(
        f"{index}. {message}" for index, message in enumerate(messages, start=1)
    )
    return prompt + INVOICE_FEEDBACK_TEMPLATE.format(feedback=numbered)


def get_max_invoice_chars() -> int:
    raw_value = (os.getenv("GROQ_INVOICE_MAX_CHARS") or "").strip()
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_MAX_INVOICE_CHARS
    return value if value > 0 else DEFAULT_MAX_INVOICE_CHARS


def parse_amount(raw_value: Any) -> Optional[float]:
    """Converte valores em número, aceitando float, "R$ 1.584,50" e "−45,00"."""
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, (int, float)):
        return float(raw_value)

    candidate = str(raw_value or "").strip()
    if not candidate:
        return None

    # U+2212 (menos matemático) e travessões usados como sinal negativo.
    candidate = candidate.replace("−", "-").replace("–", "-")

    first_digit = next(
        (idx for idx, char in enumerate(candidate) if char.isdigit()), None
    )
    if first_digit is None:
        return None
    prefix = candidate[:first_digit]
    negative = "-" in prefix or "(" in prefix

    normalized = re.sub(r"[^0-9,.]", "", candidate)
    if not normalized:
        return None

    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    elif normalized.count(".") > 1:
        normalized = normalized.replace(".", "")

    try:
        value = float(normalized)
    except ValueError:
        return None
    return -value if negative else value


def to_cents(value: float) -> int:
    return int(round(float(value) * 100))


def clean_description(name: str) -> str:
    cleaned = (name or "").replace("→", " ").replace("•", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -\n\t")
    return cleaned


def _clean_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def slugify(value: Any) -> str:
    """ "Conta de Luz" -> "conta_de_luz"; usado para casar o doc_type da IA."""
    text = str(value or "").strip()
    if not text:
        return ""
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    slug = re.sub(r"[^a-z0-9]+", "_", without_accents.casefold())
    return slug.strip("_")


def normalize_doc_type(raw_value: Any) -> str:
    """Reduz o que a IA respondeu ao vocabulário fechado de DOC_TYPES."""
    slug = slugify(raw_value)
    if slug in DOC_TYPES:
        return slug
    return DOC_TYPE_SYNONYMS.get(slug, DOC_TYPE_OTHER)


def document_regime(document: Any) -> str:
    """O doc_type decide o regime de conciliação (e de materialização)."""
    doc_type = normalize_doc_type((document or {}).get("doc_type"))
    return REGIME_CARD if doc_type == DOC_TYPE_CARD else REGIME_SINGLE_CHARGE


def default_category_for_doc_type(doc_type: Any, issuer: Optional[str] = None) -> str:
    """Categoria de fallback quando a IA não sugere nenhuma."""
    normalized = normalize_doc_type(doc_type)
    if normalized == DOC_TYPE_CARD:
        return f"Cartão {issuer}".strip() if issuer else "Cartão de crédito"
    return DOC_TYPE_DEFAULT_CATEGORY.get(normalized, "Outros")


def normalize_invoice_item(entry: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None

    description = clean_description(str(entry.get("description", "")))
    amount = parse_amount(entry.get("amount"))
    if not description or amount is None or amount == 0:
        return None

    item_type = str(entry.get("type", "") or "").strip().casefold()
    if item_type not in INVOICE_ITEM_TYPES:
        item_type = "compra"

    if item_type in CREDIT_ITEM_TYPES:
        amount = -abs(amount)
    elif item_type in PURCHASE_ITEM_TYPES and amount < 0:
        # Uma "compra" negativa é, na prática, um crédito de volta.
        item_type = "estorno"

    return {
        "date": _clean_text(entry.get("date")),
        "description": description,
        "amount": round(amount, 2),
        "type": item_type,
        "original_currency": _clean_text(entry.get("original_currency")),
    }


def normalize_totals(raw_totals: Any) -> List[Dict[str, Any]]:
    totals = []
    for entry in raw_totals or []:
        if not isinstance(entry, dict):
            continue
        label = _clean_text(entry.get("label_original"))
        value = parse_amount(entry.get("value"))
        if not label or value is None:
            continue
        totals.append({"label_original": label, "value": round(value, 2)})
    return totals


def normalize_anchor(
    raw_anchor: Any, totals: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_anchor, dict):
        return None

    label = _clean_text(raw_anchor.get("label_original"))
    value = parse_amount(raw_anchor.get("value"))
    reason = _clean_text(raw_anchor.get("reason"))

    if value is None and label:
        match = next(
            (
                total
                for total in totals
                if total["label_original"].casefold() == label.casefold()
            ),
            None,
        )
        if match:
            value = match["value"]

    if value is None or value <= 0:
        return None

    return {
        "label_original": label,
        "value": round(value, 2),
        "reason": reason,
    }


def normalize_invoice_document(payload: Any) -> Optional[Dict[str, Any]]:
    """Valida o contrato de saída da IA. Devolve None se não for aproveitável."""
    if not isinstance(payload, dict):
        return None

    items = [
        normalized
        for normalized in (
            normalize_invoice_item(entry) for entry in payload.get("items") or []
        )
        if normalized
    ]
    if not items:
        return None

    totals = normalize_totals(payload.get("totals"))
    anchor = normalize_anchor(payload.get("reconciliation_anchor"), totals)

    confidence = parse_amount(payload.get("confidence"))
    if confidence is None:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        "issuer": _clean_text(payload.get("issuer")),
        "doc_type": normalize_doc_type(payload.get("doc_type")),
        "suggested_category": _clean_text(payload.get("suggested_category")),
        "period": _clean_text(payload.get("period")),
        "due_date": _clean_text(payload.get("due_date")),
        "totals": totals,
        "reconciliation_anchor": anchor,
        "items": items,
        "confidence": round(confidence, 4),
        "summary": _clean_text(payload.get("summary")),
    }


def extract_invoice_document(
    raw_text: str,
    *,
    model: Optional[str] = None,
    feedback: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Pede o documento estruturado ao Groq e devolve o contrato normalizado.

    ``feedback`` carrega as contestações do usuário sobre leituras anteriores
    deste mesmo documento, na ordem em que ele as escreveu.
    """
    if not (raw_text or "").strip():
        return None

    payload = groq_client.request_json(
        system_prompt=INVOICE_SYSTEM_PROMPT,
        user_prompt=build_invoice_user_prompt(raw_text, feedback=feedback),
        schema=INVOICE_DOCUMENT_SCHEMA,
        schema_name=INVOICE_SCHEMA_NAME,
        model=model,
    )
    if payload is None:
        return None
    return normalize_invoice_document(payload)


def split_items_by_type(items: List[dict]) -> Dict[str, List[dict]]:
    purchases = [item for item in items if item.get("type") in PURCHASE_ITEM_TYPES]
    charges = [
        item
        for item in items
        if item.get("type") in CHARGE_ITEM_TYPES and item.get("amount", 0) > 0
    ]
    credits = [item for item in items if item.get("type") in CREDIT_ITEM_TYPES]
    return {"purchases": purchases, "charges": charges, "credits": credits}


def sum_amounts(items: List[dict]) -> float:
    return round(sum(float(item.get("amount", 0) or 0) for item in items), 2)


def select_items_matching_expected_total(
    items: List[dict], expected_total: Optional[float]
) -> Optional[List[dict]]:
    """Subset-sum em centavos, para quando a IA extrai itens a mais.

    Continua útil quando o modelo puxa uma seção de lançamentos futuros junto
    com os desta fatura: a soma passa do total e existe um subconjunto exato.
    """
    if expected_total is None or not items:
        return None

    target_cents = to_cents(expected_total)
    item_cents = [to_cents(max(float(item.get("amount", 0) or 0), 0)) for item in items]
    parsed_cents = sum(item_cents)
    if parsed_cents == target_cents:
        return items
    if target_cents <= 0 or parsed_cents < target_cents:
        return None

    reachable = {0: None}
    for idx, cents in enumerate(item_cents):
        if cents <= 0:
            continue
        for total in sorted(reachable.keys(), reverse=True):
            new_total = total + cents
            if new_total > target_cents or new_total in reachable:
                continue
            reachable[new_total] = (total, idx)
        if target_cents in reachable:
            break

    if target_cents not in reachable:
        return None

    selected_indices = set()
    cursor = target_cents
    while cursor:
        previous = reachable.get(cursor)
        if previous is None:
            return None
        cursor, idx = previous
        selected_indices.add(idx)

    if len(selected_indices) == len(items):
        return items
    return [item for idx, item in enumerate(items) if idx in selected_indices]


RECONCILED_STATUSES = frozenset({"ok", "adjusted", "gap_covered"})


def reconcile_invoice_document(document: Dict[str, Any]) -> Dict[str, Any]:
    """Confere a aritmética do documento no regime que o ``doc_type`` pede.

    Fatura de cartão confere a soma dos lançamentos de compra contra o total de
    compras; conta de cobrança única confere a soma dos componentes contra o
    valor a pagar. Os dois devolvem o mesmo formato de resultado, e em nenhum
    dos dois a conferência é pulada.
    """
    if document_regime(document) == REGIME_CARD:
        return reconcile_card_invoice(document)
    return reconcile_single_charge_document(document)


def reconcile_single_charge_document(document: Dict[str, Any]) -> Dict[str, Any]:
    """Confere a soma dos componentes contra o valor a pagar, em centavos.

    Status possíveis:

    * ``ok``        — os componentes somam exatamente o valor a pagar (um
      componente só também é um caso desta soma).
    * ``no_anchor`` — a IA não identificou o valor a pagar do documento.
    * ``mismatch``  — não bateu.
    """
    items = list((document or {}).get("items") or [])
    anchor = (document or {}).get("reconciliation_anchor") or None
    anchor_total = anchor.get("value") if anchor else None
    components_total = sum_amounts(items)

    result = {
        "regime": REGIME_SINGLE_CHARGE,
        "status": "mismatch",
        "anchor_total": anchor_total,
        "anchor_label": anchor.get("label_original") if anchor else None,
        # No regime de cobrança única os "itens de compra" são os componentes
        # do valor a pagar; o formato do resultado é o mesmo dos dois lados.
        "purchase_items": items,
        "purchase_total": components_total,
        "charge_items": [],
        "charge_total": 0.0,
        "gap": 0.0,
    }

    if anchor_total is None:
        result["status"] = "no_anchor"
        return result

    if not items:
        result["gap"] = round(anchor_total, 2)
        return result

    gap_cents = to_cents(anchor_total) - to_cents(components_total)
    if gap_cents == 0:
        result["status"] = "ok"
        return result

    result["gap"] = round(gap_cents / 100, 2)
    return result


def reconcile_card_invoice(document: Dict[str, Any]) -> Dict[str, Any]:
    """Confere soma(compra + parcela) contra a âncora, em centavos inteiros.

    Status possíveis:

    * ``ok``          — a soma bate com a âncora.
    * ``adjusted``    — a soma passava da âncora e um subconjunto exato bateu.
    * ``gap_covered`` — a soma ficou abaixo e os encargos explicam a diferença.
    * ``no_anchor``   — a IA não indicou um total de compras para conciliar.
    * ``mismatch``    — não bateu.
    """
    items = list((document or {}).get("items") or [])
    groups = split_items_by_type(items)
    purchases = groups["purchases"]
    charges = groups["charges"]

    anchor = (document or {}).get("reconciliation_anchor") or None
    anchor_total = anchor.get("value") if anchor else None

    result = {
        "regime": REGIME_CARD,
        "status": "mismatch",
        "anchor_total": anchor_total,
        "anchor_label": anchor.get("label_original") if anchor else None,
        "purchase_items": purchases,
        "purchase_total": sum_amounts(purchases),
        "charge_items": charges,
        "charge_total": sum_amounts(charges),
        "gap": 0.0,
    }

    if anchor_total is None:
        result["status"] = "no_anchor"
        return result

    if not purchases:
        result["gap"] = round(anchor_total, 2)
        return result

    anchor_cents = to_cents(anchor_total)
    purchase_cents = to_cents(result["purchase_total"])

    if purchase_cents == anchor_cents:
        result["status"] = "ok"
        return result

    if purchase_cents > anchor_cents:
        selected = select_items_matching_expected_total(purchases, anchor_total)
        if selected:
            result["status"] = "adjusted"
            result["purchase_items"] = selected
            result["purchase_total"] = sum_amounts(selected)
            return result
        result["gap"] = round(anchor_total - result["purchase_total"], 2)
        return result

    gap_cents = anchor_cents - purchase_cents
    result["gap"] = round(gap_cents / 100, 2)
    if charges and to_cents(result["charge_total"]) == gap_cents:
        result["status"] = "gap_covered"
    return result
