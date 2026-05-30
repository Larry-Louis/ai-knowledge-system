import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fastapi.responses import JSONResponse

from core.memory import MemoryManager
from models.schema import ChatCompletionRequest, ChatCompletionResponse

router = APIRouter()
memory_manager = MemoryManager()


@router.get("/v1/last-prompt")
def get_last_prompt():
    if not memory_manager.last_prompt:
        return JSONResponse({"prompt": None, "message": "暂无对话记录"})
    return JSONResponse(memory_manager.last_prompt)


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def chat_completions(request: ChatCompletionRequest):
    try:
        result = memory_manager.process_request(
            request_messages=request.messages,
            session_id=request.session_id,
            model=request.model,
        )

        msg = {
            "role": "assistant",
            "content": result["response"],
        }
        if result.get("reasoning"):
            msg["reasoning_content"] = result["reasoning"]

        output = None
        if result.get("reasoning"):
            output = [
                {
                    "type": "reasoning",
                    "id": f"r-{uuid.uuid4().hex[:8]}",
                    "status": "completed",
                    "start_tag": "<think>",
                    "end_tag": "</think>",
                    "attributes": {"type": "reasoning_content"},
                    "content": [{"type": "output_text", "text": result["reasoning"]}],
                    "summary": None,
                },
                {
                    "type": "message",
                    "id": f"msg-{uuid.uuid4().hex[:8]}",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": result["response"]}],
                },
            ]

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
            object="chat.completion",
            created=int(time.time()),
            model=request.model or "default",
            choices=[
                {
                    "index": 0,
                    "message": msg,
                    "finish_reason": "stop",
                }
            ],
            output=output,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class QueryRequest(BaseModel):
    question: str


@router.post("/query")
def query(req: QueryRequest):
    try:
        result = memory_manager.process_request(
            request_messages=[{"role": "user", "content": req.question}],
            session_id=None,
        )
        return {"answer": result["response"], "session_id": result["session_id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
