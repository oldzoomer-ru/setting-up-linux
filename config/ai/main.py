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

lm_client = AsyncOpenAI(
    base_url=f"{LM_STUDIO_URL}/v1",
    api_key="lm-studio",
    timeout=180.0,
    max_retries=0,
)


# ==================== JSON / TEXT HELPERS ====================

def _strip_fence(raw: str) -> str:
    """Strip a ```lang\\n...\\n``` fence from a complete string."""
    stripped = raw.strip()
    if not stripped.startswith("```"):
        return stripped
    parts = stripped.split("\n", 1)
    if len(parts) < 2:
        return ""
    body = parts[1]
    body_stripped = body.rstrip()
    if body_stripped.endswith("```"):
        body = body_stripped[:-3].rstrip()
    return body


def _try_repair_json(text: str) -> str:
    """Repair only if the result is a valid JSON string; else return original."""
    try:
        json.loads(text)
        return text
    except Exception:
        pass
    try:
        fixed = repair_json(text)
        if not isinstance(fixed, str):
            fixed = json.dumps(fixed, ensure_ascii=False)
        json.loads(fixed)
        return fixed
    except Exception:
        return text


def maybe_clean_text(text: str, aggressive: bool = False) -> str:
    """
    aggressive=False: only strip markdown fences (safe for any content).
    aggressive=True : also attempt JSON repair (only when response_format set).
    Note: JSON repair is never applied when the text contains a `<tool_call`
    block — that text is model output that happens to look JSON-ish, and
    repairing it can corrupt the payload.
    """
    if not text:
        return text
    stripped = text.strip()
    if not stripped:
        return text
    if "<tool_call" in stripped:
        aggressive = False
    if stripped.startswith("```"):
        body = _strip_fence(stripped)
        return _try_repair_json(body) if aggressive else body
    if aggressive and stripped.startswith(("{", "[")):
        return _try_repair_json(stripped)
    return text


def _extra(obj, key: str) -> str:
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


def _normalize_usage_dict(usage_obj) -> dict | None:
    """Normalize usage object or dict to a plain dict with int values."""
    if usage_obj is None:
        return None
    if isinstance(usage_obj, dict):
        p = usage_obj.get("prompt_tokens") or 0
        c = usage_obj.get("completion_tokens") or 0
        t = usage_obj.get("total_tokens") or (p + c)
        return {"prompt_tokens": int(p), "completion_tokens": int(c), "total_tokens": int(t)}
    p = getattr(usage_obj, "prompt_tokens", 0) or 0
    c = getattr(usage_obj, "completion_tokens", 0) or 0
    t = getattr(usage_obj, "total_tokens", 0) or (p + c)
    return {"prompt_tokens": int(p), "completion_tokens": int(c), "total_tokens": int(t)}


# ==================== TOOL CALL PARSING (Qwen format) ====================
#
# Qwen3 / Qwen3.6 emit tool calls as:
#
#   <tool_call>
#   {"name": "fn_name", "arguments": {"a": 1}}
#   </tool_call>
#
# This module handles both native `tool_calls` (from LM Studio) and the
# textual fallback when the backend fails to parse them server-side.


_OPEN_PREFIX = "<tool_call"
_CLOSE_TAG = "</tool_call>"


def _extract_inner(block: str) -> str:
    """Strip <tool_call...> and </tool_call> wrappers from a block."""
    inner = re.sub(r'<tool_call[^>]*>', '', block, count=1)
    inner = re.sub(r'</tool_call>\s*$', '', inner)
    return inner.strip()


