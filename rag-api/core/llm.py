from abc import ABC, abstractmethod

import httpx

from core.config import Config


class LLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[dict]) -> str:
        raise NotImplementedError


class OllamaClient(LLMClient):
    def __init__(self):
        self.base_url = Config.OLLAMA_BASE_URL
        self.model = Config.OLLAMA_MODEL

    def chat(self, messages: list[dict]) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": m["role"], "content": m["content"]} for m in messages
            ],
            "stream": False,
        }
        with httpx.Client(timeout=900) as client:
            resp = client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]


class DeepSeekClient(LLMClient):
    def __init__(self, model: str | None = None):
        self.api_key = Config.DEEPSEEK_API_KEY
        self.base_url = Config.DEEPSEEK_BASE_URL
        self.model = model or Config.DEEPSEEK_MODEL
        self.last_reasoning = None

    def chat(self, messages: list[dict]) -> str:
        payload = {"model": self.model, "messages": messages}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
            self.last_reasoning = msg.get("reasoning_content")
            return msg["content"]


class OpenAIClient(LLMClient):
    def __init__(self):
        self.api_key = Config.OPENAI_API_KEY
        self.base_url = Config.OPENAI_BASE_URL
        self.model = Config.OPENAI_MODEL

    def chat(self, messages: list[dict]) -> str:
        payload = {"model": self.model, "messages": messages}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class LLMFactory:
    @staticmethod
    def get(provider: str | None = None, model: str | None = None) -> LLMClient:
        provider = provider or Config.LLM_PROVIDER
        if provider == "ollama":
            return OllamaClient()
        elif provider == "deepseek":
            return DeepSeekClient(model=model)
        elif provider == "openai":
            return OpenAIClient()
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")
