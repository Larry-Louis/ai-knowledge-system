import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.memory import MemoryManager
from models.schema import ChatCompletionRequest, ChatCompletionResponse

router = APIRouter()
memory_manager = MemoryManager()


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def chat_completions(request: ChatCompletionRequest):
    try:
        result = memory_manager.process_request(
            request_messages=request.messages,
            session_id=request.session_id,
        )

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
            object="chat.completion",
            created=int(time.time()),
            model=request.model or "default",
            choices=[
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": result["response"],
                    },
                    "finish_reason": "stop",
                }
            ],
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