def _parse_tool_call_json(inner: str) -> dict | None:
    """Parse the JSON body of a Qwen <tool_call> block."""
    inner = inner.strip()
    if not inner:
        return None
    obj = None
    try:
        obj = json.loads(inner)
    except Exception:
        try:
            fixed = repair_json(inner)
            obj = json.loads(fixed) if isinstance(fixed, str) else fixed
        except Exception:
            return None
    if not isinstance(obj, dict):
        return None
    name = obj.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    args = obj.get("arguments")
    if args is None:
        args = obj.get("parameters", {})
    if not isinstance(args, str):
        args = json.dumps(args, ensure_ascii=False)
    return {
        "type": "function_call",
        "id": f"fc_{uuid.uuid4().hex[:24]}",
        "call_id": f"call_{uuid.uuid4().hex[:24]}",
        "name": name.strip(),
        "arguments": args,
        "status": "completed",
    }


def _split_text_and_tools(raw_text: str) -> tuple[str, list[dict]]:
    if _OPEN_PREFIX not in raw_text:
        return raw_text, []
    tool_blocks = re.findall(r'<tool_call[^>]*>(.*?)</tool_call>', raw_text, re.DOTALL)
    clean_text = re.sub(r'<tool_call[^>]*>.*?</tool_call>', '', raw_text, flags=re.DOTALL).strip()
    items = []
    for inner in tool_blocks:
        item = _parse_tool_call_json(inner)
        if item:
            items.append(item)
    return clean_text, items


class ToolCallStreamParser:
    """Detects <tool_call>...</tool_call> blocks in streaming text."""

    def __init__(self):
        self.mode = "text"          # "text" | "in_tool"
        self.pending = ""           # bytes not yet classified
        self.tool_buf = ""
        self.tools: list[str] = []  # complete raw blocks, including tags

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        if self.mode == "in_tool":
            self.tool_buf += chunk
            if _CLOSE_TAG in self.tool_buf:
                idx = self.tool_buf.find(_CLOSE_TAG) + len(_CLOSE_TAG)
                self.tools.append(self.tool_buf[:idx])
                remainder = self.tool_buf[idx:]
                self.tool_buf = ""
                self.mode = "text"
                return self.feed(remainder)
            return ""

        self.pending += chunk
        idx = self.pending.find(_OPEN_PREFIX)
        if idx == -1:
            # keep a partial prefix at the tail
            for n in range(len(_OPEN_PREFIX) - 1, 0, -1):
                if self.pending.endswith(_OPEN_PREFIX[:n]):
                    emit = self.pending[:-n]
                    self.pending = self.pending[-n:]
                    return emit
            emit = self.pending
            self.pending = ""
            return emit

        emit = self.pending[:idx]
        rest = self.pending[idx + len(_OPEN_PREFIX):]
        self.pending = ""
        self.mode = "in_tool"
        self.tool_buf = _OPEN_PREFIX + rest
        if _CLOSE_TAG in self.tool_buf:
            cidx = self.tool_buf.find(_CLOSE_TAG) + len(_CLOSE_TAG)
            self.tools.append(self.tool_buf[:cidx])
            remainder = self.tool_buf[cidx:]
            self.tool_buf = ""
            self.mode = "text"
            return emit + self.feed(remainder)
        return emit

    def flush(self) -> tuple[str, list[str]]:
        if self.mode == "text":
            text = self.pending
            self.pending = ""
            return text, self.tools

        # in_tool mode: incomplete block — preserve whatever we have as text
        # (dropping it silently loses user-visible content).
        partial = self.tool_buf
        self.tool_buf = ""
        self.mode = "text"
        return partial, self.tools


