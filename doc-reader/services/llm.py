import os
import httpx

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")


def chat(messages: list[dict], model: str | None = None) -> str:
    """Call DeepSeek chat API and return response content."""
    payload = {
        "model": model or DEEPSEEK_MODEL,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=120) as client:
        resp = client.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
