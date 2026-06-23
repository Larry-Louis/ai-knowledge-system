import re
import json
import httpx
from core.config import Config
from core.prompt_factory import get_memory_validation_prompt
from core.decision_maker import DecisionMaker
from services.embedding import EmbeddingService
from services.qdrant_store import QdrantStore

_TERM_MAP = {'autosar': 'AUTOSAR', 'rag': 'RAG', 'ai': 'AI', 'llm': 'LLM', 'api': 'API', 'slm': 'SLM', 'qdrant': 'Qdrant', 'ollama': 'Ollama', 'deepseek': 'DeepSeek', 'python': 'Python', 'java': 'Java', 'docker': 'Docker', 'kubernetes': 'Kubernetes', 'sqlite': 'SQLite'}

def normalize(text: str) -> str:
    """
    [S1-4e] 文本规范化：标准化术语和角色标记

    主要工作流：
    1. 去除首尾空白
    2. 将 "我们" 开头的行替换为 "用户"
    3. 将常见术语（如 autosar、rag、ai 等）统一大小写
    4. 返回规范化后的文本
    """
    text = text.strip()
    if not text: return text
    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('用户') and not line.startswith('我们'): line = '用户' + line[1:]
        elif line.startswith('我们'): line = '用户' + line[2:]
        for key, val in _TERM_MAP.items():
            esc = re.escape(key)
            line = re.sub(rf'(?i)(^|[^a-zA-Z]){esc}([^a-zA-Z]|$)', rf'\1{val}\2', line)
        lines.append(line)
    return '\n'.join(lines)

_POSITIVE = {'喜欢', '爱', '可以', '会', '要', '想', '支持', '推荐'}
_NEGATIVE = {'不喜欢', '不爱', '不好', '不可以', '不会', '不是', '不要', '不想', '讨厌', '恨', '反对', '拒绝', '无法', '不能'}

def detect_polarity(text: str) -> int:
    """
    [S1-4-Rule] 极性检测：判断文本的情感倾向

    主要工作流：
    1. 统计正面词汇（喜欢、爱、可以等）和负面词汇（不喜欢、不爱、不好等）的出现次数
    2. 处理重叠情况（如 "不喜欢" 包含 "喜欢"）
    3. 返回 1（正面）、-1（负面）或 0（中性）
    """
    text_lower = text.lower()
    pos_count = sum(text_lower.count(w) for w in _POSITIVE)
    neg_count = sum(text_lower.count(w) for w in _NEGATIVE)
    for nw in _NEGATIVE:
        for pw in _POSITIVE:
            if pw in nw:
                overlap = text_lower.count(nw)
                pos_count = max(0, pos_count - overlap)
    return 1 if pos_count > neg_count else (-1 if neg_count > pos_count else 0)

DEDUP_THRESHOLD = 0.90
CONFLICT_THRESHOLD = 0.80

def is_duplicate(content: str, qdrant: QdrantStore) -> tuple[bool, list[float] | None]:
    """
    [S1-4e] 去重检查：判断内容是否与已有记忆单元重复

    主要工作流：
    1. 对内容进行向量化
    2. 在 Qdrant 中搜索类型为 memory_unit 的相似点
    3. 如果最高相似度 >= 0.90，则视为重复
    4. 返回 (是否重复, 向量)
    """
    try: embedding = EmbeddingService.embed(content)
    except: return False, None
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    results = qdrant.client.query_points(collection_name=Config.QDRANT_MEMORY_COLLECTION, query=embedding, query_filter=Filter(must=[FieldCondition(key='type', match=MatchValue(value='memory_unit'))]), limit=5)
    for p in results.points:
        if p.score >= DEDUP_THRESHOLD: return True, embedding
    return False, embedding

_SEPARATORS = re.compile(r'(?:并且|而且|以及|同时|，|。|；|、)')

def extract_mus(turn_text: str, user_msg: str) -> list[str]:
    candidates = [s.strip() for s in _SEPARATORS.split(user_msg) if len(s.strip()) > 4]
    return candidates[:5] if candidates else [user_msg[:200]]

def _safe_parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith(''): text = text.split('')[1].replace('json', '', 1).strip()
    try: result = json.loads(text); return result if isinstance(result, dict) else None
    except: pass
    m = re.search(r'\{.*?\}', text, re.DOTALL)
    if m:
        try: return json.loads(m.group())
        except: pass
    return None

def slm_validate(turn_text: str) -> dict:
    """
    [S1-4b] SLM 验证：调用小型语言模型验证对话内容是否值得记忆

    主要工作流：
    1. 构建验证提示（使用 get_memory_validation_prompt）
    2. 调用 Ollama API 获取 SLM 响应
    3. 解析 JSON 响应
    4. 通过 DecisionMaker.classify_mu 应用决策矩阵
    5. 返回包含 keep、type、tag、importance、confidence 等信息的字典
    """
    payload = {
        'model': Config.OLLAMA_MODEL,
        'messages': [{'role': 'user', 'content': get_memory_validation_prompt(turn_text)}],
        'options': {'temperature': 0.1, 'num_predict': 300},
        'stream': False
    }
    headers = {'Content-Type': 'application/json'}
    try:
        resp = httpx.post(f'{Config.OLLAMA_BASE_URL}/api/chat', json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        text = resp.json()['message']['content'].strip()
        print(f'[SLM DEBUG] Raw Output: {text[:500]}')
        raw = _safe_parse_json(text)
        if raw is None: return {'keep': False}
        return DecisionMaker.classify_mu(raw)
    except Exception as e:
        print(f'[SLM Validation Error] {e}')
        return {'keep': False}
