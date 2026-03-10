"""OpenAI provider supporting Responses and Chat Completions APIs."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from agentkit.config.schema import ProviderConfig
from agentkit.errors import ProviderError, ProviderIssue
from agentkit.llm.base import BaseLLMProvider
from agentkit.llm.types import (
    CompletionReason,
    ConversationItem,
    MessageItem,
    ReasoningItem,
    StatePatch,
    ToolCallItem,
    ToolResultItem,
    TurnStatus,
    UnifiedLLMRequest,
    UnifiedLLMResponse,
    Usage,
)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider adapter for the unified request/response model."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.model = config.model
        self._api_variant = config.openai_api_variant

        client_kwargs: dict[str, Any] = {
            "timeout": config.timeout_s,
            "max_retries": config.retries,
        }
        if config.api_key:
            client_kwargs["api_key"] = config.api_key
        if config.base_url:
            client_kwargs["base_url"] = config.base_url

        self._client = OpenAI(**client_kwargs)

    def generate(self, req: UnifiedLLMRequest) -> UnifiedLLMResponse:
        if self._api_variant == "chat_completions":
            return self._generate_chat_completions(req)
        return self._generate_responses(req)

    def render_output_text(
        self,
        output_items: list[ConversationItem],
        raw_response: dict[str, object] | None,
    ) -> str:
        del raw_response
        assistant_texts = [
            item.text
            for item in output_items
            if isinstance(item, MessageItem) and item.role == "assistant"
        ]
        return "\n".join(text for text in assistant_texts if text).strip()

    def _generate_responses(self, req: UnifiedLLMRequest) -> UnifiedLLMResponse:
        if req.state.mode == "server" and self._api_variant != "responses":
            raise ProviderError(
                "conversation_mode='server' is only supported with OpenAI Responses.",
                issue=ProviderIssue(category="invalid_request", retryable=False),
            )

        use_server_cursor = req.state.mode == "server" or (
            req.state.mode == "auto" and bool(req.state.provider_cursor)
        )

        if use_server_cursor and req.state.provider_cursor:
            response_input = self._compile_responses_items(req.inputs)
        else:
            response_input = self._compile_responses_items(
                req.state.history + req.inputs
            )

        kwargs: dict[str, Any] = {
            "model": req.model,
            "input": response_input,
        }

        instructions_text = self._build_instruction_text(req)
        if instructions_text:
            kwargs["instructions"] = instructions_text

        if use_server_cursor and req.state.provider_cursor:
            kwargs["previous_response_id"] = req.state.provider_cursor

        if req.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
                for tool in req.tools
            ]

        temperature = self._resolve_option(
            req.options.temperature, self.config.temperature
        )
        if temperature is not None:
            kwargs["temperature"] = temperature

        if req.options.max_output_tokens is not None:
            kwargs["max_output_tokens"] = req.options.max_output_tokens

        if req.options.stop_sequences:
            kwargs["stop"] = list(req.options.stop_sequences)

        reasoning_effort = self._resolve_option(
            req.options.reasoning_effort,
            self.config.reasoning_effort,
        )
        if reasoning_effort and self._allow_reasoning_effort():
            kwargs["reasoning"] = {"effort": reasoning_effort}

        kwargs.update(self._extra_responses_kwargs(req))

        try:
            response = self._client.responses.create(**kwargs)
        except Exception as exc:  # pragma: no cover - provider/network specific
            raise ProviderError(
                f"OpenAI request failed: {exc}",
                issue=self._issue_from_exception(exc),
            ) from exc
        return self._parse_responses_response(response)

    def _generate_chat_completions(self, req: UnifiedLLMRequest) -> UnifiedLLMResponse:
        if req.state.mode == "server":
            raise ProviderError(
                "conversation_mode='server' is only supported with OpenAI Responses.",
                issue=ProviderIssue(category="invalid_request", retryable=False),
            )

        messages = self._compile_chat_messages(req.state.history + req.inputs, req)

        kwargs: dict[str, Any] = {
            "model": req.model,
            "messages": messages,
        }

        if req.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in req.tools
            ]

        temperature = self._resolve_option(
            req.options.temperature, self.config.temperature
        )
        if temperature is not None:
            kwargs["temperature"] = temperature

        if req.options.max_output_tokens is not None:
            kwargs["max_completion_tokens"] = req.options.max_output_tokens

        if req.options.stop_sequences:
            kwargs["stop"] = list(req.options.stop_sequences)

        reasoning_effort = self._resolve_option(
            req.options.reasoning_effort,
            self.config.reasoning_effort,
        )
        if reasoning_effort and self._allow_reasoning_effort():
            kwargs["reasoning_effort"] = reasoning_effort

        kwargs.update(self._extra_chat_kwargs(req))

        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # pragma: no cover - provider/network specific
            raise ProviderError(
                f"OpenAI request failed: {exc}",
                issue=self._issue_from_exception(exc),
            ) from exc
        return self._parse_chat_response(response)

    def _build_instruction_text(self, req: UnifiedLLMRequest) -> str:
        return req.instructions.strip()

    def _compile_responses_items(
        self, items: list[ConversationItem]
    ) -> list[dict[str, Any]]:
        compiled: list[dict[str, Any]] = []
        for item in items:
            payload = self._to_responses_item(item)
            if payload is not None:
                compiled.append(payload)
        return compiled

    def _compile_chat_messages(
        self,
        items: list[ConversationItem],
        req: UnifiedLLMRequest,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []

        instructions_text = req.instructions.strip()
        if instructions_text:
            messages.append({"role": "system", "content": instructions_text})

        index = 0
        while index < len(items):
            item = items[index]

            if isinstance(item, MessageItem):
                if item.role == "user":
                    messages.append({"role": "user", "content": item.text})
                    index += 1
                    continue
                assistant_message, next_index = self._consume_assistant_chat_turn(
                    items, index
                )
                if assistant_message is not None:
                    messages.append(assistant_message)
                    index = next_index
                    continue

            if isinstance(item, ToolResultItem):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": item.call_id,
                        "content": self._serialize_tool_result(item),
                    }
                )
                index += 1
                continue

            if isinstance(item, (ReasoningItem, ToolCallItem)):
                assistant_message, next_index = self._consume_assistant_chat_turn(
                    items, index
                )
                if assistant_message is not None:
                    messages.append(assistant_message)
                    index = next_index
                    continue

            index += 1

        return messages

    def _to_responses_item(self, item: ConversationItem) -> dict[str, Any] | None:
        if isinstance(item, MessageItem):
            return {
                "role": item.role,
                "content": item.text,
            }

        if isinstance(item, ToolCallItem):
            raw_arguments = item.raw_arguments
            if raw_arguments is None:
                raw_arguments = json.dumps(item.arguments, ensure_ascii=False)
            return {
                "type": "function_call",
                "call_id": item.call_id,
                "name": item.name,
                "arguments": raw_arguments,
            }

        if isinstance(item, ToolResultItem):
            return {
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": self._serialize_tool_result(item),
            }

        if item.replay_hint and item.raw_item:
            return item.raw_item

        return None

    def _serialize_tool_result(self, item: ToolResultItem) -> str:
        return item.output_text

    def _consume_assistant_chat_turn(
        self,
        items: list[ConversationItem],
        start_index: int,
    ) -> tuple[dict[str, Any] | None, int]:
        index = start_index
        consumed = False
        content: str | None = None
        content_seen = False
        tool_calls: list[dict[str, Any]] = []
        reasoning_fields: dict[str, Any] = {}

        while index < len(items):
            item = items[index]

            if isinstance(item, ReasoningItem):
                consumed = True
                reasoning_fields.update(self._reasoning_item_to_chat_fields(item))
                index += 1
                continue

            if isinstance(item, MessageItem) and item.role == "assistant":
                if content_seen:
                    break
                consumed = True
                content = item.text
                content_seen = True
                index += 1
                continue

            if isinstance(item, ToolCallItem):
                consumed = True
                tool_calls.append(self._to_chat_tool_call(item))
                index += 1
                continue

            break

        if not consumed:
            return None, start_index + 1

        message: dict[str, Any] = {"role": "assistant"}
        if content_seen:
            # Keep empty-string content as-is to preserve round-trip fidelity.
            message["content"] = content
        elif not tool_calls:
            message["content"] = ""

        if tool_calls:
            message["tool_calls"] = tool_calls
        if reasoning_fields:
            message.update(reasoning_fields)
        return message, index

    def _reasoning_item_to_chat_fields(self, item: ReasoningItem) -> dict[str, Any]:
        if not item.replay_hint:
            return {}

        raw = item.raw_item if isinstance(item.raw_item, dict) else None
        if raw:
            if raw.get("type") == "chat_reasoning":
                field_name = raw.get("field")
                if isinstance(field_name, str):
                    return {field_name: raw.get("value")}
            for field_name in (
                "reasoning",
                "reasoning_content",
                "reasoningContent",
                "thinking",
            ):
                if field_name in raw:
                    return {field_name: raw.get(field_name)}

        if item.text is not None:
            return {"reasoning": item.text}
        if item.summary is not None:
            return {"reasoning": item.summary}
        return {}

    def _to_chat_tool_call(self, item: ToolCallItem) -> dict[str, Any]:
        raw_arguments = item.raw_arguments
        if raw_arguments is None:
            raw_arguments = json.dumps(item.arguments, ensure_ascii=False)

        return {
            "id": item.call_id,
            "type": "function",
            "function": {
                "name": item.name,
                "arguments": raw_arguments,
            },
        }

    def _parse_responses_response(self, response: Any) -> UnifiedLLMResponse:
        raw_response = self._to_dict(response)
        output = self._get(response, "output", []) or []

        output_items: list[ConversationItem] = []
        saw_refusal = False

        for output_item in output:
            item = self._to_dict(output_item)
            item_type = str(item.get("type") or "")

            if item_type == "reasoning":
                output_items.append(self._to_reasoning_item(item))
                continue

            if item_type == "function_call":
                raw_arguments = item.get("arguments")
                raw_arguments_str = (
                    raw_arguments if isinstance(raw_arguments, str) else None
                )
                arguments = self._parse_arguments(raw_arguments)
                output_items.append(
                    ToolCallItem(
                        call_id=str(item.get("call_id") or item.get("id") or ""),
                        name=str(item.get("name") or ""),
                        arguments=arguments,
                        raw_arguments=raw_arguments_str,
                    )
                )
                continue

            if item_type == "message":
                role = str(item.get("role") or "assistant")
                if role not in {"assistant", "user"}:
                    role = "assistant"

                content_items = item.get("content")
                if isinstance(content_items, list):
                    for content_item in content_items:
                        content = self._to_dict(content_item)
                        ctype = str(content.get("type") or "")
                        if ctype in {"output_text", "text", "input_text"}:
                            text = str(content.get("text") or "")
                            if text:
                                output_items.append(MessageItem(role=role, text=text))  # type: ignore
                        elif ctype == "refusal":
                            refusal_text = str(
                                content.get("refusal") or content.get("text") or ""
                            )
                            if refusal_text:
                                saw_refusal = True
                                output_items.append(
                                    MessageItem(role="assistant", text=refusal_text)
                                )
                else:
                    text = str(item.get("content") or "")
                    if text:
                        output_items.append(MessageItem(role=role, text=text))  # type: ignore
                continue

            if item_type == "refusal":
                refusal_text = str(item.get("refusal") or item.get("text") or "")
                if refusal_text:
                    saw_refusal = True
                    output_items.append(
                        MessageItem(role="assistant", text=refusal_text)
                    )

        status, reason = self._map_responses_status(response, output_items, saw_refusal)

        output_text = self.render_output_text(
            output_items,
            raw_response if isinstance(raw_response, dict) else None,
        )
        if not output_text:
            output_text = str(self._get(response, "output_text", "") or "").strip()

        return UnifiedLLMResponse(
            response_id=str(self._get(response, "id", "") or "") or None,
            status=status,
            reason=reason,
            output_items=output_items,
            output_text=output_text,
            usage=self._parse_responses_usage(response),
            state_patch=StatePatch(
                new_provider_cursor=str(self._get(response, "id", "") or "") or None
            ),
            provider_name="openai",
            raw_response=raw_response if isinstance(raw_response, dict) else None,
        )

    def _parse_chat_response(self, response: Any) -> UnifiedLLMResponse:
        raw_response = self._to_dict(response)
        choices = self._get(response, "choices", []) or []
        if not choices:
            raise ProviderError(
                "OpenAI chat.completions response has no choices.",
                issue=ProviderIssue(category="parse", retryable=False),
            )

        choice = self._to_dict(choices[0])
        message = self._to_dict(choice.get("message") or {})
        if not message:
            raise ProviderError(
                "OpenAI chat.completions response missing choice message.",
                issue=ProviderIssue(category="parse", retryable=False),
            )

        output_items: list[ConversationItem] = []

        output_items.extend(self._extract_chat_reasoning_items(message))

        content = message.get("content")
        if isinstance(content, str):
            # Keep empty-string content so chat turn can be reconstructed exactly.
            output_items.append(MessageItem(role="assistant", text=content))
        elif isinstance(content, list):
            text_content = self._chat_content_list_to_text(content)
            if text_content is not None:
                output_items.append(MessageItem(role="assistant", text=text_content))

        saw_refusal = False
        refusal = message.get("refusal")
        if isinstance(refusal, str) and refusal.strip():
            saw_refusal = True
            output_items.append(MessageItem(role="assistant", text=refusal.strip()))

        for tool_call in message.get("tool_calls") or []:
            call = self._to_dict(tool_call)
            if str(call.get("type") or "") != "function":
                continue
            function = self._to_dict(call.get("function") or {})
            raw_arguments = function.get("arguments")
            raw_arguments_str = (
                raw_arguments if isinstance(raw_arguments, str) else None
            )
            output_items.append(
                ToolCallItem(
                    call_id=str(call.get("id") or call.get("call_id") or ""),
                    name=str(function.get("name") or ""),
                    arguments=self._parse_arguments(raw_arguments),
                    raw_arguments=raw_arguments_str,
                )
            )

        finish_reason = str(choice.get("finish_reason") or "")
        status, reason = self._map_chat_status(
            finish_reason=finish_reason,
            output_items=output_items,
            saw_refusal=saw_refusal,
        )

        return UnifiedLLMResponse(
            response_id=str(self._get(response, "id", "") or "") or None,
            status=status,
            reason=reason,
            output_items=output_items,
            output_text=self.render_output_text(
                output_items,
                raw_response if isinstance(raw_response, dict) else None,
            ),
            usage=self._parse_chat_usage(response),
            state_patch=StatePatch(),
            provider_name="openai",
            raw_response=raw_response if isinstance(raw_response, dict) else None,
        )

    def _map_responses_status(
        self,
        response: Any,
        output_items: list[ConversationItem],
        saw_refusal: bool,
    ) -> tuple[TurnStatus, CompletionReason]:
        if any(isinstance(item, ToolCallItem) for item in output_items):
            return "requires_tool", "tool_call"

        if saw_refusal:
            return "blocked", "refusal"

        status = str(self._get(response, "status", "") or "").lower()
        incomplete_details = self._to_dict(
            self._get(response, "incomplete_details") or {}
        )
        incomplete_reason = str(incomplete_details.get("reason") or "").lower()

        if incomplete_reason in {"max_output_tokens", "max_tokens", "length"}:
            return "incomplete", "max_tokens"
        if incomplete_reason in {
            "content_filter",
            "safety",
            "safety_violation",
            "recitation",
        }:
            return "blocked", "content_filter"
        if incomplete_reason in {"pause", "pause_turn"}:
            return "incomplete", "pause"
        if incomplete_reason in {
            "context_window",
            "context_window_exceeded",
            "model_context_window_exceeded",
        }:
            return "incomplete", "context_window"
        if incomplete_reason == "refusal":
            return "blocked", "refusal"

        if status in {"failed", "error", "cancelled"}:
            return "failed", "error"
        if status == "incomplete":
            return "incomplete", "unknown"
        if status == "completed" or not status:
            return "completed", "stop"

        return "failed", "unknown"

    def _map_chat_status(
        self,
        *,
        finish_reason: str,
        output_items: list[ConversationItem],
        saw_refusal: bool,
    ) -> tuple[TurnStatus, CompletionReason]:
        if any(isinstance(item, ToolCallItem) for item in output_items):
            return "requires_tool", "tool_call"

        if saw_refusal:
            return "blocked", "refusal"

        reason = finish_reason.lower()
        if reason in {"stop", "stop_sequence", "end_turn", ""}:
            return "completed", "stop"
        if reason in {"tool_calls", "tool_call"}:
            return "requires_tool", "tool_call"
        if reason in {"length", "max_tokens", "max_output_tokens"}:
            return "incomplete", "max_tokens"
        if reason in {"content_filter", "safety", "recitation"}:
            return "blocked", "content_filter"
        if reason in {"refusal"}:
            return "blocked", "refusal"
        if reason in {"context_window", "context_window_exceeded"}:
            return "incomplete", "context_window"

        return "incomplete", "unknown"

    def _parse_responses_usage(self, response: Any) -> Usage:
        usage = self._to_dict(self._get(response, "usage") or {})
        input_details = self._to_dict(
            usage.get("input_tokens_details") or usage.get("input_token_details") or {}
        )
        output_details = self._to_dict(
            usage.get("output_tokens_details")
            or usage.get("output_token_details")
            or {}
        )

        return Usage(
            input_tokens=self._as_int(usage.get("input_tokens")),
            output_tokens=self._as_int(usage.get("output_tokens")),
            total_tokens=self._as_int(usage.get("total_tokens")),
            reasoning_tokens=self._as_int(output_details.get("reasoning_tokens")),
            cache_read_tokens=self._as_int(
                input_details.get("cached_tokens") or usage.get("cached_tokens")
            ),
            cache_write_tokens=self._as_int(
                input_details.get("cache_creation_tokens")
                or usage.get("cache_creation_tokens")
            ),
            raw=usage or None,
        )

    def _parse_chat_usage(self, response: Any) -> Usage:
        usage = self._to_dict(self._get(response, "usage") or {})
        completion_details = self._to_dict(
            usage.get("completion_tokens_details")
            or usage.get("output_tokens_details")
            or {}
        )
        prompt_details = self._to_dict(
            usage.get("prompt_tokens_details")
            or usage.get("input_tokens_details")
            or {}
        )
        return Usage(
            input_tokens=self._as_int(usage.get("prompt_tokens")),
            output_tokens=self._as_int(usage.get("completion_tokens")),
            total_tokens=self._as_int(usage.get("total_tokens")),
            reasoning_tokens=self._as_int(completion_details.get("reasoning_tokens")),
            cache_read_tokens=self._as_int(prompt_details.get("cached_tokens")),
            raw=usage or None,
        )

    def _to_reasoning_item(self, item: dict[str, Any]) -> ReasoningItem:
        text: str | None = None
        summary: str | None = None

        raw_text = item.get("text")
        if isinstance(raw_text, str) and raw_text.strip():
            text = raw_text.strip()

        raw_summary = item.get("summary")
        if isinstance(raw_summary, str) and raw_summary.strip():
            summary = raw_summary.strip()
        elif isinstance(raw_summary, list):
            summary_parts: list[str] = []
            for part in raw_summary:
                part_dict = self._to_dict(part)
                part_text = (
                    part_dict.get("text")
                    or part_dict.get("summary")
                    or part_dict.get("content")
                )
                if isinstance(part_text, str) and part_text.strip():
                    summary_parts.append(part_text.strip())
            if summary_parts:
                summary = "\n".join(summary_parts)

        if text is None and summary is None:
            raw_thinking = item.get("thinking")
            if isinstance(raw_thinking, str) and raw_thinking.strip():
                text = raw_thinking.strip()

        return ReasoningItem(
            text=text, summary=summary, raw_item=item, replay_hint=True
        )

    def _extract_chat_reasoning_items(
        self, message: dict[str, Any]
    ) -> list[ReasoningItem]:
        reasoning_items: list[ReasoningItem] = []
        for field_name in (
            "reasoning",
            "reasoning_content",
            "thinking",
        ):
            if field_name not in message:
                continue
            value = message.get(field_name)
            text, summary = self._reasoning_text_and_summary_from_value(value)
            reasoning_items.append(
                ReasoningItem(
                    text=text,
                    summary=summary,
                    raw_item={
                        "type": "chat_reasoning",
                        "field": field_name,
                        "value": value,
                    },
                    replay_hint=True,
                )
            )
        return reasoning_items

    def _reasoning_text_and_summary_from_value(
        self, value: Any
    ) -> tuple[str | None, str | None]:
        if isinstance(value, str):
            return value, None
        if isinstance(value, dict):
            item = self._to_reasoning_item(value)
            return item.text, item.summary
        if isinstance(value, list):
            parts: list[str] = []
            for entry in value:
                if isinstance(entry, str):
                    parts.append(entry)
                    continue
                entry_dict = self._to_dict(entry)
                text = (
                    entry_dict.get("text")
                    or entry_dict.get("content")
                    or entry_dict.get("summary")
                )
                if isinstance(text, str):
                    parts.append(text)
            if parts:
                return "\n".join(parts), None
        return None, None

    def _chat_content_list_to_text(self, content: list[Any]) -> str | None:
        parts: list[str] = []
        for entry in content:
            entry_dict = self._to_dict(entry)
            text = entry_dict.get("text")
            if isinstance(text, str):
                parts.append(text)
        if parts:
            return "\n".join(parts)
        return None

    def _parse_arguments(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {"_raw": value}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        if value is None:
            return {}
        return {"value": value}

    def _issue_from_exception(self, exc: Exception) -> ProviderIssue:
        status = getattr(exc, "status_code", None)
        body = getattr(exc, "body", None)
        code = getattr(exc, "code", None)

        category = "unknown"
        retryable = False

        if isinstance(status, int):
            if status in {401, 403}:
                category = "auth"
            elif status == 429:
                category = "rate_limit"
                retryable = True
            elif status in {408, 504}:
                category = "timeout"
                retryable = True
            elif 400 <= status < 500:
                category = "invalid_request"
            elif status >= 500:
                category = "upstream"
                retryable = True

        message = str(exc).lower()
        if "timeout" in message and category == "unknown":
            category = "timeout"
            retryable = True
        if (
            "content filter" in message or "safety" in message
        ) and category == "unknown":
            category = "safety"

        raw: dict[str, Any] | None = None
        if isinstance(body, dict):
            raw = body

        return ProviderIssue(
            category=category,
            http_status=status if isinstance(status, int) else None,
            provider_code=str(code) if code else None,
            retryable=retryable,
            raw=raw,
        )

    def _resolve_option(self, request_value: Any, config_value: Any) -> Any:
        return request_value if request_value is not None else config_value

    def _allow_reasoning_effort(self) -> bool:
        return True

    def _extra_responses_kwargs(self, req: UnifiedLLMRequest) -> dict[str, Any]:
        del req
        return {}

    def _extra_chat_kwargs(self, req: UnifiedLLMRequest) -> dict[str, Any]:
        del req
        return {}

    def _as_int(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    def _to_dict(self, item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return item
        if hasattr(item, "model_dump"):
            try:
                dumped = item.model_dump(mode="python")
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass
        if hasattr(item, "__dict__"):
            try:
                dumped = dict(vars(item))
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass
        return {}

    def _get(self, obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)
