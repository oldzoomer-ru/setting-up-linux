import time
import uuid
import json
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from json_repair import repair_json

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import ChoiceDelta


app = FastAPI()

# ==================== КОНФИГУРАЦИЯ ====================

LM_STUDIO_URL = "http://localhost:1234"
MODEL_IDENTIFIER = "qwen/qwen3.6-35b-a3b"
MAX_CONTEXT_WINDOW = 262144

# Единый клиент SDK для LM Studio. httpx-пул внутри SDK переиспользуется.
lm_client = AsyncOpenAI(
    base_url=f"{LM_STUDIO_URL}/v1",
    api_key="lm-studio",          # LM Studio не проверяет, но SDK требует непустой
    timeout=180.0,
    max_retries=0,                # не ретраим tool-вызовы автоматически
)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def fix_and_clean_json(raw_content: str) -> str:
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1).strip()
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()
    try:
        return repair_json(cleaned)
    except Exception:
        return cleaned


def maybe_fix_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith(("`", "{", "[")):
        return fix_and_clean_json(stripped)
    return text


def _extra(obj, key: str) -> str:
    """
    Достаёт кастомное поле (например reasoning_content) из Pydantic-модели SDK.
    SDK хранит не-схемные поля в model_extra, но также может пробрасывать их
    как обычные атрибуты — проверяем оба варианта.
    """
    if obj is None:
        return ""
    val = getattr(obj, key, None)
    if val:
        return val
    extra = getattr(obj, "model_extra", None) or {}
    return extra.get(key) or ""


def _extract_url(block: dict, *keys) -> str | None:
    for key in keys:
        value = block.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            url = value.get("url")
            if url:
                return url
    return None


# ==================== XML FALLBACK (только sync) ====================

_PARAM_PATTERNS = [
    re.compile(r'<parameter=([\w_]+)>(.*?)</parameter(?:=\1)?>', re.DOTALL),
    re.compile(r'<parameter\s+name=["\']([\w_]+)["\']\s*>(.*?)</parameter>', re.DOTALL),
    re.compile(r'<parameter>([\w_]+)>(.*?)</parameter>', re.DOTALL),
    re.compile(r'<parameter\s+([\w_]+)=["\']([^"\']*)["\']\s*/?>'),
]


def _parse_xml_params(block: str) -> dict:
    params = {}
    for pattern in _PARAM_PATTERNS:
        for m in pattern.finditer(block):
            params.setdefault(m.group(1).strip(), m.group(2).strip())
    return params


def _split_text_and_tools(raw_text: str) -> tuple[str, list[dict]]:
    if "<tool_use" not in raw_text:
        return raw_text, []

    tool_blocks = re.findall(r'<tool_use[^>]*>(.*?)</tool_use>', raw_text, re.DOTALL)
    clean_text = re.sub(r'<tool_use[^>]*>.*?</tool_use>', '', raw_text, flags=re.DOTALL).strip()

    items = []
    for block in tool_blocks:
        name_match = re.search(r'<name>\s*(.*?)\s*</name>', block, re.DOTALL)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        if not name:
            continue
        items.append({
            "type": "function_call",
            "id": f"fc_{uuid.uuid4().hex[:24]}",
            "call_id": f"call_{uuid.uuid4().hex[:24]}",
            "name": name,
            "arguments": json.dumps(_parse_xml_params(block), ensure_ascii=False),
            "status": "completed",
        })
    return clean_text, items


# ==================== ТРАНСЛЯЦИЯ ВХОДА (Responses -> Chat) ====================

def convert_tools_to_lm(tools: list) -> list:
    result = []
    for tool in tools or []:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        result.append({
            "type": "function",
            "function": {
                "name": tool.get("name"),
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters", {}),
            },
        })
    return result


def convert_tool_choice(choice):
    if choice is None:
        return None
    if isinstance(choice, str):
        return choice
    if isinstance(choice, dict) and choice.get("type") == "function":
        return {"type": "function", "function": {"name": choice.get("name")}}
    return choice


