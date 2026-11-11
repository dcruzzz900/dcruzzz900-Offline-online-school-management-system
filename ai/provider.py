"""Server-side multi-provider AI adapter.

Supported providers: OpenAI-compatible, Google Gemini and Anthropic.
Provider credentials are read only from environment variables.  The legacy
AI_API_URL/AI_API_KEY configuration remains supported for backwards
compatibility.  The module never sends school/student records unless a caller
explicitly supplies a minimized prompt after checking school settings/consent.
"""
import json
import os
import urllib.request
import urllib.error


def _provider():
    chosen = (os.environ.get("AI_PROVIDER") or "auto").strip().lower()
    if chosen != "auto":
        return chosen
    if os.environ.get("AI_API_URL") and os.environ.get("AI_API_KEY"):
        return "openai_compatible"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "none"


def configured(provider=None):
    p = (provider or _provider()).lower()
    if p == "none":
        return False
    if p == "openai_compatible":
        return bool(os.environ.get("AI_API_URL") and os.environ.get("AI_API_KEY"))
    if p in ("openai", "openai-compatible"):
        return bool(os.environ.get("OPENAI_API_KEY") or (os.environ.get("AI_API_URL") and os.environ.get("AI_API_KEY")))
    if p in ("gemini", "google"):
        return bool(os.environ.get("GEMINI_API_KEY"))
    if p == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    return False


def active_provider():
    return _provider()


def _post(url, payload, headers, timeout=45):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def generate(system_prompt, user_prompt, *, max_tokens=700, provider=None):
    p = (provider or _provider()).lower()
    if not configured(p):
        return None, "No approved AI provider is configured. Offline/local assistance remains available."
    try:
        if p in ("openai_compatible", "openai", "openai-compatible"):
            legacy = p == "openai_compatible" or (not os.environ.get("OPENAI_API_KEY") and os.environ.get("AI_API_URL"))
            url = os.environ.get("AI_API_URL", "https://api.openai.com/v1/chat/completions") if legacy else os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
            key = os.environ.get("AI_API_KEY") if legacy else os.environ.get("OPENAI_API_KEY")
            payload = {"model": os.environ.get("AI_MODEL", "gpt-4o-mini"), "messages": [
                {"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "temperature": 0.2, "max_tokens": max_tokens}
            data = _post(url, payload, {"Authorization": "Bearer " + key})
            result = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        elif p in ("gemini", "google"):
            model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
            url = "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent?key=" + os.environ["GEMINI_API_KEY"]
            payload = {"systemInstruction": {"parts": [{"text": system_prompt}]},
                       "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                       "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens}}
            data = _post(url, payload, {})
            result = "".join(x.get("text", "") for x in (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []))
        elif p == "anthropic":
            model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
            url = os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")
            payload = {"model": model, "max_tokens": max_tokens, "temperature": 0.2,
                       "system": system_prompt, "messages": [{"role": "user", "content": user_prompt}]}
            data = _post(url, payload, {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
            result = "".join(x.get("text", "") for x in data.get("content", []) if x.get("type") == "text")
        else:
            return None, "Unsupported AI provider selection."
        result = result.strip() if isinstance(result, str) else None
        return (result or None), (None if result else "The AI provider returned an empty response.")
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as exc:
        return None, "AI provider request failed: " + exc.__class__.__name__
    except Exception as exc:
        return None, "AI provider request failed: " + exc.__class__.__name__
