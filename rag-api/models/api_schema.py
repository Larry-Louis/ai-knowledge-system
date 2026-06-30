from pydantic import BaseModel
from typing import Optional, List


class ChatMessage(BaseModel):
    """
    [S0-1] 聊天消息模型：包含角色和内容
    """
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """
    [S0-1] 聊天完成请求模型

    主要字段：
    - model: 模型名称，支持 "default" 或 "模型:角色" 格式
    - messages: 消息列表
    - session_id: 会话 ID（可选）
    - stream: 是否流式输出
    """
    model: str = "default"
    messages: List[ChatMessage]
    session_id: Optional[str] = None
    stream: Optional[bool] = False


class ChatCompletionResponse(BaseModel):
    """
    [S0-1] 聊天完成响应模型

    主要字段：
    - id: 响应 ID
    - object: 对象类型
    - created: 创建时间戳
    - model: 使用的模型
    - choices: 选择列表（包含消息和完成原因）
    - usage: token 使用统计
    - output: 推理输出（可选）
    """
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[dict]
    usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    output: Optional[List[dict]] = None