class FenceStripper:
    """Streaming markdown-fence stripper (leading ``` and trailing ```)."""
    SUFFIX_KEEP = 4

    def __init__(self):
        self.prefix_buf = ""
        self.prefix_done = False
        self.had_fence = False
        self.suffix_buf = ""

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        if not self.prefix_done:
            self.prefix_buf += chunk
            stripped = self.prefix_buf.lstrip()
            if stripped.startswith("```"):
                nl = stripped.find("\n")
                if nl == -1:
                    return ""
                rest = stripped[nl + 1:]
                self.had_fence = True
                self.prefix_done = True
                self.prefix_buf = ""
                return self._suffix_feed(rest)
            self.prefix_done = True
            out = self.prefix_buf
            self.prefix_buf = ""
            return self._suffix_feed(out)
        return self._suffix_feed(chunk)

    def _suffix_feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self.suffix_buf += chunk
        if len(self.suffix_buf) <= self.SUFFIX_KEEP:
            return ""
        emit = self.suffix_buf[:-self.SUFFIX_KEEP]
        self.suffix_buf = self.suffix_buf[-self.SUFFIX_KEEP:]
        return emit

    def flush(self) -> str:
        out = ""
        if not self.prefix_done and self.prefix_buf:
            out += self.prefix_buf
            self.prefix_buf = ""
        buf = self.suffix_buf
        self.suffix_buf = ""
        stripped_tail = buf.rstrip()
        if self.had_fence and stripped_tail.endswith("```"):
            stripped_tail = stripped_tail[:-3].rstrip()
        out += stripped_tail
        return out


# ==================== INPUT TRANSFORMATION ====================

def _normalize_blocks(content):
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks = []
        for b in content:
            if not isinstance(b, dict):
                continue
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
        return blocks if blocks else None
    return str(content)


def transform_input_to_lm_studio(input_data) -> list:
    if isinstance(input_data, str):
        return [{"role": "user", "content": input_data}]
    if isinstance(input_data, dict):
        input_data = [input_data]
    if not isinstance(input_data, list) or not input_data:
        return [{"role": "user", "content": "Hello"}]

    messages = []
    assistant_buf = {
        "content": None,
        "reasoning_content": None,
        "tool_calls": [],
    }

    def flush_assistant():
        nonlocal assistant_buf
        if (
            assistant_buf["content"] is not None
            or assistant_buf["reasoning_content"]
            or assistant_buf["tool_calls"]
        ):
            msg = {"role": "assistant", "content": assistant_buf["content"]}
            if assistant_buf["reasoning_content"]:
                msg["reasoning_content"] = assistant_buf["reasoning_content"]
            if assistant_buf["tool_calls"]:
                msg["tool_calls"] = assistant_buf["tool_calls"]
            messages.append(msg)
        assistant_buf = {"content": None, "reasoning_content": None, "tool_calls": []}

    def append_content(new_content):
        if new_content is None:
            return
        if isinstance(new_content, (list, str)) and not new_content:
            return
        cur = assistant_buf["content"]
        if cur is None:
            assistant_buf["content"] = new_content
        elif isinstance(cur, str) and isinstance(new_content, str):
            assistant_buf["content"] = cur + new_content
        else:
            def to_blocks(c):
                if isinstance(c, str):
                    return [{"type": "text", "text": c}]
                return c
            assistant_buf["content"] = to_blocks(cur) + to_blocks(new_content)

    for item in input_data:
        if not isinstance(item, dict):
            continue
        itype = item.get("type", "message")

        if itype == "reasoning":
            text = "".join(
                s.get("text", "") for s in item.get("summary", []) if isinstance(s, dict)
            )
            if text:
                if assistant_buf["reasoning_content"]:
                    assistant_buf["reasoning_content"] += text
                else:
                    assistant_buf["reasoning_content"] = text
            continue

        if itype == "function_call":
            assistant_buf["tool_calls"].append({
                "id": item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": item.get("name", ""),
                    "arguments": item.get("arguments", "{}"),
                },
            })
            continue

        if itype == "function_call_output":
            flush_assistant()
            messages.append({
                "role": "tool",
                "tool_call_id": item.get("call_id", ""),
                "content": item.get("output", ""),
            })
            continue

        role = item.get("role", "user")
        content = _normalize_blocks(item.get("content"))

        if role == "assistant":
            reasoning = item.get("reasoning_content")
            if reasoning:
                if assistant_buf["reasoning_content"]:
                    assistant_buf["reasoning_content"] += reasoning
                else:
                    assistant_buf["reasoning_content"] = reasoning
            append_content(content)
        else:
            flush_assistant()
            messages.append({"role": role, "content": content})

    flush_assistant()
    return messages or [{"role": "user", "content": "Hello"}]


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
                "schema": fmt.get("schema") or {},
                # pass through whatever client asked; LM Studio will ignore
                # strict itself if it doesn't support it
                "strict": bool(fmt.get("strict", False)),
            },
        }
    if ftype == "json_object":
        return {"type": "json_object"}
    return None


