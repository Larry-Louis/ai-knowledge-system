import os
import httpx

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")


MAX_PROMPT_CHARS = 500000  # ~125K tokens, safe for 1M token limit


def chat(messages: list[dict], model: str | None = None) -> str:
    """
    调用 DeepSeek 聊天 API 并返回响应内容

    主要工作流：
    1. 计算消息总长度，如果超过 MAX_PROMPT_CHARS（500K 字符），则截断最后一条用户消息
    2. 构建 API 请求（模型、消息）
    3. 调用 DeepSeek /chat/completions 端点
    4. 返回助手消息内容
    """
    # Truncate messages to stay within context limit
    total = sum(len(m.get("content", "")) for m in messages)
    if total > MAX_PROMPT_CHARS:
        # Trim the user message (last one) if too long
        for m in reversed(messages):
            if m["role"] == "user" and len(m["content"]) > 1000:
                excess = total - MAX_PROMPT_CHARS
                m["content"] = m["content"][:-excess]
                if len(m["content"]) < 500:
                    m["content"] = m["content"][:500]
                break

    payload = {
        "model": model or DEEPSEEK_MODEL,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=300) as client:
        resp = client.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
        )
        if resp.status_code != 200:
            detail = resp.text[:500]
            raise Exception(f"DeepSeek API {resp.status_code}: {detail}")
        return resp.json()["choices"][0]["message"]["content"]
