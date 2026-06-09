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


@router.get('/v1/last-prompt')
def get_last_prompt():
    if not memory_manager.last_prompt:
        return JSONResponse({'prompt': None, 'message': '暂无对话记录'})
    return JSONResponse(memory_manager.last_prompt)


def _build_chat_response(result: dict, request: ChatCompletionRequest) -> dict:
    msg = {
        'role': 'assistant',
        'content': result['response'],
    }
    if result.get('reasoning'):
        msg['reasoning_content'] = result['reasoning']

    output = None
    if result.get('reasoning'):
        output = [
            {
                'type': 'reasoning',
                'id': f'r-{uuid.uuid4().hex[:8]}',
                'status': 'completed',
                'start_tag': '<think>',
                'end_tag': '</think>',
                'attributes': {'type': 'reasoning_content'},
                'content': [{'type': 'output_text', 'text': result['reasoning']}],
                'summary': None,
            },
            {
                'type': 'message',
                'id': f'msg-{uuid.uuid4().hex[:8]}',
                'status': 'completed',
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': result['response']}],
            },
        ]

    return {
        'id': f'chatcmpl-{uuid.uuid4().hex[:12]}',
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': request.model or 'default',
        'choices': [
            {
                'index': 0,
                'message': msg,
                'finish_reason': 'stop',
            }
        ],
        'output': output,
    }


@router.post("/v1/chat/completions")
def chat_completions(request: ChatCompletionRequest):
    try:
        model_str = request.model if request.model != "default" else ""
        
        # 动态读取配置
        layers = list(Config.MEMORY_LAYERS.keys())
        models = Config.AVAILABLE_MODELS

        model_resolved = None
        role_resolved = "general"

        if ":" in model_str:
            parts = model_str.split(":")
            last_part = parts[-1]
            potential_model = ":".join(parts[:-1])
            
            if last_part in layers:
                role_resolved = last_part
                model_resolved = potential_model if potential_model in models else None
            else:
                model_resolved = model_str
                role_resolved = "general"
        else:
            if model_str in layers:
                role_resolved = model_str
                model_resolved = None
            elif model_str in models:
                model_resolved = model_str
                role_resolved = "general"
            elif model_str == "core":
                set_core_write_mode(True)
                model_resolved = None
            else:
                model_resolved = None
                role_resolved = "general"

        if role_resolved:
            set_active_role(role_resolved)
            set_core_write_mode(False)

        result = memory_manager.process_request(
            request_messages=request.messages,
            session_id=request.session_id,
            model=model_resolved,
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
    async def generate():
        chunk = {
            'id': data['id'],
            'object': 'chat.completion.chunk',
            'created': data['created'],
            'model': data['model'],
            'choices': [{
                'index': 0,
                'delta': {
                    'role': 'assistant',
                    'content': data['choices'][0]['message']['content'],
                },
                'finish_reason': None,
            }],
        }
        if data['choices'][0]['message'].get('reasoning_content'):
            chunk['choices'][0]['delta']['reasoning_content'] = data['choices'][0]['message']['reasoning_content']

        yield f'data: {json.dumps(chunk, ensure_ascii=False)}\n\n'

        final = {
            'id': data['id'],
            'object': 'chat.completion.chunk',
            'created': data['created'],
            'model': data['model'],
            'choices': [{
                'index': 0,
                'delta': {},
                'finish_reason': 'stop',
            }],
        }
        yield f'data: {json.dumps(final, ensure_ascii=False)}\n\n'
        yield 'data: [DONE]\n\n'

    return StreamingResponse(generate(), media_type='text/event-stream')


class QueryRequest(BaseModel):
    question: str


@router.post('/query')
def query(req: QueryRequest):
    try:
        result = memory_manager.process_request(
            request_messages=[{'role': 'user', 'content': req.question}],
            session_id=None,
        )
        return {'answer': result['response'], 'session_id': result['session_id']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