def convert_text_format(text_config) -> dict | None:
    """Responses text.format -> Chat Completions response_format."""
    if not isinstance(text_config, dict):
        return None
    fmt = text_config.get("format")
    if not isinstance(fmt, dict):
        return None
    ftype = fmt.get("type")
    if ftype == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {
                "name": fmt.get("name", "output"),
                "schema": fmt.get("schema", {}),
                "strict": fmt.get("strict", True),
            },
        }
    if ftype == "json_object":
        return {"type": "json_object"}
    return None


def transform_input_to_lm_studio(input_data) -> list:
    if not isinstance(input_data, list):
        return [{"role": "user", "content": "Hello"}]

    messages = []
    pending_tool_calls = []

    def flush():
        nonlocal pending_tool_calls
        if pending_tool_calls:
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": pending_tool_calls,
            })
            pending_tool_calls = []

    for item in input_data:
        itype = item.get("type", "message")

        if itype == "reasoning":
            flush()
            text = "".join(
                s.get("text", "") for s in item.get("summary", []) if isinstance(s, dict)
            )
            if text:
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": text,
                })
            continue

        if itype == "function_call":
            pending_tool_calls.append({
                "id": item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": item.get("name", ""),
                    "arguments": item.get("arguments", "{}"),
                },
            })
            continue

        if itype == "function_call_output":
            flush()
            messages.append({
                "role": "tool",
                "tool_call_id": item.get("call_id", ""),
                "content": item.get("output", ""),
            })
            continue

        # Обычное сообщение
        flush()
        role = item.get("role", "user")
        content = item.get("content")

        reasoning = item.get("reasoning_content") or ""
        if reasoning and role == "assistant":
            messages.append({
                "role": "assistant",
                "content": None,
                "reasoning_content": reasoning,
            })

        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue

        if isinstance(content, list):
            blocks = []
            for b in content:
                btype = b.get("type")
                if btype in ("input_text", "output_text", "text"):
                    blocks.append({"type": "text", "text": b.get("text", "")})
                elif btype in ("input_image", "image_url"):
                    url = _extract_url(b, "image_url", "input_image")
                    if url:
                        blocks.append({"type": "image_url", "image_url": {"url": url}})
                elif btype in ("input_video", "video_url", "input_file"):
                    url = _extract_url(b, "video_url", "input_video", "input_file")
                    if url:
                        blocks.append({"type": "video_url", "video_url": {"url": url}})
            if blocks:
                messages.append({"role": role, "content": blocks})

    flush()
    return messages or [{"role": "user", "content": "Hello"}]


# ==================== ПОСТРОЕНИЕ ОТВЕТА (SYNC) ====================

def create_responses_api_payload(completion: ChatCompletion, input_items: list) -> dict:
    choice = completion.choices[0]
    message = choice.message

    raw_text = message.content or ""
    reasoning_text = _extra(message, "reasoning_content")
    tool_calls = message.tool_calls or []

    output = []

    # Reasoning
    if reasoning_text:
        output.append({
            "id": f"rs_{uuid.uuid4().hex[:24]}",
            "type": "reasoning",
            "status": "completed",
            "summary": [{"type": "summary_text", "text": reasoning_text}],
        })

    # Текст (+ XML fallback, если нативных tool_calls нет)
    if raw_text:
        if tool_calls:
            output.append({
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": maybe_fix_json(raw_text)}],
            })
        else:
            clean_text, xml_items = _split_text_and_tools(raw_text)
            if clean_text:
                output.append({
                    "id": f"msg_{uuid.uuid4().hex[:24]}",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": maybe_fix_json(clean_text)}],
                })
            output.extend(xml_items)

    # Нативные tool_calls
    for tc in tool_calls:
        fn = tc.function
        output.append({
            "type": "function_call",
            "id": f"fc_{uuid.uuid4().hex[:24]}",
            "call_id": tc.id,
            "name": fn.name,
            "arguments": fn.arguments or "{}",
            "status": "completed",
        })

    # Usage: берём из LM Studio, если пришёл, иначе оцениваем
    if completion.usage is not None:
        prompt_tokens = completion.usage.prompt_tokens
        completion_tokens = completion.usage.completion_tokens
        total_tokens = completion.usage.total_tokens
    else:
        prompt_tokens = len(str(input_items)) // 4
        completion_tokens = (
            len(raw_text) // 4
            + len(reasoning_text) // 4
            + sum(len((tc.function.arguments or "")) for tc in tool_calls) // 4
        )
        total_tokens = prompt_tokens + completion_tokens

    remaining_tokens = max(0, MAX_CONTEXT_WINDOW - total_tokens)

    return {
        "id": f"resp_{uuid.uuid4().hex[:24]}",
        "object": "response",
        "created_at": int(time.time()),
        "model": MODEL_IDENTIFIER,
        "status": "completed",
        "output": output,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "context_window": {
                "max_tokens": MAX_CONTEXT_WINDOW,
                "tokens_used": total_tokens,
                "tokens_remaining": remaining_tokens,
            },
        },
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ==================== HTTP POST ====================