def _apply_generation_params(body: dict, create_kwargs: dict, extra_body: dict):
    max_tokens = body.get("max_output_tokens")
    if max_tokens is None:
        max_tokens = body.get("max_tokens")
    if max_tokens is not None:
        try:
            create_kwargs["max_tokens"] = int(max_tokens)
        except (TypeError, ValueError):
            pass

    for param in ("temperature", "top_p", "frequency_penalty", "presence_penalty", "seed"):
        if body.get(param) is not None:
            create_kwargs[param] = body[param]

    if body.get("stop") is not None:
        create_kwargs["stop"] = body["stop"]

    if body.get("top_k") is not None:
        extra_body["top_k"] = body["top_k"]

    # top_logprobs implies logprobs in the Responses API, but OpenAI SDK /
    # Chat Completions requires logprobs=True explicitly.
    if body.get("top_logprobs") is not None:
        create_kwargs["logprobs"] = True
        try:
            create_kwargs["top_logprobs"] = int(body["top_logprobs"])
        except (TypeError, ValueError):
            pass
    elif body.get("logprobs") is not None:
        create_kwargs["logprobs"] = bool(body["logprobs"])


# ==================== SYNC PAYLOAD ====================

def _usage_sync(completion, input_items, raw_text, reasoning_text, tool_calls):
    usage = _normalize_usage_dict(getattr(completion, "usage", None))
    if usage is not None and usage["total_tokens"] > 0:
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]
        total_tokens = usage["total_tokens"]
    else:
        prompt_tokens = len(str(input_items)) // 4
        completion_tokens = (
            len(raw_text) // 4
            + len(reasoning_text or "") // 4
            + sum(len((tc.function.arguments or "")) for tc in (tool_calls or [])) // 4
        )
        total_tokens = prompt_tokens + completion_tokens
    remaining = max(0, MAX_CONTEXT_WINDOW - total_tokens)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "context_window": {
            "max_tokens": MAX_CONTEXT_WINDOW,
            "tokens_used": total_tokens,
            "tokens_remaining": remaining,
        },
    }


def create_responses_api_payload(
    completion: ChatCompletion, input_items, json_mode: bool = False
) -> dict:
    choice = completion.choices[0]
    message = choice.message
    finish_reason = choice.finish_reason

    raw_text = message.content or ""
    reasoning_text = _extra(message, "reasoning_content")
    native_tool_calls = message.tool_calls or []

    output = []

    if reasoning_text:
        output.append({
            "id": f"rs_{uuid.uuid4().hex[:24]}",
            "type": "reasoning",
            "status": "completed",
            "summary": [{"type": "summary_text", "text": reasoning_text}],
        })

    if raw_text:
        if native_tool_calls:
            # Native tools take priority; clean but do not attempt JSON repair
            # (text may contain tool_call XML that we must not mangle).
            clean_text = maybe_clean_text(
                raw_text, aggressive=json_mode and "<tool_call" not in raw_text
            )
            xml_items: list[dict] = []
        else:
            clean_text, xml_items = _split_text_and_tools(raw_text)
            if xml_items:
                clean_text = maybe_clean_text(clean_text, aggressive=False)
            else:
                clean_text = maybe_clean_text(clean_text, aggressive=json_mode)

        if clean_text:
            output.append({
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": clean_text, "annotations": []}],
            })
        output.extend(xml_items)

    for tc in native_tool_calls:
        fn = tc.function
        output.append({
            "type": "function_call",
            "id": f"fc_{uuid.uuid4().hex[:24]}",
            "call_id": tc.id,
            "name": fn.name,
            "arguments": fn.arguments or "{}",
            "status": "completed",
        })

    status = "completed"
    incomplete_details = None
    if finish_reason == "length":
        status = "incomplete"
        incomplete_details = {"reason": "max_output_tokens"}
    elif finish_reason == "content_filter":
        status = "incomplete"
        incomplete_details = {"reason": "content_filter"}

    payload = {
        "id": f"resp_{uuid.uuid4().hex[:24]}",
        "object": "response",
        "created_at": int(time.time()),
        "model": MODEL_IDENTIFIER,
        "status": status,
        "output": output,
        "usage": _usage_sync(completion, input_items, raw_text, reasoning_text, native_tool_calls),
    }
    if incomplete_details:
        payload["incomplete_details"] = incomplete_details
    return payload


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_failed(response_id: str, created_at: int, err_message: str) -> str:
    return _sse("response.failed", {
        "type": "response.failed",
        "response": {
            "id": response_id,
            "object": "response",
            "created_at": created_at,
            "model": MODEL_IDENTIFIER,
            "status": "failed",
            "output": [],
            "error": {"code": "stream_error", "message": err_message},
        },
    })


