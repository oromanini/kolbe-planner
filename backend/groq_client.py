"""Cliente mínimo para a API da Groq (compatível com OpenAI em /openai/v1).

Restrições da plataforma que moldam este cliente:

* A Groq **não aceita PDF nativo**. Só texto ou imagens. Por isso o motor de
  faturas envia o texto já extraído do PDF (pypdf preserva a ordem de leitura),
  e não o arquivo.
* Visão (escalonamento futuro): no máximo 5 imagens por requisição e 4MB por
  imagem em base64. Não é usado aqui.
* Free tier: 30 requisições/minuto e 6.000-30.000 tokens/minuto conforme o
  modelo, no nível da organização. Uma fatura em texto gasta ~1.700-2.900
  tokens, o que cabe com folga em uma requisição.

Sobre structured output: a Groq expõe `response_format` no padrão OpenAI, mas o
suporte a `json_schema` varia por modelo e há relatos de modelos que aceitam o
parâmetro e ignoram o schema. Por isso este cliente tenta `json_schema`, cai
para `json_object` (JSON mode) quando a API rejeita o formato, e **sempre**
devolve o JSON cru para o chamador validar contra o schema em código.
"""

import json
import logging
import os
import re
import time
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_CHAT_COMPLETIONS_PATH = "/chat/completions"

# Modelo padrão. `openai/gpt-oss-120b` é o substituto recomendado pela Groq nas
# depreciações de 2026 (Kimi K2, Qwen 3 32B, Llama 4 Scout/Maverick) e é o
# modelo de texto de uso geral disponível hoje no free tier.
DEFAULT_GROQ_INVOICE_MODEL = "openai/gpt-oss-120b"

# Modelo multimodal, para o escalonamento por visão (fase seguinte).
DEFAULT_GROQ_VISION_MODEL = "qwen/qwen3.6-27b"

GROQ_MAX_IMAGES_PER_REQUEST = 5
GROQ_MAX_BASE64_IMAGE_BYTES = 4 * 1024 * 1024

GROQ_REQUEST_TIMEOUT_SECONDS = 60

RESPONSE_FORMAT_AUTO = "auto"
RESPONSE_FORMAT_JSON_SCHEMA = "json_schema"
RESPONSE_FORMAT_JSON_OBJECT = "json_object"

# Códigos que indicam "esse modelo/rota não aceita o response_format pedido".
_UNSUPPORTED_FORMAT_STATUS = {400, 404, 415, 422}

# Códigos que pedem para tentar de novo, não para mudar de formato. O free tier
# limita a 30 requisições/minuto e 6.000-30.000 tokens/minuto no nível da
# organização, então um lote de documentos bate em 429 com facilidade.
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

DEFAULT_GROQ_MAX_RETRIES = 3
DEFAULT_GROQ_RETRY_BASE_SECONDS = 2.0
GROQ_MAX_RETRY_DELAY_SECONDS = 30.0


# O secret usado no GitHub Actions se chama GROQ_KEY; aceitamos os dois nomes
# para a chave valer igual no deploy e no ambiente local.
GROQ_API_KEY_ENV_VARS = ("GROQ_API_KEY", "GROQ_KEY")


def get_groq_api_key() -> str:
    for env_var in GROQ_API_KEY_ENV_VARS:
        key = (os.getenv(env_var) or "").strip()
        if key:
            return key
    return ""


def get_groq_model() -> str:
    return (
        os.getenv("GROQ_INVOICE_MODEL") or DEFAULT_GROQ_INVOICE_MODEL
    ).strip() or DEFAULT_GROQ_INVOICE_MODEL


def get_chat_model() -> str:
    return (
        os.getenv("GROQ_CHAT_MODEL") or get_groq_model()
    ).strip() or get_groq_model()


def get_response_format_mode() -> str:
    mode = (os.getenv("GROQ_INVOICE_RESPONSE_FORMAT") or RESPONSE_FORMAT_AUTO).strip()
    if mode not in {
        RESPONSE_FORMAT_AUTO,
        RESPONSE_FORMAT_JSON_SCHEMA,
        RESPONSE_FORMAT_JSON_OBJECT,
    }:
        return RESPONSE_FORMAT_AUTO
    return mode


def is_groq_configured() -> bool:
    return bool(get_groq_api_key())


