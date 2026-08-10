"""Motor de extração de faturas baseado em LLM (Groq).

Não há mais parsing por padrão de banco. O texto extraído do PDF vai inteiro
para o modelo, que devolve um documento estruturado; o código valida o contrato
e faz a conferência aritmética de forma genérica, comparando a soma dos itens de
compra com a âncora de conciliação escolhida pelo modelo.
"""

import os
import re
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - depende de como o app é iniciado
    from backend import groq_client
except ImportError:  # o Dockerfile roda `uvicorn server:app` de dentro de backend/
    import groq_client


INVOICE_ITEM_TYPES = (
    "compra",
    "parcela",
    "iof",
    "juros",
    "anuidade",
    "pagamento",
    "estorno",
    "ajuste",
)

# Itens que compõem o total de compras conciliado.
PURCHASE_ITEM_TYPES = frozenset({"compra", "parcela"})
# Encargos que podem explicar a diferença entre compras e o total do documento.
CHARGE_ITEM_TYPES = frozenset({"iof", "juros", "anuidade", "ajuste"})
# Créditos: sempre negativos, nunca entram na conciliação de compras.
CREDIT_ITEM_TYPES = frozenset({"pagamento", "estorno"})

# O free tier da Groq limita tokens por minuto; uma fatura em texto gasta
# ~1.700-2.900 tokens, então este teto é folgado e evita estourar o limite com
# PDFs anômalos.
DEFAULT_MAX_INVOICE_CHARS = 24000

INVOICE_SCHEMA_NAME = "documento_fatura"

INVOICE_DOCUMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "issuer": {"type": "string"},
        "doc_type": {"type": "string"},
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
    "Você não usa regras fixas por banco: lê o documento como um humano leria, "
    "pelo texto e pelos rótulos que ele mesmo usa. Nunca invente valores."
)

INVOICE_USER_PROMPT_TEMPLATE = """Abaixo está o texto de um documento financeiro extraído de um PDF, na ordem de leitura. Normalmente é uma fatura de cartão de crédito.

Responda apenas com um objeto JSON com estes campos:

- issuer: o emissor do documento, como ele se identifica (ex.: "Nubank", "Itaú", "Neon").
- doc_type: o tipo do documento (ex.: "fatura_cartao").
- period: o período/competência da fatura, se houver.
- due_date: a data de vencimento, se houver.
- totals: TODOS os totais que aparecerem no documento, cada um com label_original (o rótulo textual exato como está escrito) e value (número).
- reconciliation_anchor: qual dos totals é o total de COMPRAS/LANÇAMENTOS desta fatura, com label_original, value e reason (por que esse é o total de compras).
- items: um item por lançamento desta fatura, com date, description, amount, type e, quando houver, original_currency.
- confidence: 0 a 1.
- summary: uma frase em português descrevendo o documento (ex.: "parece ser uma fatura de cartão do Nubank com 23 compras").

Regras de leitura:

1. O mesmo rótulo pode aparecer várias vezes com significados diferentes. Use o contexto ao redor, não a primeira ocorrência.
2. A âncora de conciliação é o total das compras/lançamentos desta fatura. NÃO use o "total a pagar" quando existir um total de compras separado: o total a pagar costuma incluir saldo anterior, encargos, pagamentos e estornos.
3. Um lançamento pode ocupar várias linhas (data, cartão, valor em moeda estrangeira, conversão, explicação e valor). O amount é o valor que efetivamente cai NESTA fatura, que costuma ser o último valor do bloco.
4. Texto explicativo dentro do bloco (ex.: "valor da transação de R$ ... + R$ ... de IOF + R$ ... de juros") descreve a composição do lançamento. Não transforme essas parcelas em itens separados e não use esses números como amount.
5. Em compras parceladas, o amount é o valor da parcela desta fatura, não o valor total da compra.
6. Se a explicação e o valor lançado divergirem por centavos (arredondamento), vale o valor lançado.
7. Sinal negativo pode vir como "-" ou como "−" (U+2212). Estornos e pagamentos são créditos e devem ter amount negativo.
8. Não inclua lançamentos de faturas futuras (seções como "próximas faturas", "parcelas a vencer", "lançamentos futuros") nem informações de limite, saldo devedor ou composição do pagamento mínimo.
9. type deve ser um de: {types}. Use "parcela" para uma parcela de compra parcelada, "compra" para compra à vista, e os demais para encargos, pagamentos, estornos e ajustes.
10. Não agrupe, não some e não deduplique lançamentos: dois lançamentos iguais no mesmo dia são dois itens.

Texto do documento:
---
{raw_text}
---
"""


def build_invoice_user_prompt(raw_text: str, *, max_chars: Optional[int] = None) -> str:
    limit = max_chars if max_chars is not None else get_max_invoice_chars()
    snippet = (raw_text or "")[:limit]
    return INVOICE_USER_PROMPT_TEMPLATE.format(
        types=", ".join(INVOICE_ITEM_TYPES), raw_text=snippet
    )


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
        "doc_type": _clean_text(payload.get("doc_type")),
        "period": _clean_text(payload.get("period")),
        "due_date": _clean_text(payload.get("due_date")),
        "totals": totals,
        "reconciliation_anchor": anchor,
        "items": items,
        "confidence": round(confidence, 4),
        "summary": _clean_text(payload.get("summary")),
    }


def extract_invoice_document(
    raw_text: str, *, model: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Pede o documento estruturado ao Groq e devolve o contrato normalizado."""
    if not (raw_text or "").strip():
        return None

    payload = groq_client.request_json(
        system_prompt=INVOICE_SYSTEM_PROMPT,
        user_prompt=build_invoice_user_prompt(raw_text),
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


def reconcile_invoice_document(document: Dict[str, Any]) -> Dict[str, Any]:
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