# ==================== HTTP HANDLER ====================

@app.post("/v1/responses")
async def handle_openai_responses_api(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    raw_input = body.get("input")
    if raw_input is None:
        raw_input = body.get("messages")
    if raw_input is None:
        raw_input = [{"role": "user", "content": "Hello"}]

    instructions = body.get("instructions")

    stream_flag = body.get("stream", False)
    if isinstance(stream_flag, str):
        should_stream = stream_flag.lower() == "true"
    else:
        should_stream = bool(stream_flag)

    messages = transform_input_to_lm_studio(raw_input)
    if instructions:
        if messages and messages[0].get("role") == "system":
            existing = messages[0].get("content") or ""
            if isinstance(existing, str) and isinstance(instructions, str):
                messages[0] = {
                    "role": "system",
                    "content": instructions + "\n\n" + existing,
                }
            else:
                messages = [{"role": "system", "content": instructions}] + messages
        else:
            messages = [{"role": "system", "content": instructions}] + messages

    # --- Reasoning config ---
    preserve_thinking = body.get("preserve_thinking")
    if preserve_thinking is None:
        rcfg = body.get("reasoning", {})
        if isinstance(rcfg, dict):
            preserve_thinking = rcfg.get("preserve_thinking")
    enable_thinking = body.get("enable_thinking")
    if enable_thinking is None:
        enable_thinking = True

    extra_body = {
        "chat_template_kwargs": {
            "enable_thinking": bool(enable_thinking),
            "preserve_thinking": bool(preserve_thinking) if preserve_thinking is not None else True,
        }
    }

    tools = convert_tools_to_lm(body.get("tools"))
    tool_choice = convert_tool_choice(body.get("tool_choice"))
    response_format = convert_text_format(body.get("text", {}))
    json_mode = response_format is not None

    create_kwargs: dict = {
        "model": MODEL_IDENTIFIER,
        "messages": messages,
        "stream": should_stream,
        "extra_body": extra_body,
    }

    if tools:
        create_kwargs["tools"] = tools
        if tool_choice is not None:
            create_kwargs["tool_choice"] = tool_choice
        if body.get("parallel_tool_calls") is not None:
            create_kwargs["parallel_tool_calls"] = bool(body["parallel_tool_calls"])

    if response_format is not None:
        create_kwargs["response_format"] = response_format

    _apply_generation_params(body, create_kwargs, extra_body)

    if should_stream:
        create_kwargs["stream_options"] = {"include_usage": True}

    # ==================== SYNC ====================
    if not should_stream:
        try:
            completion = await lm_client.chat.completions.create(**create_kwargs)
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={"error": {"message": f"LM Studio error: {e}"}},
            )

        if not completion.choices:
            return JSONResponse(
                status_code=502,
                content={"error": {"message": "Empty choices from LM Studio"}},
            )

        return JSONResponse(
            content=create_responses_api_payload(completion, raw_input, json_mode=json_mode)
        )

    # ==================== STREAM ====================
    async def event_generator():
        response_id = f"resp_{uuid.uuid4().hex[:24]}"
        created_at = int(time.time())
        next_index = 0

        message_id = None
        message_index = None
        full_text = ""

        reasoning_id = None
        reasoning_index = None
        full_reasoning = ""

        tool_calls: dict[int, dict] = {}
        finish_reason = None
        stream_usage: dict | None = None

        fence_stripper = FenceStripper()
        xml_parser = ToolCallStreamParser()

        async def ensure_message():
            """Emit `output_item.added` + `content_part.added` lazily, only
            when there is real text to emit. Prevents an empty `message`
            item in the stream that the sync path would have dropped."""
            nonlocal message_id, message_index, next_index
            if message_id is not None:
                return
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
            yield _sse("response.content_part.added", {
                "type": "response.content_part.added",
                "item_id": message_id,
                "output_index": message_index,
                "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": []},
            })

        yield _sse("response.created", {
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": created_at,
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
            yield _sse_failed(response_id, created_at, f"LM Studio error: {e}")
            return

        try:
            async for chunk in stream:
                # Usage may come on the final chunk (dict or object).
                usage_obj = getattr(chunk, "usage", None)
                if usage_obj is None:
                    extra = getattr(chunk, "model_extra", {}) or {}
                    usage_obj = extra.get("usage")
                normalized = _normalize_usage_dict(usage_obj)
                if normalized is not None:
                    stream_usage = normalized

                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason

                delta: ChoiceDelta = choice.delta

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
                        yield _sse("response.reasoning_summary_part.added", {
                            "type": "response.reasoning_summary_part.added",
                            "item_id": reasoning_id,
                            "output_index": reasoning_index,
                            "summary_index": 0,
                            "part": {"type": "summary_text", "text": ""},
                        })
                    full_reasoning += reasoning_delta
                    yield _sse("response.reasoning_summary_text.delta", {
                        "type": "response.reasoning_summary_text.delta",
                        "item_id": reasoning_id,
                        "output_index": reasoning_index,
                        "summary_index": 0,
                        "delta": reasoning_delta,
                    })

                # --- TEXT (fence strip + tool-call XML detection) ---
                chunk_text = delta.content or ""
                if chunk_text:
                    filtered = fence_stripper.feed(chunk_text)
                    emitted = xml_parser.feed(filtered)
                    if emitted:
                        async for ev in ensure_message():
                            yield ev
                        full_text += emitted
                        yield _sse("response.output_text.delta", {
                            "type": "response.output_text.delta",
                            "item_id": message_id,
                            "output_index": message_index,
                            "content_index": 0,
                            "delta": emitted,
                        })

                # --- NATIVE TOOL CALLS ---
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
            yield _sse_failed(response_id, created_at, f"Stream error: {e}")
            return

        # --- Flush streaming parsers ---
        xml_tool_blocks: list[str] = []
        try:
            tail = fence_stripper.flush()
            emitted = xml_parser.feed(tail)
            if emitted:
                async for ev in ensure_message():
                    yield ev
                full_text += emitted
                yield _sse("response.output_text.delta", {
                    "type": "response.output_text.delta",
                    "item_id": message_id,
                    "output_index": message_index,
                    "content_index": 0,
                    "delta": emitted,
                })

            remaining, xml_tool_blocks = xml_parser.flush()
            if remaining:
                async for ev in ensure_message():
                    yield ev
                full_text += remaining
                yield _sse("response.output_text.delta", {
                    "type": "response.output_text.delta",
                    "item_id": message_id,
                    "output_index": message_index,
                    "content_index": 0,
                    "delta": remaining,
                })
        except Exception:
            # Never let parser cleanup break finalization.
            pass

        # ==================== FINALIZATION ====================
        collected: list[tuple[int, dict]] = []

        # --- Reasoning ---
        if reasoning_id is not None:
            yield _sse("response.reasoning_summary_text.done", {
                "type": "response.reasoning_summary_text.done",
                "item_id": reasoning_id,
                "output_index": reasoning_index,
                "summary_index": 0,
                "text": full_reasoning,
            })
            yield _sse("response.reasoning_summary_part.done", {
                "type": "response.reasoning_summary_part.done",
                "item_id": reasoning_id,
                "output_index": reasoning_index,
                "summary_index": 0,
                "part": {"type": "summary_text", "text": full_reasoning},
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

        # --- Message ---
        if message_id is not None:
            yield _sse("response.output_text.done", {
                "type": "response.output_text.done",
                "item_id": message_id,
                "output_index": message_index,
                "content_index": 0,
                "text": full_text,
            })
            yield _sse("response.content_part.done", {
                "type": "response.content_part.done",
                "item_id": message_id,
                "output_index": message_index,
                "content_index": 0,
                "part": {"type": "output_text", "text": full_text, "annotations": []},
            })
            m_item = {
                "id": message_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": full_text, "annotations": []}],
            }
            yield _sse("response.output_item.done", {
                "type": "response.output_item.done",
                "output_index": message_index,
                "item": m_item,
            })
            collected.append((message_index, m_item))

        # --- XML fallback tools ---
        for block in xml_tool_blocks:
            parsed = _parse_tool_call_json(_extract_inner(block))
            if not parsed:
                continue
            output_index = next_index
            next_index += 1
            yield _sse("response.output_item.added", {
                "type": "response.output_item.added",
                "output_index": output_index,
                "item": {
                    "id": parsed["id"],
                    "type": "function_call",
                    "call_id": parsed["call_id"],
                    "name": parsed["name"],
                    "arguments": "",
                    "status": "in_progress",
                },
            })
            yield _sse("response.function_call_arguments.delta", {
                "type": "response.function_call_arguments.delta",
                "item_id": parsed["id"],
                "output_index": output_index,
                "delta": parsed["arguments"],
            })
            yield _sse("response.function_call_arguments.done", {
                "type": "response.function_call_arguments.done",
                "item_id": parsed["id"],
                "output_index": output_index,
                "arguments": parsed["arguments"],
            })
            yield _sse("response.output_item.done", {
                "type": "response.output_item.done",
                "output_index": output_index,
                "item": parsed,
            })
            collected.append((output_index, parsed))

        # --- Native tools ---
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

        # --- Usage ---
        if stream_usage is not None and stream_usage["total_tokens"] > 0:
            prompt_tokens = stream_usage["prompt_tokens"]
            completion_tokens = stream_usage["completion_tokens"]
            total_tokens = stream_usage["total_tokens"]
        else:
            prompt_tokens = len(str(raw_input)) // 4
            completion_tokens = (
                len(full_text) // 4
                + len(full_reasoning) // 4
                + sum(len(tc["arguments"]) for tc in tool_calls.values()) // 4
            )
            total_tokens = prompt_tokens + completion_tokens
        remaining_tokens = max(0, MAX_CONTEXT_WINDOW - total_tokens)

        # --- Status ---
        status = "completed"
        incomplete_details = None
        if finish_reason == "length":
            status = "incomplete"
            incomplete_details = {"reason": "max_output_tokens"}
        elif finish_reason == "content_filter":
            status = "incomplete"
            incomplete_details = {"reason": "content_filter"}

        final_response = {
            "id": response_id,
            "object": "response",
            "created_at": created_at,
            "model": MODEL_IDENTIFIER,
            "status": status,
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
        }
        if incomplete_details:
            final_response["incomplete_details"] = incomplete_details

        event_type = "response.incomplete" if status == "incomplete" else "response.completed"
        yield _sse(event_type, {
            "type": event_type,
            "response": final_response,
        })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ==================== MODELS ====================

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
