import requests
import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime
from dotenv import load_dotenv
import urllib3

from prompt_registry import get_prompt_metadata

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# .env dosyasındaki değişkenleri yükle
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SAKA_API_KEY = os.getenv("SAKA_API_KEY", "")
QWEN_RCA_MODEL_ID = os.getenv("QWEN_RCA_MODEL_ID", "ai-genai__qwen35-122b-a10b-awq-ai-genai")
# Qwen deployment can require a distinct gateway credential. Keep it separate
# while preserving SAKA_API_KEY as a backwards-compatible fallback.
QWEN_RCA_API_KEY = os.getenv("QWEN_RCA_API_KEY", SAKA_API_KEY)
QWEN_RCA_URL = os.getenv(
    "QWEN_RCA_URL",
    "https://common-inference-apis.turkcelltech.ai/qwen35-122b-a10b-awq-ai-genai/v1/chat/completions",
)

MODELS_CONFIG = {
    "Ajan_1_Triyaj": {
        "provider": "saka",
        "url": "https://common-inference-apis.turkcelltech.ai/llm-dynamo-deepseek-v4-flash-0731/v1/chat/completions",
        "key": SAKA_API_KEY,
        "model_id": "deepseek-v4-flash-0731"
    },
    # Multiline segmentation için aynı yerel/kurumsal inference modeli kullanılır.
    # Discovery ve refinement bilinçli olarak ayrı agent key'leridir; böylece daha
    # sonra farklı modellerle A/B test etmek mümkündür.
    "Segmentation_Discovery": {
        "provider": "saka",
        "url": "https://common-inference-apis.turkcelltech.ai/llm-dynamo-deepseek-v4-flash-0731/v1/chat/completions",
        "key": SAKA_API_KEY,
        "model_id": "deepseek-v4-flash-0731"
    },
    "Segmentation_Refinement": {
        "provider": "saka",
        "url": "https://common-inference-apis.turkcelltech.ai/llm-dynamo-deepseek-v4-flash-0731/v1/chat/completions",
        "key": SAKA_API_KEY,
        "model_id": "deepseek-v4-flash-0731"
    },
    "Causal_Graph_Judge": {
        "provider": "saka",
        "url": "https://common-inference-apis.turkcelltech.ai/llm-dynamo-deepseek-v4-flash-0731/v1/chat/completions",
        "key": SAKA_API_KEY,
        "model_id": "deepseek-v4-flash-0731"
    },
    "Incident_Correlation_Judge": {
        "provider": "saka",
        "url": "https://common-inference-apis.turkcelltech.ai/llm-dynamo-deepseek-v4-flash-0731/v1/chat/completions",
        "key": SAKA_API_KEY,
        "model_id": "deepseek-v4-flash-0731"
    },
    "Segmentation_Critic": {
        "provider": "saka",
        "url": QWEN_RCA_URL,
        "key": QWEN_RCA_API_KEY,
        "model_id": QWEN_RCA_MODEL_ID
    },
    "Ajan_2_RCA_Expert": {
        "provider": "saka", # local yerine saka yaptık
        "url": QWEN_RCA_URL,
        "key": QWEN_RCA_API_KEY,
        "model_id": QWEN_RCA_MODEL_ID
    },
    # Slow expert model: used primarily for final RCA, and only as an
    # escalation path for unresolved high-value causal decisions.
    "Ajan_2_Causal_Expert": {
        "provider": "saka",
        "url": QWEN_RCA_URL,
        "key": QWEN_RCA_API_KEY,
        "model_id": QWEN_RCA_MODEL_ID
    },
    # Backward-compatible alias for existing CLI/UI configurations.
    "Ajan_2_RCA_AgirTop": {
        "provider": "saka",
        "url": QWEN_RCA_URL,
        "key": QWEN_RCA_API_KEY,
        "model_id": QWEN_RCA_MODEL_ID
    },
    "Ajan_2_RCA_Hizli": {
        "provider": "openai",
        "url": "https://api.openai.com/v1/chat/completions",
        "key": OPENAI_API_KEY,
        "model_id": "gpt-4o-mini" 
    },
    "Claude-3": {
        "provider": "anthropic",
        "url": "https://api.anthropic.com/v1/messages",
        "key": ANTHROPIC_API_KEY,
        "model_id": "claude-3-haiku-20240307"
    }
}



