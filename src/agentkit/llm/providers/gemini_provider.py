"""Gemini GenerateContent API provider adapter."""

from __future__ import annotations

from typing import Any

import requests

from agentkit.config.provider_defaults import DEFAULT_GEMINI_BASE_URL
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

class GeminiProvider(BaseLLMProvider):
    """Gemini GenerateContent adapter."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.model = config.model
        self._session = requests.Session()

    def generate(self, req: UnifiedLLMRequest) -> UnifiedLLMResponse:
        payload = self._build_payload(req)

        try:
            response = self._session.post(
                self._endpoint(req.model),
                headers=self._headers,
                json=payload,
                timeout=self.config.timeout_s,
            )
        except requests.Timeout as exc:  # pragma: no cover - network specific
            raise ProviderError(
                f"Gemini request timed out: {exc}",
                issue=ProviderIssue(category="timeout", retryable=True),
            ) from exc
        except requests.RequestException as exc:  # pragma: no cover - network specific
            raise ProviderError(
                f"Gemini request failed: {exc}",
                issue=ProviderIssue(category="upstream", retryable=True),
            ) from exc

        if response.status_code >= 400:
            self._raise_http_error(response)

        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(
                "Gemini response is not valid JSON.",
                issue=ProviderIssue(category="parse", retryable=False),
            ) from exc

        return self._parse_response(body)

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

    @property
    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.config.api_key:
            headers["x-goog-api-key"] = self.config.api_key
        return headers

    def _endpoint(self, model: str) -> str:
        base = self.config.base_url or DEFAULT_GEMINI_BASE_URL
        if ":generateContent" in base:
            return base
        return f"{base.rstrip('/')}/models/{model}:generateContent"

    def _build_payload(self, req: UnifiedLLMRequest) -> dict[str, Any]:
        contents = self._compile_contents(req.state.history + req.inputs, req)

        payload: dict[str, Any] = {"contents": contents}

        system_instruction = self._compile_system_instruction(req)
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        if req.tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        }
                        for tool in req.tools
                    ]
                }
            ]

        generation_config: dict[str, Any] = {}
        temperature = (
            req.options.temperature
            if req.options.temperature is not None
            else self.config.temperature
        )
        if temperature is not None:
            generation_config["temperature"] = temperature
        if req.options.max_output_tokens is not None:
            generation_config["maxOutputTokens"] = req.options.max_output_tokens
        if req.options.stop_sequences:
            generation_config["stopSequences"] = list(req.options.stop_sequences)
        if generation_config:
            payload["generationConfig"] = generation_config

        return payload

    def _compile_system_instruction(self, req: UnifiedLLMRequest) -> dict[str, Any] | None:
        text = req.instructions.strip()
        if not text:
            return None
        return {"parts": [{"text": text}]}

    def _compile_contents(
        self,
        items: list[ConversationItem],
        req: UnifiedLLMRequest,
    ) -> list[dict[str, Any]]:
        call_name_map = req.state.provider_meta.get("tool_name_by_call_id", {})
        if not isinstance(call_name_map, dict):
            call_name_map = {}

        contents: list[dict[str, Any]] = []
        for item in items:
            content = self._item_to_content(item, call_name_map)
            if content is None:
                continue
            if contents and contents[-1]["role"] == content["role"]:
                contents[-1]["parts"].extend(content["parts"])
            else:
                contents.append(content)
        return contents

    def _item_to_content(
        self,
        item: ConversationItem,
        call_name_map: dict[str, Any],
    ) -> dict[str, Any] | None:
        if isinstance(item, MessageItem):
            role = "user" if item.role == "user" else "model"
            return {"role": role, "parts": [{"text": item.text}]}

        if isinstance(item, ToolCallItem):
            function_call: dict[str, Any] = {
                "name": item.name,
                "args": item.arguments,
            }
            if item.call_id:
                function_call["id"] = item.call_id
            return {"role": "model", "parts": [{"functionCall": function_call}]}

        if isinstance(item, ToolResultItem):
            tool_name = item.tool_name or call_name_map.get(item.call_id)
            if not isinstance(tool_name, str) or not tool_name:
                tool_name = "tool_result"
            if isinstance(item.payload, dict):
                response_payload = dict(item.payload)
                response_payload.setdefault("call_id", item.call_id)
                response_payload.setdefault("tool_name", tool_name)
            else:
                response_payload = {
                    "content": item.output_text,
                    "call_id": item.call_id,
                    "tool_name": tool_name,
                }
            return {
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": tool_name,
                            "response": response_payload,
                        }
                    }
                ],
            }

        if item.replay_hint and item.raw_item:
            if "thoughtSignature" in item.raw_item or item.raw_item.get("thought") is True:
                return {"role": "model", "parts": [item.raw_item]}

        return None

    def _parse_response(self, body: dict[str, Any]) -> UnifiedLLMResponse:
        prompt_feedback = self._to_dict(body.get("promptFeedback") or {})
        candidates = body.get("candidates") or []

        if prompt_feedback.get("blockReason") and not candidates:
            return UnifiedLLMResponse(
                response_id=None,
                status="blocked",
                reason="content_filter",
                output_items=[],
                output_text="",
                usage=self._parse_usage(body),
                state_patch=StatePatch(),
                provider_name="gemini",
                raw_response=body,
            )

        if not candidates:
            raise ProviderError(
                "Gemini response has no candidates.",
                issue=ProviderIssue(category="parse", retryable=False),
            )

        candidate = self._to_dict(candidates[0])
        content = self._to_dict(candidate.get("content") or {})
        parts = content.get("parts") or []

        output_items: list[ConversationItem] = []
        tool_name_patch: dict[str, str] = {}

        for idx, raw_part in enumerate(parts):
            part = self._to_dict(raw_part)

            function_call = self._to_dict(part.get("functionCall") or {})
            if function_call:
                call_id = str(function_call.get("id") or f"gemini-call-{idx + 1}")
                name = str(function_call.get("name") or "")
                arguments = function_call.get("args")
                if not isinstance(arguments, dict):
                    arguments = {}
                output_items.append(
                    ToolCallItem(
                        call_id=call_id,
                        name=name,
                        arguments=arguments,
                    )
                )
                if name:
                    tool_name_patch[call_id] = name
                continue

            has_thought = part.get("thought") is True or "thoughtSignature" in part
            if has_thought:
                reasoning_text = part.get("text") if isinstance(part.get("text"), str) else None
                output_items.append(
                    ReasoningItem(
                        text=reasoning_text,
                        summary=None,
                        raw_item=part,
                        replay_hint=True,
                    )
                )
                continue

            text = part.get("text")
            if isinstance(text, str) and text:
                output_items.append(MessageItem(role="assistant", text=text))

        status, reason = self._map_status(candidate, output_items)

        return UnifiedLLMResponse(
            response_id=None,
            status=status,
            reason=reason,
            output_items=output_items,
            output_text=self.render_output_text(output_items, body),
            usage=self._parse_usage(body),
            state_patch=StatePatch(provider_meta_patch={"tool_name_by_call_id": tool_name_patch}),
            provider_name="gemini",
            raw_response=body,
        )

    def _map_status(
        self,
        candidate: dict[str, Any],
        output_items: list[ConversationItem],
    ) -> tuple[TurnStatus, CompletionReason]:
        if any(isinstance(item, ToolCallItem) for item in output_items):
            return "requires_tool", "tool_call"

        finish_reason = str(candidate.get("finishReason") or "")
        mapping: dict[str, tuple[TurnStatus, CompletionReason]] = {
            "STOP": ("completed", "stop"),
            "MAX_TOKENS": ("incomplete", "max_tokens"),
            "SAFETY": ("blocked", "content_filter"),
            "RECITATION": ("blocked", "content_filter"),
            "BLOCKLIST": ("blocked", "content_filter"),
            "PROHIBITED_CONTENT": ("blocked", "content_filter"),
        }
        if finish_reason in mapping:
            return mapping[finish_reason]

        if finish_reason in {"MODEL_ARMOR", "MALFORMED_FUNCTION_CALL"}:
            return "failed", "error"

        return "incomplete", "unknown"

    def _parse_usage(self, body: dict[str, Any]) -> Usage:
        usage = self._to_dict(body.get("usageMetadata") or {})
        return Usage(
            input_tokens=self._as_int(usage.get("promptTokenCount")),
            output_tokens=self._as_int(usage.get("candidatesTokenCount")),
            total_tokens=self._as_int(usage.get("totalTokenCount")),
            reasoning_tokens=self._as_int(usage.get("thoughtsTokenCount")),
            cache_read_tokens=self._as_int(usage.get("cachedContentTokenCount")),
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

        provider_code: str | None = None
        if body:
            error = self._to_dict(body.get("error") or {})
            provider_code = str(error.get("status") or error.get("code") or "") or None
            err_message = str(error.get("message") or "").lower()
            if "safety" in err_message or "policy" in err_message:
                category = "safety"

        raise ProviderError(
            f"Gemini request failed with status {status}.",
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