@app.post("/v1/responses")
async def handle_openai_responses_api(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    raw_input = body.get("input", body.get("messages", [{"role": "user", "content": "Hello"}]))
    instructions = body.get("instructions")
    should_stream = bool(body.get("stream", False))

    # --- Сообщения ---
    messages = transform_input_to_lm_studio(raw_input)
    if instructions:
        messages = [{"role": "system", "content": instructions}] + messages

    # --- Reasoning / preserve_thinking ---
    preserve_thinking = body.get("preserve_thinking")
    if preserve_thinking is None:
        rcfg = body.get("reasoning", {})
        if isinstance(rcfg, dict):
            preserve_thinking = rcfg.get("preserve_thinking")
    enable_thinking = body.get("enable_thinking")
    if enable_thinking is None:
        enable_thinking = True

    chat_template_kwargs = {
        "enable_thinking": bool(enable_thinking),
        "preserve_thinking": bool(preserve_thinking) if preserve_thinking is not None else True,
    }

    # --- Инструменты ---
    tools = convert_tools_to_lm(body.get("tools"))
    tool_choice = convert_tool_choice(body.get("tool_choice"))
    response_format = convert_text_format(body.get("text", {}))

    # --- Базовые kwargs для SDK ---
    create_kwargs: dict = {
        "model": MODEL_IDENTIFIER,
        "messages": messages,
        "stream": should_stream,
        "extra_body": {"chat_template_kwargs": chat_template_kwargs},
    }
    if tools:
        create_kwargs["tools"] = tools
        if tool_choice is not None:
            create_kwargs["tool_choice"] = tool_choice
        if "parallel_tool_calls" in body:
            create_kwargs["parallel_tool_calls"] = bool(body["parallel_tool_calls"])
    if response_format is not None:
        create_kwargs["response_format"] = response_format

    # ==================== СИНХРОННЫЙ ОТВЕТ ====================
    if not should_stream:
        try:
            completion: ChatCompletion = await lm_client.chat.completions.create(**create_kwargs)
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={"error": {"message": f"LM Studio error: {e}"}},
            )
        return JSONResponse(content=create_responses_api_payload(completion, raw_input))

    # ==================== STREAMING ====================
    async def event_generator():
        response_id = f"resp_{uuid.uuid4().hex[:24]}"
        next_index = 0

        message_id = None
        message_index = None
        full_text = ""
        markdown_skipped = False

        reasoning_id = None
        reasoning_index = None
        full_reasoning = ""

        tool_calls: dict[int, dict] = {}

        yield _sse("response.created", {
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": int(time.time()),
                "model": MODEL_IDENTIFIER,
                "status": "in_progress",
                "output": [],
            },
        })

        try:
            stream = await lm_client.chat.completions.create(**create_kwargs)
        except Exception as e:
            yield _sse("error", {
                "type": "error",
                "error": {"message": f"LM Studio error: {e}"},
            })
            return

        try:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta: ChoiceDelta = chunk.choices[0].delta

                # --- REASONING ---
                reasoning_delta = _extra(delta, "reasoning_content")
                if reasoning_delta:
                    if reasoning_id is None:
                        reasoning_id = f"rs_{uuid.uuid4().hex[:24]}"
                        reasoning_index = next_index
                        next_index += 1
                        yield _sse("response.output_item.added", {
                            "type": "response.output_item.added",
                            "output_index": reasoning_index,
                            "item": {
                                "id": reasoning_id,
                                "type": "reasoning",
                                "status": "in_progress",
                                "summary": [],
                            },
                        })
                    full_reasoning += reasoning_delta
                    yield _sse("response.reasoning_summary_text.delta", {
                        "type": "response.reasoning_summary_text.delta",
                        "item_id": reasoning_id,
                        "output_index": reasoning_index,
                        "summary_index": 0,
                        "delta": reasoning_delta,
                    })

                # --- ТЕКСТ ---
                chunk_text = delta.content or ""
                if chunk_text:
                    if message_id is None:
                        message_id = f"msg_{uuid.uuid4().hex[:24]}"
                        message_index = next_index
                        next_index += 1
                        yield _sse("response.output_item.added", {
                            "type": "response.output_item.added",
                            "output_index": message_index,
                            "item": {
                                "id": message_id,
                                "type": "message",
                                "status": "in_progress",
                                "role": "assistant",
                                "content": [],
                            },
                        })

                    full_text += chunk_text
                    current = full_text.strip()

                    if not markdown_skipped:
                        if current in ("`", "``", "```", "```j", "```js", "```jso", "```json"):
                            continue
                        if current.startswith("```json") or current.startswith("```"):
                            markdown_skipped = True
                            continue
                        if len(current) >= 7:
                            markdown_skipped = True

                    if "```" in chunk_text:
                        chunk_text = chunk_text.replace("```", "").replace("json", "").strip()
                        if not chunk_text:
                            continue

                    yield _sse("response.output_text.delta", {
                        "type": "response.output_text.delta",
                        "item_id": message_id,
                        "output_index": message_index,
                        "content_index": 0,
                        "delta": chunk_text,
                    })

                # --- НАТИВНЫЕ TOOL CALLS ---
                for tc_delta in delta.tool_calls or []:
                    tc_idx = tc_delta.index
                    fn = tc_delta.function

                    if tc_idx not in tool_calls:
                        item_id = f"fc_{uuid.uuid4().hex[:24]}"
                        output_index = next_index
                        next_index += 1
                        tool_calls[tc_idx] = {
                            "item_id": item_id,
                            "call_id": tc_delta.id or f"call_{uuid.uuid4().hex[:24]}",
                            "name": (fn.name if fn and fn.name else ""),
                            "arguments": "",
                            "output_index": output_index,
                        }
                        yield _sse("response.output_item.added", {
                            "type": "response.output_item.added",
                            "output_index": output_index,
                            "item": {
                                "id": item_id,
                                "type": "function_call",
                                "call_id": tool_calls[tc_idx]["call_id"],
                                "name": tool_calls[tc_idx]["name"],
                                "arguments": "",
                                "status": "in_progress",
                            },
                        })
                    else:
                        if fn and fn.name and not tool_calls[tc_idx]["name"]:
                            tool_calls[tc_idx]["name"] = fn.name

                    args_delta = (fn.arguments if fn and fn.arguments else "")
                    if args_delta:
                        tool_calls[tc_idx]["arguments"] += args_delta
                        yield _sse("response.function_call_arguments.delta", {
                            "type": "response.function_call_arguments.delta",
                            "item_id": tool_calls[tc_idx]["item_id"],
                            "output_index": tool_calls[tc_idx]["output_index"],
                            "delta": args_delta,
                        })
        except Exception as e:
            yield _sse("error", {
                "type": "error",
                "error": {"message": f"Stream error: {e}"},
            })

        # ==================== ФИНАЛИЗАЦИЯ ====================
        collected: list[tuple[int, dict]] = []

        if reasoning_id is not None:
            yield _sse("response.reasoning_summary_text.done", {
                "type": "response.reasoning_summary_text.done",
                "item_id": reasoning_id,
                "output_index": reasoning_index,
                "summary_index": 0,
                "text": full_reasoning,
            })
            r_item = {
                "id": reasoning_id,
                "type": "reasoning",
                "status": "completed",
                "summary": [{"type": "summary_text", "text": full_reasoning}],
            }
            yield _sse("response.output_item.done", {
                "type": "response.output_item.done",
                "output_index": reasoning_index,
                "item": r_item,
            })
            collected.append((reasoning_index, r_item))

        if message_id is not None:
            final_text = maybe_fix_json(full_text) if full_text else ""
            yield _sse("response.output_text.done", {
                "type": "response.output_text.done",
                "item_id": message_id,
                "output_index": message_index,
                "content_index": 0,
                "text": final_text,
            })
            m_item = {
                "id": message_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": final_text}],
            }
            yield _sse("response.output_item.done", {
                "type": "response.output_item.done",
                "output_index": message_index,
                "item": m_item,
            })
            collected.append((message_index, m_item))

        for tc_idx in sorted(tool_calls.keys()):
            tc = tool_calls[tc_idx]
            yield _sse("response.function_call_arguments.done", {
                "type": "response.function_call_arguments.done",
                "item_id": tc["item_id"],
                "output_index": tc["output_index"],
                "arguments": tc["arguments"],
            })
            fc_item = {
                "id": tc["item_id"],
                "type": "function_call",
                "call_id": tc["call_id"],
                "name": tc["name"],
                "arguments": tc["arguments"],
                "status": "completed",
            }
            yield _sse("response.output_item.done", {
                "type": "response.output_item.done",
                "output_index": tc["output_index"],
                "item": fc_item,
            })
            collected.append((tc["output_index"], fc_item))

        collected.sort(key=lambda x: x[0])
        final_output = [item for _, item in collected]

        prompt_tokens = len(str(raw_input)) // 4
        completion_tokens = (
            len(full_text) // 4
            + len(full_reasoning) // 4
            + sum(len(tc["arguments"]) for tc in tool_calls.values()) // 4
        )
        total_tokens = prompt_tokens + completion_tokens
        remaining_tokens = max(0, MAX_CONTEXT_WINDOW - total_tokens)

        yield _sse("response.completed", {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": int(time.time()),
                "model": MODEL_IDENTIFIER,
                "status": "completed",
                "output": final_output,
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "context_window": {
                        "max_tokens": MAX_CONTEXT_WINDOW,
                        "tokens_used": total_tokens,
                        "tokens_remaining": remaining_tokens,
                    },
                },
            },
        })

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ==================== МОДЕЛИ ====================

@app.get("/v1/models")
async def list_models():
    current_time = int(time.time())
    return JSONResponse(content={
        "object": "list",
        "data": [
            {
                "id": MODEL_IDENTIFIER,
                "object": "model",
                "created": current_time - 86400,
                "owned_by": "qwen-local",
                "context_window": MAX_CONTEXT_WINDOW,
                "max_context_window": MAX_CONTEXT_WINDOW,
                "context_length": MAX_CONTEXT_WINDOW,
                "max_completion_tokens": 8192,
                "capabilities": {
                    "chat": True,
                    "embeddings": False,
                    "vision": True,
                    "video": True,
                    "tool_calling": True,
                    "structured_output": True,
                    "json_mode": True,
                    "streaming": True,
                    "reasoning": True,
                    "responses_api": True,
                    "context_window": MAX_CONTEXT_WINDOW,
                },
            }
        ],
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8999)