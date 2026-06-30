from abc import ABC, abstractmethod
import httpx
from infrastructure.config.config import Config

class LLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[dict]) -> str:
        raise NotImplementedError

class OllamaClient(LLMClient):
    def __init__(self, model: str | None = None):
        self.base_url = Config.OLLAMA_BASE_URL
        self.model = model or Config.OLLAMA_MODEL

    def chat(self, messages: list[dict]) -> str:
        payload = {
            'model': self.model,
            'messages': [
                {'role': m['role'], 'content': m['content']} for m in messages
            ],
            'stream': False,
        }
        with httpx.Client(timeout=900) as client:
            resp = client.post(f'{self.base_url}/api/chat', json=payload)
            resp.raise_for_status()
            return resp.json()['message']['content']

class DeepSeekClient(LLMClient):
    def __init__(self, model: str | None = None):
        self.api_key = Config.DEEPSEEK_API_KEY
        self.base_url = Config.DEEPSEEK_BASE_URL
        self.model = model or Config.DEEPSEEK_MODEL
        self.last_reasoning = None

    def chat(self, messages: list[dict]) -> str:
        payload = {'model': self.model, 'messages': messages}
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f'{self.base_url}/chat/completions',
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            msg = resp.json()['choices'][0]['message']
            self.last_reasoning = msg.get('reasoning_content')
            return msg['content']

class OpenAIClient(LLMClient):
    def __init__(self, model: str | None = None):
        self.api_key = Config.OPENAI_API_KEY
        self.base_url = Config.OPENAI_BASE_URL
        self.model = model or Config.OPENAI_MODEL

    def chat(self, messages: list[dict]) -> str:
        payload = {'model': self.model, 'messages': messages}
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f'{self.base_url}/chat/completions',
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()['choices'][0]['message']['content']

class LLMFactory:
    @staticmethod
    def get(provider: str | None = None, model: str | None = None) -> LLMClient:
        """
        [S0-9] LLM 工厂方法：根据 provider 和 model 返回对应的 LLM 客户端

        主要工作流：
        1. 如果指定了 model，根据模型名称选择客户端：
           - deepseek-r1:8b / qwen3.5:9b -> OllamaClient
           - 包含 "deepseek" -> DeepSeekClient
           - 其他 -> OpenAIClient
        2. 如果未指定 model，根据 provider 选择：
           - deepseek -> DeepSeekClient
           - ollama -> OllamaClient
           - openai -> OpenAIClient
           - 默认回退到 deepseek-v4-flash
        """
        # Dynamic Routing Logic
        if model:
            if model in ['deepseek-r1:8b', 'qwen3.5:9b']:
                return OllamaClient(model=model)
            elif 'deepseek' in model:
                return DeepSeekClient(model=model)
            else:
                return OpenAIClient(model=model)
        
        # Default fallback logic
        provider = provider or Config.LLM_PROVIDER
        
        # 强制逻辑：如果是 deepseek provider，绝不降级
        if provider == 'deepseek':
            return DeepSeekClient()
        elif provider == 'ollama':
            return OllamaClient()
        elif provider == 'openai':
            return OpenAIClient()
        else:
            # Final fallback to deepseek-v4-flash
            return DeepSeekClient(model='deepseek-v4-flash')