AI_CACHE_PATH = os.getenv("AIOPS_AI_CACHE_PATH", "data/.aiops_ai_cache.sqlite3")
AI_CACHE_ENABLED = os.getenv("AIOPS_AI_CACHE_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
AI_CACHE_TTL_SECONDS = max(0, int(os.getenv("AIOPS_AI_CACHE_TTL_SECONDS", str(30 * 24 * 3600))))
AI_CACHE_MAX_ENTRIES = max(100, int(os.getenv("AIOPS_AI_CACHE_MAX_ENTRIES", "2000")))
AI_CACHE_MAX_BYTES = max(1024 * 1024, int(os.getenv("AIOPS_AI_CACHE_MAX_BYTES", str(50 * 1024 * 1024))))
AI_CACHE_EVICTION_EVERY_WRITES = max(1, int(os.getenv("AIOPS_AI_CACHE_EVICTION_EVERY_WRITES", "20")))
_ai_cache_write_count = 0


def _ai_cache_key(agent_key, config, system_prompt, user_content, temperature, max_tokens, response_format, extra_body):
    payload = {
        "agent_key": agent_key,
        "provider": config.get("provider"),
        "model_id": config.get("model_id"),
        "url": config.get("url"),
        "system_prompt": system_prompt,
        "user_content": user_content,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": response_format,
        "extra_body": extra_body or {},
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ai_cache_ensure_schema(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS ai_responses ("
        "cache_key TEXT PRIMARY KEY, agent_key TEXT NOT NULL, model_id TEXT, response TEXT NOT NULL, "
        "usage_json TEXT NOT NULL, created_at REAL NOT NULL, accessed_at REAL NOT NULL, response_bytes INTEGER NOT NULL DEFAULT 0)"
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(ai_responses)").fetchall()}
    if "accessed_at" not in cols:
        conn.execute("ALTER TABLE ai_responses ADD COLUMN accessed_at REAL NOT NULL DEFAULT 0")
    if "response_bytes" not in cols:
        conn.execute("ALTER TABLE ai_responses ADD COLUMN response_bytes INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE ai_responses SET response_bytes = length(CAST(response AS BLOB)) WHERE response_bytes = 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_responses_accessed_at ON ai_responses(accessed_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_responses_created_at ON ai_responses(created_at)")


def _ai_cache_evict(conn, force=False):
    now = time.time()
    if AI_CACHE_TTL_SECONDS > 0:
        conn.execute("DELETE FROM ai_responses WHERE created_at < ?", (now - AI_CACHE_TTL_SECONDS,))

    count = conn.execute("SELECT COUNT(*) FROM ai_responses").fetchone()[0]
    if count > AI_CACHE_MAX_ENTRIES:
        remove_n = count - AI_CACHE_MAX_ENTRIES
        conn.execute(
            "DELETE FROM ai_responses WHERE cache_key IN (SELECT cache_key FROM ai_responses ORDER BY accessed_at ASC, created_at ASC LIMIT ?)",
            (remove_n,),
        )

    total_bytes = conn.execute("SELECT COALESCE(SUM(response_bytes),0) FROM ai_responses").fetchone()[0]
    if force or total_bytes > AI_CACHE_MAX_BYTES:
        while total_bytes > AI_CACHE_MAX_BYTES:
            row = conn.execute(
                "SELECT cache_key, response_bytes FROM ai_responses ORDER BY accessed_at ASC, created_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                break
            conn.execute("DELETE FROM ai_responses WHERE cache_key = ?", (row[0],))
            total_bytes -= int(row[1] or 0)


def _ai_cache_get(key):
    if not AI_CACHE_ENABLED:
        return None
    try:
        path = os.path.abspath(AI_CACHE_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        now = time.time()
        with sqlite3.connect(path, timeout=5) as conn:
            _ai_cache_ensure_schema(conn)
            row = conn.execute(
                "SELECT response, usage_json, created_at FROM ai_responses WHERE cache_key = ?", (key,)
            ).fetchone()
            if not row:
                return None
            if AI_CACHE_TTL_SECONDS > 0 and row[2] < now - AI_CACHE_TTL_SECONDS:
                conn.execute("DELETE FROM ai_responses WHERE cache_key = ?", (key,))
                return None
            conn.execute("UPDATE ai_responses SET accessed_at = ? WHERE cache_key = ?", (now, key))
        usage = json.loads(row[1]) if row[1] else {}
        usage["cache_hit"] = True
        return row[0], usage
    except Exception as exc:
        print(f"[AI CACHE] READ WARNING | {exc}")
        return None


def _ai_cache_put(key, agent_key, model_id, response_text, usage):
    global _ai_cache_write_count
    if not AI_CACHE_ENABLED or not response_text:
        return
    try:
        path = os.path.abspath(AI_CACHE_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        now = time.time()
        response_bytes = len(response_text.encode("utf-8", errors="ignore"))
        with sqlite3.connect(path, timeout=5) as conn:
            _ai_cache_ensure_schema(conn)
            conn.execute(
                "INSERT OR REPLACE INTO ai_responses(cache_key, agent_key, model_id, response, usage_json, created_at, accessed_at, response_bytes) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (key, agent_key, model_id, response_text, json.dumps(usage or {}, ensure_ascii=False), now, now, response_bytes),
            )
            _ai_cache_write_count += 1
            if _ai_cache_write_count % AI_CACHE_EVICTION_EVERY_WRITES == 0:
                _ai_cache_evict(conn)
            elif response_bytes > AI_CACHE_MAX_BYTES:
                _ai_cache_evict(conn, force=True)
    except Exception as exc:
        print(f"[AI CACHE] WRITE WARNING | {exc}")


def load_prompt(prompt_filename, **variables):
    """Load a modular prompt and render simple {{name}} placeholders.

    No template dependency is required. Missing placeholders are left intact,
    while missing prompt files raise a clear error instead of silently sending
    an error string to the model.
    """
    prompt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'prompts', prompt_filename))
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            template = f.read()
    except OSError as e:
        raise FileNotFoundError(f"Prompt dosyası okunamadı: {prompt_filename}: {e}") from e

    rendered = template
    # Resolve the shared system prompt first. This keeps all agents aligned on
    # the same safety/evidence contract while allowing role-specific templates.
    if '{{common_system}}' in rendered:
        common_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'prompts', 'common_system.md'))
        with open(common_path, 'r', encoding='utf-8') as f:
            common = f.read().strip()
        rendered = rendered.replace('{{common_system}}', common)

    for key, value in variables.items():
        rendered = rendered.replace('{{' + str(key) + '}}', str(value))
    return rendered

def load_registered_prompt(role: str, **variables):
    """Load a prompt by stable role name using prompts/registry.json.

    This keeps runtime code independent from prompt filenames and makes prompt
    version/role changes explicit in one registry file.
    """
    meta = get_prompt_metadata(role)
    rendered = load_prompt(meta["file"], **variables)
    return rendered, meta

def log_conversation(agent_role, model_name, prompt_data, ai_response, duration):
    """Etkileşimleri model adı ve süresiyle birlikte loglar."""
    log_file_path = os.path.join(os.path.dirname(__file__), '..', 'conv.history.md')
    zaman = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    md_icerik = f"## 🕒 Tarih: {zaman} | Görev: {agent_role} | Model: {model_name} | Süre: {duration:.2f} sn\n\n"
    md_icerik += f"### 📥 Girdi (Input):\n```text\n{prompt_data}\n```\n\n"
    md_icerik += f"### 📤 Çıktı (Output):\n{ai_response}\n\n---\n\n"
    
    with open(log_file_path, 'a', encoding='utf-8') as f:
        f.write(md_icerik)

def call_ai_agent(agent_key, system_prompt, user_content, temperature=0.1, max_tokens=None, response_format=None, return_usage=False, extra_body=None):
    """İstenen modele göre doğru API formatını hazırlayıp analizi çalıştırır.

    Console logging deliberately exposes model/agent/status/duration/token usage,
    but never the API key.
    """
    config = MODELS_CONFIG.get(agent_key)
    if not config:
        msg = f"Hata: {agent_key} konfigürasyonu bulunamadı."
        if return_usage:
            return msg, 0.0, {}
        return msg, 0.0

    provider = config.get("provider")
    model_id = config.get("model_id")
    url = config.get("url")

    cache_key = _ai_cache_key(
        agent_key, config, system_prompt, user_content, temperature, max_tokens, response_format, extra_body
    )
    cached = _ai_cache_get(cache_key)
    if cached is not None:
        cached_text, cached_usage = cached
        print(
            f"[AI] CACHE HIT | agent={agent_key} | model={model_id} | "
            f"prompt_tokens={cached_usage.get('prompt_tokens', 0)} | completion_tokens={cached_usage.get('completion_tokens', 0)}"
        )
        if return_usage:
            return cached_text, 0.0, cached_usage
        return cached_text, 0.0

    print(
        f"[AI] CALL | agent={agent_key} | provider={provider} | "
        f"model={model_id} | max_tokens={max_tokens} | temperature={temperature}"
    )
    print(f"[AI] ENDPOINT | {url}")

    if provider in ["saka", "openai"]:
        headers = {
            "Authorization": f"Bearer {config['key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = response_format
        if extra_body:
            payload.update(extra_body)
        # Qwen3-family deployments enable thinking by default. For compact RCA,
        # disable thinking at request level so completion tokens are reserved for
        # the final report rather than internal reasoning tokens. vLLM supports
        # request-level chat_template_kwargs for this behavior.
        if agent_key in {"Ajan_2_RCA_Expert", "Ajan_2_Causal_Expert", "Ajan_2_RCA_AgirTop", "Segmentation_Critic"}:
            payload.setdefault("chat_template_kwargs", {})
            payload["chat_template_kwargs"].setdefault(
                "enable_thinking",
                os.getenv("QWEN_RCA_ENABLE_THINKING", "false").lower() == "true",
            )
            if os.getenv("QWEN_RCA_INCLUDE_REASONING", "false").lower() != "true":
                payload.setdefault("include_reasoning", False)
    elif provider == "anthropic":
        headers = {
            "x-api-key": config["key"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model_id,
            "max_tokens": max_tokens if max_tokens is not None else 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
            "temperature": temperature,
        }
    else:
        msg = f"Desteklenmeyen provider: {provider}"
        print(f"[AI] CONFIG_ERROR | agent={agent_key} | model={model_id} | error={msg}")
        if return_usage:
            return msg, 0.0, {}
        return msg, 0.0

    start_time = time.time()
    try:
        # Qwen gateway is known to work through the same OpenAI-compatible
        # contract as curl. Disable inherited system proxy settings for the
        # Qwen family so the Python path more closely matches a direct curl
        # invocation. Other models retain requests defaults.
        session = requests.Session()
        if agent_key in {"Ajan_2_RCA_Expert", "Ajan_2_Causal_Expert", "Ajan_2_RCA_AgirTop", "Segmentation_Critic"}:
            session.trust_env = False
            headers.setdefault("Accept", "application/json")
            headers.setdefault("User-Agent", "curl/8-compatible-aiops-client")
        response = session.post(
            url,
            headers=headers,
            json=payload,
            verify=False,
            timeout=(15, 180),
        )
        duration = time.time() - start_time

        # Bazı OpenAI-compatible gateway'ler response_format'ı kabul etmeyebilir.
        if response.status_code == 400 and response_format is not None:
            fallback_payload = dict(payload)
            fallback_payload.pop("response_format", None)
            response = session.post(
                url,
                headers=headers,
                json=fallback_payload,
                verify=False,
                timeout=(15, 180),
            )
            duration = time.time() - start_time

        if response.status_code == 200:
            response_json = response.json()
            if provider == "anthropic":
                ai_reply = response_json["content"][0]["text"]
                usage = response_json.get("usage", {}) or {}
            else:
                ai_reply = response_json["choices"][0]["message"].get("content") or ""
                usage = response_json.get("usage", {}) or {}

            finish_reason = None
            try:
                finish_reason = response_json.get("choices", [{}])[0].get("finish_reason")
            except Exception:
                finish_reason = None
            usage_info = {
                "prompt_tokens": usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0,
                "cached_tokens": usage.get("cached_tokens", usage.get("prompt_cached_tokens", 0)) or 0,
                "completion_tokens": usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0,
                "total_tokens": usage.get("total_tokens", 0) or 0,
                "finish_reason": finish_reason,
                "cache_hit": False,
            }

            # Only cache complete, successful responses. Never persist transport
            # failures or truncated generations because they are not trustworthy
            # reusable results.
            if finish_reason in (None, "stop") and ai_reply:
                _ai_cache_put(cache_key, agent_key, model_id, ai_reply, usage_info)

            log_conversation(agent_key, model_id, user_content, ai_reply, duration)
            status = "SUCCESS" if finish_reason not in {"length", "max_tokens"} else "INCOMPLETE"
            print(
                f"[AI] {status} | agent={agent_key} | model={model_id} | "
                f"duration={duration:.2f}s | prompt_tokens={usage_info['prompt_tokens']} | "
                f"completion_tokens={usage_info['completion_tokens']} | "
                f"total_tokens={usage_info['total_tokens']} | finish_reason={usage_info.get('finish_reason')}"
            )
            if return_usage:
                return ai_reply, duration, usage_info
            return ai_reply, duration

        error_msg = f"API Hatası ({response.status_code}): {response.text}"
        print(
            f"[AI] FAIL | agent={agent_key} | model={model_id} | "
            f"status={response.status_code} | duration={duration:.2f}s | "
            f"error={response.text[:500]}"
        )
        if return_usage:
            return error_msg, duration, {}
        return error_msg, duration

    except Exception as exc:
        duration = time.time() - start_time
        error_msg = f"Bağlantı Hatası: {exc}"
        print(
            f"[AI] CONNECTION_ERROR | agent={agent_key} | model={model_id} | "
            f"duration={duration:.2f}s | error={exc}"
        )
        if return_usage:
            return error_msg, duration, {}
        return error_msg, duration
