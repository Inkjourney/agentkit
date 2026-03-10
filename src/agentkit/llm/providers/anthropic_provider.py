"""Anthropic Messages API provider adapter."""

from __future__ import annotations

import json
from typing import Any

import requests

from agentkit.config.provider_defaults import DEFAULT_ANTHROPIC_BASE_URL
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

class AnthropicProvider(BaseLLMProvider):
    """Anthropic Messages API adapter."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.model = config.model
        self._session = requests.Session()

    def generate(self, req: UnifiedLLMRequest) -> UnifiedLLMResponse:
        payload = self._build_payload(req)

        try:
            response = self._session.post(
                self._messages_endpoint,
                headers=self._headers,
                json=payload,
                timeout=self.config.timeout_s,
            )
        except requests.Timeout as exc:  # pragma: no cover - network specific
            raise ProviderError(
                f"Anthropic request timed out: {exc}",
                issue=ProviderIssue(category="timeout", retryable=True),
            ) from exc
        except requests.RequestException as exc:  # pragma: no cover - network specific
            raise ProviderError(
                f"Anthropic request failed: {exc}",
                issue=ProviderIssue(category="upstream", retryable=True),
            ) from exc

        if response.status_code >= 400:
            self._raise_http_error(response)

        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(
                "Anthropic response is not valid JSON.",
                issue=ProviderIssue(category="parse", retryable=False),
            ) from exc

        return self._parse_response(body)

    @property
    def _messages_endpoint(self) -> str:
        base = self.config.base_url or DEFAULT_ANTHROPIC_BASE_URL
        if base.endswith("/v1/messages"):
            return base
        return f"{base.rstrip('/')}/v1/messages"

    @property
    def _headers(self) -> dict[str, str]:
        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.config.api_key:
            headers["x-api-key"] = self.config.api_key
        return headers

    def render_output_text(
        self,
        output_items: list[ConversationItem],
        raw_response: dict[str, object] | None,
    ) -> str:
        del raw_response
        texts = [
            item.text
            for item in output_items
            if isinstance(item, MessageItem) and item.role == "assistant" and item.text
        ]
        return "\n".join(texts).strip()

    def _build_payload(self, req: UnifiedLLMRequest) -> dict[str, Any]:
        messages = self._compile_messages(req.state.history + req.inputs)

        payload: dict[str, Any] = {
            "model": req.model,
            "messages": messages,
            "max_tokens": req.options.max_output_tokens or 1024,
        }

        if req.tools:
            payload["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters,
                }
                for tool in req.tools
            ]

        system_prompt = self._compile_system(req)
        if system_prompt:
            payload["system"] = system_prompt

        temperature = (
            req.options.temperature
            if req.options.temperature is not None
            else self.config.temperature
        )
        if temperature is not None:
            payload["temperature"] = temperature

        if req.options.stop_sequences:
            payload["stop_sequences"] = list(req.options.stop_sequences)

        return payload

    def _compile_system(self, req: UnifiedLLMRequest) -> str:
        return req.instructions.strip()

    def _compile_messages(self, items: list[ConversationItem]) -> list[dict[str, Any]]:
        raw_messages: list[dict[str, Any]] = []
        for item in items:
            message = self._item_to_message(item)
            if message is not None:
                raw_messages.append(message)

        return self._merge_consecutive_roles(raw_messages)

    def _item_to_message(self, item: ConversationItem) -> dict[str, Any] | None:
        if isinstance(item, MessageItem):
            return {
                "role": item.role,
                "content": [{"type": "text", "text": item.text}],
            }

        if isinstance(item, ToolCallItem):
            return {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": item.call_id,
                        "name": item.name,
                        "input": item.arguments,
                    }
                ],
            }

        if isinstance(item, ToolResultItem):
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": item.call_id,
                        "content": item.output_text,
                        "is_error": item.is_error,
                    }
                ],
            }

        if item.replay_hint and item.raw_item:
            block_type = str(item.raw_item.get("type") or "")
            if block_type in {"thinking", "redacted_thinking"}:
                return {"role": "assistant", "content": [item.raw_item]}

        return None

    def _merge_consecutive_roles(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not messages:
            return []

        merged: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "user")
            content = list(message.get("content") or [])
            if merged and merged[-1].get("role") == role:
                merged[-1].setdefault("content", [])
                merged[-1]["content"].extend(content)
            else:
                merged.append({"role": role, "content": content})
        return merged

    def _parse_response(self, body: dict[str, Any]) -> UnifiedLLMResponse:
        output_items: list[ConversationItem] = []

        for block_raw in body.get("content") or []:
            block = self._to_dict(block_raw)
            block_type = str(block.get("type") or "")

            if block_type == "text":
                text = str(block.get("text") or "")
                if text:
                    output_items.append(MessageItem(role="assistant", text=text))
                continue

            if block_type == "tool_use":
                output_items.append(
                    ToolCallItem(
                        call_id=str(block.get("id") or ""),
                        name=str(block.get("name") or ""),
                        arguments=self._ensure_dict(block.get("input")),
                    )
                )
                continue

            if block_type in {"thinking", "redacted_thinking"}:
                thinking_text = block.get("thinking")
                if not isinstance(thinking_text, str):
                    thinking_text = block.get("text") if isinstance(block.get("text"), str) else None
                output_items.append(
                    ReasoningItem(
                        text=thinking_text,
                        summary=None,
                        raw_item=block,
                        replay_hint=True,
                    )
                )

        status, reason = self._map_status(body, output_items)

        return UnifiedLLMResponse(
            response_id=str(body.get("id") or "") or None,
            status=status,
            reason=reason,
            output_items=output_items,
            output_text=self.render_output_text(output_items, body),
            usage=self._parse_usage(body),
            state_patch=StatePatch(),
            provider_name="anthropic",
            raw_response=body,
        )

    def _map_status(
        self,
        body: dict[str, Any],
        output_items: list[ConversationItem],
    ) -> tuple[TurnStatus, CompletionReason]:
        if any(isinstance(item, ToolCallItem) for item in output_items):
            return "requires_tool", "tool_call"

        stop_reason = str(body.get("stop_reason") or "")

        mapping: dict[str, tuple[TurnStatus, CompletionReason]] = {
            "end_turn": ("completed", "stop"),
            "stop_sequence": ("completed", "stop"),
            "max_tokens": ("incomplete", "max_tokens"),
            "tool_use": ("requires_tool", "tool_call"),
            "pause_turn": ("incomplete", "pause"),
            "refusal": ("blocked", "refusal"),
            "model_context_window_exceeded": ("incomplete", "context_window"),
        }
        if stop_reason in mapping:
            return mapping[stop_reason]

        if body.get("type") == "error":
            return "failed", "error"

        return "incomplete", "unknown"

    def _parse_usage(self, body: dict[str, Any]) -> Usage:
        usage = self._to_dict(body.get("usage") or {})
        input_tokens = self._as_int(usage.get("input_tokens"))
        output_tokens = self._as_int(usage.get("output_tokens"))

        total_tokens: int | None = None
        if input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens

        return Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cache_write_tokens=self._as_int(usage.get("cache_creation_input_tokens")),
            cache_read_tokens=self._as_int(usage.get("cache_read_input_tokens")),
            raw=usage or None,
        )

    def _raise_http_error(self, response: requests.Response) -> None:
        body: dict[str, Any] | None = None
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = None

        status = response.status_code
        category = "unknown"
        retryable = False
        provider_code: str | None = None

        if status in {401, 403}:
            category = "auth"
        elif status == 429:
            category = "rate_limit"
            retryable = True
        elif 400 <= status < 500:
            category = "invalid_request"
        elif status >= 500:
            category = "upstream"
            retryable = True

        if body:
            err = self._to_dict(body.get("error") or {})
            provider_code = str(err.get("type") or err.get("code") or "") or None
            err_message = str(err.get("message") or "").lower()
            if "safety" in err_message or "policy" in err_message:
                category = "safety"

        raise ProviderError(
            f"Anthropic request failed with status {status}.",
            issue=ProviderIssue(
                category=category,
                http_status=status,
                provider_code=provider_code,
                retryable=retryable,
                raw=body,
            ),
        )

    def _to_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            try:
                dumped = value.model_dump(mode="python")
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass
        return {}

    def _ensure_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
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