def build_response_format(mode: str, schema: dict, schema_name: str) -> dict:
    if mode == RESPONSE_FORMAT_JSON_OBJECT:
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {"name": schema_name, "strict": True, "schema": schema},
    }


def _response_format_attempts(mode: str) -> List[str]:
    if mode == RESPONSE_FORMAT_JSON_SCHEMA:
        return [RESPONSE_FORMAT_JSON_SCHEMA]
    if mode == RESPONSE_FORMAT_JSON_OBJECT:
        return [RESPONSE_FORMAT_JSON_OBJECT]
    return [RESPONSE_FORMAT_JSON_SCHEMA, RESPONSE_FORMAT_JSON_OBJECT]


def extract_message_content(body: dict) -> str:
    """Lê o texto da primeira choice de uma resposta chat/completions."""
    for choice in (body or {}).get("choices", []) or []:
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        # Alguns modelos devolvem content como lista de blocos.
        if isinstance(content, list):
            joined = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict)
                and block.get("type") in {"text", "output_text"}
            )
            if joined.strip():
                return joined
    return ""


def parse_json_object(text: str) -> Optional[dict]:
    """Converte a resposta em dict, tolerando cercas de código e texto ao redor.

    JSON mode não garante um objeto limpo, então isso precisa ser defensivo.
    """
    candidate = (text or "").strip()
    if not candidate:
        return None

    fenced = re.search(r"```(?:json)?\s*(.+?)```", candidate, flags=re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return None

    return parsed if isinstance(parsed, dict) else None


_VERDICT_OK = "ok"
_VERDICT_NEXT_MODE = "next_mode"
_VERDICT_GIVE_UP = "give_up"


def get_max_retries() -> int:
    raw_value = (os.getenv("GROQ_MAX_RETRIES") or "").strip()
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_GROQ_MAX_RETRIES
    return max(0, value)


def _sleep(seconds: float) -> None:
    """Isolado para os testes não dormirem de verdade."""
    time.sleep(seconds)


def retry_delay_seconds(response, attempt: int) -> float:
    """Respeita o Retry-After da Groq; sem ele, backoff exponencial."""
    headers = getattr(response, "headers", None) or {}
    for header in ("Retry-After", "retry-after"):
        raw_value = headers.get(header) if hasattr(headers, "get") else None
        if raw_value is None:
            continue
        try:
            return min(max(float(raw_value), 0.0), GROQ_MAX_RETRY_DELAY_SECONDS)
        except (TypeError, ValueError):
            # Retry-After também aceita data HTTP; nesse caso cai no backoff.
            break
    delay = DEFAULT_GROQ_RETRY_BASE_SECONDS * (2**attempt)
    return min(delay, GROQ_MAX_RETRY_DELAY_SECONDS)


def _request_with_retries(
    requests_module, payload: dict, api_key: str, timeout: int, mode: str
) -> Tuple[Optional[dict], str]:
    """Uma tentativa de formato, com retentativas para 429 e erros transitórios.

    O 429 é um problema de cota, não de formato: repetir a mesma requisição em
    JSON mode só gastaria uma segunda chamada de uma conta já limitada. Por isso
    o rate limit retenta o MESMO modo e, se não passar, desiste.
    """
    max_retries = get_max_retries()

    for attempt in range(max_retries + 1):
        try:
            response = requests_module.post(
                f"{GROQ_BASE_URL}{GROQ_CHAT_COMPLETIONS_PATH}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            status_code = getattr(response, "status_code", None)

            if (
                mode == RESPONSE_FORMAT_JSON_SCHEMA
                and status_code in _UNSUPPORTED_FORMAT_STATUS
            ):
                logger.warning(
                    "Groq recusou response_format json_schema (HTTP %s); "
                    "repetindo em JSON mode.",
                    status_code,
                )
                return None, _VERDICT_NEXT_MODE

            if status_code in _RETRYABLE_STATUS:
                if attempt >= max_retries:
                    logger.warning(
                        "Groq segue indisponível (HTTP %s) após %s tentativas.",
                        status_code,
                        attempt + 1,
                    )
                    return None, _VERDICT_GIVE_UP
                delay = retry_delay_seconds(response, attempt)
                logger.warning(
                    "Groq respondeu HTTP %s; nova tentativa em %.1fs.",
                    status_code,
                    delay,
                )
                _sleep(delay)
                continue

            response.raise_for_status()
            body = response.json()
        except Exception as exc:  # rede, HTTP ou corpo inválido
            # Erro de rede não é retentado aqui: sem status não dá para saber se
            # é transitório, e insistir multiplicaria a chamada pelos dois
            # formatos. Quem retenta o documento inteiro é o usuário.
            if mode == RESPONSE_FORMAT_JSON_SCHEMA:
                logger.warning("Falha na chamada Groq com json_schema: %s", exc)
                return None, _VERDICT_NEXT_MODE
            logger.warning("Falha na chamada Groq: %s", exc)
            return None, _VERDICT_GIVE_UP

        parsed = parse_json_object(extract_message_content(body))
        if parsed is not None:
            return parsed, _VERDICT_OK
        if mode == RESPONSE_FORMAT_JSON_SCHEMA:
            logger.warning("Resposta da Groq não era JSON; repetindo em JSON mode.")
            return None, _VERDICT_NEXT_MODE
        return None, _VERDICT_GIVE_UP

    return None, _VERDICT_GIVE_UP


def request_json(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    schema_name: str,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_completion_tokens: int = 8192,
    timeout: int = GROQ_REQUEST_TIMEOUT_SECONDS,
) -> Optional[dict]:
    """Pede um objeto JSON ao modelo e devolve o dict cru (sem validar schema).

    Devolve None quando não há chave configurada, quando a chamada falha ou
    quando a resposta não é um objeto JSON. A validação do contrato é
    responsabilidade do chamador — `json_schema` não é garantido em todo modelo.
    """
    api_key = get_groq_api_key()
    if not api_key:
        return None

    import requests

    base_payload = {
        "model": (model or get_groq_model()),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_completion_tokens": max_completion_tokens,
    }

    for mode in _response_format_attempts(get_response_format_mode()):
        payload = dict(base_payload)
        payload["response_format"] = build_response_format(mode, schema, schema_name)
        parsed, verdict = _request_with_retries(
            requests, payload, api_key, timeout, mode
        )
        if verdict == _VERDICT_OK:
            return parsed
        if verdict == _VERDICT_NEXT_MODE:
            continue
        return None

    return None


ALLOWED_CHAT_ROLES = {"system", "user", "assistant"}


def request_chat(
    *,
    messages: List[dict],
    model: Optional[str] = None,
    temperature: float = 0.4,
    max_completion_tokens: int = 1024,
    timeout: int = GROQ_REQUEST_TIMEOUT_SECONDS,
) -> Optional[str]:
    """Chat de texto livre (sem ``response_format``).

    ``messages`` segue o padrão OpenAI: ``[{"role": ..., "content": ...}]``.
    Devolve o texto da resposta, ou ``None`` quando não há chave configurada,
    quando a chamada falha ou quando a resposta vem vazia. Diferente de
    ``request_json``, aqui um 429/5xx é retentado no mesmo formato (não há outro
    formato para onde cair).
    """
    api_key = get_groq_api_key()
    if not api_key:
        return None

    sanitized = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("role") in ALLOWED_CHAT_ROLES and (m.get("content") or "").strip()
    ]
    if not sanitized:
        return None

    import requests

    payload = {
        "model": (model or get_chat_model()),
        "messages": sanitized,
        "temperature": temperature,
        "max_completion_tokens": max_completion_tokens,
    }

    max_retries = get_max_retries()
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(
                f"{GROQ_BASE_URL}{GROQ_CHAT_COMPLETIONS_PATH}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            status_code = getattr(response, "status_code", None)

            if status_code in _RETRYABLE_STATUS:
                if attempt >= max_retries:
                    logger.warning(
                        "Groq chat segue indisponível (HTTP %s) após %s tentativas.",
                        status_code,
                        attempt + 1,
                    )
                    return None
                delay = retry_delay_seconds(response, attempt)
                logger.warning(
                    "Groq chat respondeu HTTP %s; nova tentativa em %.1fs.",
                    status_code,
                    delay,
                )
                _sleep(delay)
                continue

            response.raise_for_status()
            body = response.json()
        except Exception as exc:  # rede, HTTP ou corpo inválido
            logger.warning("Falha na chamada de chat da Groq: %s", exc)
            return None

        content = (extract_message_content(body) or "").strip()
        return content or None

    return None
