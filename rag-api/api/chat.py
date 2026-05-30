import time
import uuid
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fastapi.responses import JSONResponse, StreamingResponse

from core.config import Config
from core.memory import MemoryManager
from core.state import set_active_role, set_core_write_mode, get_core_write_mode
from models.schema import ChatCompletionRequest, ChatCompletionResponse

router = APIRouter()
memory_manager = MemoryManager()


@router.get("/v1/last-prompt")
def get_last_prompt():
    if not memory_manager.last_prompt:
        return JSONResponse({"prompt": None, "message": "暂无对话记录"})
    return JSONResponse(memory_manager.last_prompt)


def _build_chat_response(result: dict, request: ChatCompletionRequest) -> dict:
    """Build the standard chat completion response dict."""
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

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model or "default",
        "choices": [
            {
                "index": 0,
                "message": msg,
                "finish_reason": "stop",
            }
        ],
        "output": output,
    }


@router.post("/v1/chat/completions")
def chat_completions(request: ChatCompletionRequest):
    try:
        # Parse model name
        model_str = request.model if request.model != "default" else ""
        model = model_str
        if ":" in model_str:
            parts = model_str.split(":", 1)
            model = parts[0] or None
            role = parts[1].strip()
            if role == Config.CORE_LAYER:
                set_core_write_mode(True)
            elif role:
                set_active_role(role)
                set_core_write_mode(False)
        elif model_str == Config.CORE_LAYER:
            set_core_write_mode(True)
            model = None
        elif model_str in Config.MEMORY_LAYERS:
            set_active_role(model_str)
            set_core_write_mode(False)
            model = None

        result = memory_manager.process_request(
            request_messages=request.messages,
            session_id=request.session_id,
            model=model,
        )

        response_data = _build_chat_response(result, request)

        if request.stream:
            return _stream_response(response_data)
        return JSONResponse(response_data)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _stream_response(data: dict) -> StreamingResponse:
    """Return the response as an SSE stream (single chunk)."""
    async def generate():
        # Standard OpenAI SSE format
        chunk = {
            "id": data["id"],
            "object": "chat.completion.chunk",
            "created": data["created"],
            "model": data["model"],
            "choices": [{
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "content": data["choices"][0]["message"]["content"],
                },
                "finish_reason": None,
            }],
        }
        if data["choices"][0]["message"].get("reasoning_content"):
            chunk["choices"][0]["delta"]["reasoning_content"] = data["choices"][0]["message"]["reasoning_content"]

        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        # Final chunk with [DONE]
        final = {
            "id": data["id"],
            "object": "chat.completion.chunk",
            "created": data["created"],
            "model": data["model"],
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }],
        }
        yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
    try:
        # Parse model name: "deepseek-v4-flash:game" or bare "game"
        model_str = request.model if request.model != "default" else ""
        model = model_str
        if ":" in model_str:
            parts = model_str.split(":", 1)
            model = parts[0] or None
            role = parts[1].strip()
            if role == Config.CORE_LAYER:
                set_core_write_mode(True)
            elif role:
                set_active_role(role)
                set_core_write_mode(False)
        elif model_str == Config.CORE_LAYER:
            # "core" → enable core write mode, don't switch role
            set_core_write_mode(True)
            model = None
        elif model_str in Config.MEMORY_LAYERS:
            # Bare layer name like "story" → switch role
            set_active_role(model_str)
            set_core_write_mode(False)
            model = None

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
