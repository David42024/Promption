"""Vercel AI SDK bridge with optional legacy provider adapters."""
import asyncio
import logging
import random
import time
from functools import wraps
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

import httpx
from promption.metrics_aggregator import MetricsAggregator

from promption.llm.exceptions import (
    LLMConfigurationError,
    LLMConnectivityError,
    LLMError,
    LLMInvalidResponseError,
    LLMProviderUnavailableError,
    LLMQuotaError,
    LLMTimeoutError,
    parse_retry_after,
)
from .config import settings
from .deadline import RequestDeadline
from .http_client import get_shared_http_client
from .models import LLMResponse


logger = logging.getLogger(__name__)
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient

def _resolve_client(explicit_client: Optional[httpx.AsyncClient] = None):
    if explicit_client is not None:
        return explicit_client
    if httpx.AsyncClient is not _ORIGINAL_ASYNC_CLIENT:
        try:
            return httpx.AsyncClient()
        except TypeError:
            return httpx.AsyncClient
    return get_shared_http_client()

_attempt_metrics = ContextVar("llm_attempt_metrics", default=None)


class _AttemptMetrics:
    """Keep each transport attempt and remote consumption summary isolated."""

    def __init__(self):
        self.aggregator = MetricsAggregator()
        self.events = []

    def record(self, data=None, failed=False):
        data = data if isinstance(data, dict) else {}
        calls = data.get("provider_calls")
        calls = int(calls) if isinstance(calls, int) and calls >= 0 else 1
        scope = data.get("scope_calls", 0)
        scope = scope if isinstance(scope, int) and 0 <= scope <= calls else 0
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        known = data.get("known_usage")
        coverage = data.get("usage_coverage")
        if not isinstance(known, dict) or not isinstance(coverage, dict):
            local = MetricsAggregator()
            local.add_call("generation", calls=calls,
                prompt_tokens=_extract_token_count(usage, "prompt_tokens", "input_tokens"),
                completion_tokens=_extract_token_count(usage, "completion_tokens", "output_tokens"),
                total_tokens=_extract_token_count(usage, "total_tokens"),
                reasoning_tokens=_extract_token_count(usage, "reasoning_tokens"))
            base = local.summary()
            known, coverage = base["known_usage"], base["usage_coverage"]
        summary = {"provider_calls": calls, "generation_calls": calls - scope,
                   "scope_calls": scope, "failed_calls": data.get("failed_calls", calls if failed else 0),
                   "known_usage": known, "usage_coverage": coverage}
        event_id = f"attempt-{len(self.events) + 1}"
        self.aggregator.add_summary(summary, event_id)
        self.events.append(summary)

    def packet(self):
        return {**self.aggregator.summary(), "usage_events": self.events}

    def fail_last(self):
        if self.events and self.events[-1]["failed_calls"] == 0:
            self.events[-1]["failed_calls"] = self.events[-1]["provider_calls"]
            self.aggregator = MetricsAggregator()
            for index, event in enumerate(self.events):
                self.aggregator.add_summary(event, f"attempt-{index + 1}")


def _track_attempts(method):
    @wraps(method)
    async def tracked(*args, **kwargs):
        metrics = _AttemptMetrics()
        token = _attempt_metrics.set(metrics)
        try:
            result = await method(*args, **kwargs)
            packet = metrics.packet()
            if isinstance(result, LLMResponse):
                return result.model_copy(update=packet)
            return {**result, **packet}
        except BaseException as exc:
            metrics.fail_last()
            for name, value in metrics.packet().items():
                setattr(exc, name, value)
            raise
        finally:
            _attempt_metrics.reset(token)
    return tracked


async def _post_http(client, url, **kwargs):
    metrics = _attempt_metrics.get()
    try:
        if not isinstance(client, _ORIGINAL_ASYNC_CLIENT) and hasattr(client, "__aenter__"):
            async with client as active_client:
                response = await active_client.post(url, **kwargs)
        else:
            response = await client.post(url, **kwargs)
    except BaseException:
        if metrics is not None:
            metrics.record(failed=True)
        raise
    if metrics is not None:
        try:
            data = response.json()
        except (ValueError, TypeError):
            data = None
        metrics.record(data, failed=getattr(response, "status_code", 200) >= 400)
    return response

_guard_identity = ContextVar("vercel_ai_guard_identity", default=None)


class AIGuardBlocked(Exception):
    """Carry a sanitized model-guard failure without treating it as provider downtime."""

    def __init__(self, code: str, scope: dict | None = None, provider_calls: int = 0):
        self.code = code
        self.scope = scope
        self.provider_calls = provider_calls
        super().__init__(code)


def _raise_bridge_guard(response: httpx.Response) -> None:
    if response.status_code not in {403, 503}:
        return
    try:
        data = response.json()
    except ValueError:
        data = {}
    codes = {
        "OUT_OF_SCOPE", "SCOPE_UNCERTAIN", "CONTENT_BLOCKED", "GUARD_UNAVAILABLE",
        "INVALID_GUARD_RESPONSE", "GUARD_REQUEST_FAILED", "TOOL_ACCESS_DENIED",
        "CONVERSATION_TOO_LARGE", "CONVERSATION_NOT_CHECKED", "CONVERSATION_REDACTED",
        "UNTRUSTED_TOOL_CONTENT", "TOOL_ARGUMENTS_REDACTED", "STRUCTURED_OUTPUT_REDACTED",
        "UNINSPECTED_MODEL_FILE"
    }
    code = data.get("code") if isinstance(data, dict) else None
    if code in codes or response.status_code == 403:
        scope = data.get("scope") if isinstance(data, dict) else None
        calls = int(data.get("provider_calls", 0)) if isinstance(data, dict) and str(data.get("provider_calls", "")).isdigit() else 0
        raise AIGuardBlocked(code if code in codes else "CONTENT_BLOCKED", scope, provider_calls=calls)


def _extract_token_count(usage: dict | None, *keys: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    for k in keys:
        if k in usage and usage[k] is not None:
            try:
                return int(usage[k])
            except (ValueError, TypeError):
                pass
    return None


def set_guard_identity(user_id: str, roles: list[str], original_text: str,
                       authenticated: bool = False, security_messages: list | None = None,
                       request_id: str | None = None):
    _guard_identity.set({
        "user_id": user_id,
        "roles": roles,
        "original_text": original_text,
        "authenticated": authenticated,
        "security_messages": security_messages or [],
        "request_id": request_id,
    })


def _bridge_payload(config: dict, messages: list, tools: list | None = None,
                    force_tool: str | None = None, max_tokens: int | None = None,
                    timeout_ms: int | None = None) -> dict:
    identity = _guard_identity.get() or {}
    original_text = identity.get("original_text") or next(
        (item.get("content") for item in reversed(messages) if item.get("role") == "user"), "")
    payload = {
        "model": config["model"], "messages": messages, "tools": tools or [],
        "force_tool": force_tool, "max_tokens": max_tokens or config["max_tokens"],
        "user_id": identity.get("user_id", "system"),
        "roles": identity.get("roles", ["guest"]), "original_text": original_text,
        "authenticated": identity.get("authenticated", False),
        "security_messages": identity.get("security_messages", []),
        "request_id": identity.get("request_id"),
    }
    if timeout_ms is not None and timeout_ms > 0:
        payload["timeout_ms"] = timeout_ms
    return payload


def _calculate_backoff(attempt: int, base_backoff: float, retry_after: float | None = None) -> float:
    if retry_after is not None:
        return retry_after
    max_delay = base_backoff * (2 ** attempt)
    return random.uniform(0.5 * max_delay, max_delay)


class LLMClient:
    """Client for LLM integration with provider fallback within a shared monotonic deadline."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self.client = client
        self.gemini_api_key = settings.gemini_api_key
        self.groq_api_key = settings.groq_api_key
        self.openrouter_api_key = settings.openrouter_api_key
        self.provider_timeout = max(0.5, settings.llm_provider_timeout_seconds)
        self.total_timeout = max(0.5, settings.llm_total_timeout_seconds)
        self.max_attempts = max(1, settings.llm_max_attempts)
        self.retry_backoff = max(0.0, settings.llm_retry_backoff_seconds)
        self.models = self._get_available_models()

    async def check_health(self) -> bool:
        """Check if any LLM provider is available and configured."""
        return len(self.models) > 0

    def _get_available_models(self) -> List[Dict[str, Any]]:
        models_by_provider = {
            "openai": self._get_openai_models(),
            "gemini": self._get_gemini_models(),
            "groq": self._get_groq_models(),
            "openrouter": self._get_openrouter_models(),
        }
        models: List[Dict[str, Any]] = []
        provider_order = [
            provider.strip().lower()
            for provider in settings.llm_provider_order.split(",")
            if provider.strip()
        ]
        ordered_providers = provider_order or ["openai"]
        for provider in ordered_providers:
            provider_models = models_by_provider.get(provider, [])
            if provider_models:
                models.append(provider_models[0])
        for provider in ordered_providers:
            models.extend(models_by_provider.get(provider, [])[1:])
        return models

    def _get_openai_models(self) -> List[Dict[str, Any]]:
        if not (settings.vercel_ai_url and settings.openai_model and settings.openai_tool_model):
            return []
        return [
            {"id": model_id, "label": f"OpenAI · {model}", "provider": "openai",
             "api": "vercel_ai", "model": model, "base_url": settings.vercel_ai_url,
             "temperature": 0.2, "max_tokens": max_tokens}
            for model_id, model, max_tokens in (
                ("openai-primary", settings.openai_model, settings.token_budget_chat),
                ("openai-tools", settings.openai_tool_model, settings.token_budget_tools),
            )
        ]

    def _get_gemini_models(self) -> List[Dict[str, Any]]:
        if not self.gemini_api_key:
            return []
        return [{
            "id": "gemini-primary",
            "label": f"Gemini · {settings.gemini_model}",
            "provider": "gemini",
            "api": "gemini",
            "model": settings.gemini_model,
            "api_key": self.gemini_api_key,
            "base_url": f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
            "temperature": 0.18,
            "max_tokens": 600
        }]

    def _get_groq_models(self) -> List[Dict[str, Any]]:
        if self.groq_api_key:
            return [{
                "id": "groq-primary",
                "label": "Groq · llama-3.3-70b",
                "provider": "groq",
                "api": "groq",
                "model": "llama-3.3-70b-versatile",
                "api_key": self.groq_api_key,
                "base_url": "https://api.groq.com/openai/v1/chat/completions",
                "temperature": 0.2,
                "max_tokens": 2000
            }]
        return []

    def _get_openrouter_models(self) -> List[Dict[str, Any]]:
        if self.openrouter_api_key:
            return [{
                "id": "openrouter-primary",
                "label": "OpenRouter · Claude 3.5 Sonnet",
                "provider": "openrouter",
                "api": "openrouter",
                "model": "anthropic/claude-3.5-sonnet",
                "api_key": self.openrouter_api_key,
                "base_url": "https://openrouter.ai/api/v1/chat/completions",
                "temperature": 0.2,
                "max_tokens": 2000
            }]
        return []

    def _build_gemini_payload(self, messages: List[Dict[str, str]],
                              temperature: float, max_tokens: int) -> Dict[str, Any]:
        system_parts = []
        contents = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "tool":
                response = {"name": message["name"], "response": {"result": message["result"]}}
                if message.get("id"):
                    response["id"] = message["id"]
                contents.append({"role": "user", "parts": [{"functionResponse": response}]})
                continue
            if role == "assistant" and message.get("gemini_parts"):
                contents.append({"role": "model", "parts": message["gemini_parts"]})
                continue
            if role == "system":
                system_parts.append({"text": content})
                continue

            gemini_role = "model" if role == "assistant" else "user"
            contents.append({
                "role": gemini_role,
                "parts": [{"text": content}]
            })

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }

        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}

        return payload

    def _extract_text(self, provider: str, data: Dict[str, Any]) -> str:
        if not isinstance(data, dict):
            return ""
        if provider == "gemini":
            candidates = data.get("candidates", [])
            if candidates and isinstance(candidates[0], dict):
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts and isinstance(parts[0], dict):
                    return str(parts[0].get("text", "")).strip()
            return ""
        if "text" in data:
            return str(data["text"]).strip()
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                return str(choice.get("message", {}).get("content", "")).strip()
        return ""

    @_track_attempts
    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        deadline: Optional[RequestDeadline] = None,
    ) -> LLMResponse:
        """Generate a response using ordered fallback within a monotonic deadline."""
        if not self.models:
            raise LLMConfigurationError(
                "No LLM providers configured. Configure VERCEL_AI_URL in Chat Service and "
                "OPENAI_API_KEY in Next.js."
            )

        budget = deadline or RequestDeadline(self.total_timeout)
        budget.check_expired("generate")
        last_exception: Optional[Exception] = None
        client = _resolve_client(self.client)
        requested_model = self.models[0]["label"] if self.models else ""
        fallback_count = 0
        fallback_reason = None
        prior_provider_calls = 0

        for model_idx, model_config in enumerate(self.models):
            if model_idx > 0:
                fallback_count += 1
                fallback_reason = str(last_exception) if last_exception else "Previous model failed"
                logger.warning("LLM fallback triggered: requested=%s fallback_to=%s reason=%s",
                               requested_model, model_config["label"], fallback_reason)
            for attempt in range(self.max_attempts):
                if budget.is_expired:
                    exc = LLMTimeoutError("Total time budget exhausted across LLM providers")
                    exc.provider_calls = prior_provider_calls
                    exc.fallback_count = fallback_count
                    exc.fallback_reason = fallback_reason
                    raise exc

                step_timeout = budget.remaining_for_step(self.provider_timeout, step_name=model_config["provider"])
                headers = {"Content-Type": "application/json"}
                resolved_temperature = (
                    temperature if temperature is not None else model_config["temperature"]
                )
                resolved_max_tokens = (
                    max_tokens if max_tokens is not None else model_config["max_tokens"]
                )
                request_url = model_config["base_url"]

                if model_config["api"] == "vercel_ai":
                    headers["X-Chat-Service-Token"] = settings.chat_service_token or ""
                    payload = _bridge_payload(model_config, messages, max_tokens=resolved_max_tokens,
                                              timeout_ms=int(step_timeout * 1000))
                elif model_config["api"] == "gemini":
                    request_url = f"{request_url}?key={model_config['api_key']}"
                    payload = self._build_gemini_payload(messages, resolved_temperature, resolved_max_tokens)
                else:
                    headers["Authorization"] = f"Bearer {model_config['api_key']}"
                    if model_config["provider"] == "openrouter":
                        if settings.openrouter_site_url:
                            headers["HTTP-Referer"] = settings.openrouter_site_url
                        headers["X-Title"] = "Promption Shop Demo"

                    is_gpt5 = (
                        model_config["provider"] == "openai"
                        and model_config["model"].lower().startswith("gpt-5")
                    )
                    if is_gpt5:
                        payload = {
                            "model": model_config["model"],
                            "messages": messages,
                            "max_completion_tokens": resolved_max_tokens,
                            "reasoning_effort": "minimal",
                            "stream": False,
                        }
                    else:
                        payload = {
                            "model": model_config["model"],
                            "messages": messages,
                            "temperature": resolved_temperature,
                            "max_tokens": resolved_max_tokens,
                            "stream": False,
                        }

                t0 = time.perf_counter()
                try:
                    async with asyncio.timeout(step_timeout):
                        response = await _post_http(
                            client,
                            request_url,
                            headers=headers,
                            json=payload,
                            timeout=step_timeout,
                        )
                except asyncio.CancelledError:
                    logger.info("LLM generation cancelled")
                    raise
                except (httpx.TimeoutException, TimeoutError) as exc:
                    prior_provider_calls += 1
                    last_exception = LLMTimeoutError(
                        f"{model_config['provider'].upper()} timed out after {step_timeout:.1f}s",
                        model=model_config["label"], provider=model_config["provider"]
                    )
                    logger.warning("LLM timeout provider=%s attempt=%d timeout=%.1fs",
                                   model_config["provider"], attempt + 1, step_timeout)
                except (httpx.ConnectError, httpx.NetworkError) as exc:
                    prior_provider_calls += 1
                    last_exception = LLMConnectivityError(
                        f"Connection error to {model_config['provider']}",
                        model=model_config["label"], provider=model_config["provider"]
                    )
                    logger.warning("LLM network error provider=%s attempt=%d",
                                   model_config["provider"], attempt + 1)
                except Exception as exc:
                    prior_provider_calls += 1
                    last_exception = exc
                    logger.warning("LLM unexpected error provider=%s attempt=%d error=%s",
                                   model_config["provider"], attempt + 1, exc.__class__.__name__)
                    break
                else:
                    if model_config["api"] == "vercel_ai":
                        _raise_bridge_guard(response)

                    is_ok = getattr(response, "is_success", None)
                    if is_ok is True or (is_ok is None and getattr(response, "status_code", 200) < 400):
                        try:
                            data = response.json()
                            content = self._extract_text(model_config["provider"], data)
                        except (IndexError, KeyError, TypeError, ValueError) as exc:
                            content = ""
                            last_exception = LLMInvalidResponseError(
                                "LLM returned an unparseable payload",
                                model=model_config["label"], provider=model_config["provider"]
                            )

                        if content:
                            budget.check_expired("generate_accept_result")
                            latency = (time.perf_counter() - t0) * 1000
                            p_tokens = None
                            c_tokens = None
                            t_tokens = None
                            r_tokens = None
                            provider_calls = None
                            if isinstance(data, dict):
                                finish_r = data.get("finish_reason") or data.get("finishReason")
                                truncated = (finish_r == "length")
                                usage = data.get("usage")
                                if isinstance(usage, dict):
                                    p_tokens = _extract_token_count(usage, "prompt_tokens", "input_tokens")
                                    c_tokens = _extract_token_count(usage, "completion_tokens", "output_tokens")
                                    t_tokens = _extract_token_count(usage, "total_tokens")
                                    r_tokens = _extract_token_count(usage, "reasoning_tokens")
                                current_calls = data.get("provider_calls", 1)
                                if current_calls is not None:
                                    try:
                                        provider_calls = prior_provider_calls + int(current_calls)
                                    except (ValueError, TypeError):
                                        provider_calls = prior_provider_calls + 1
                                else:
                                    provider_calls = None
                            else:
                                provider_calls = prior_provider_calls + 1
                            return LLMResponse(
                                text=content,
                                model=model_config["label"],
                                latency_ms=latency,
                                ok=True,
                                requested_model=requested_model,
                                fallback_count=fallback_count,
                                fallback_reason=fallback_reason,
                                truncated=truncated,
                                prompt_tokens=p_tokens,
                                completion_tokens=c_tokens,
                                total_tokens=t_tokens,
                                reasoning_tokens=r_tokens,
                                provider_calls=provider_calls,
                            )
                        call_cnt = 1
                        if isinstance(data, dict) and "provider_calls" in data:
                            try:
                                call_cnt = int(data["provider_calls"])
                            except (ValueError, TypeError):
                                pass
                        prior_provider_calls += call_cnt
                        last_exception = LLMInvalidResponseError(
                            "LLM returned empty or whitespace content",
                            model=model_config["label"], provider=model_config["provider"]
                        )
                    else:
                        call_cnt = 1
                        try:
                            err_data = response.json()
                            if isinstance(err_data, dict) and "provider_calls" in err_data:
                                call_cnt = int(err_data["provider_calls"])
                        except Exception:
                            pass
                        prior_provider_calls += call_cnt
                        status = getattr(response, "status_code", 500)
                        resp_headers = getattr(response, "headers", {})
                        if status in (401, 403):
                            last_exception = LLMConfigurationError(
                                f"Provider rejected authentication (HTTP {status})",
                                model=model_config["label"], provider=model_config["provider"],
                                status_code=status
                            )
                            # 401/403 should never be retried
                            break
                        elif status == 429:
                            retry_hdr = resp_headers.get("Retry-After") if hasattr(resp_headers, "get") else None
                            retry_after = parse_retry_after(retry_hdr)
                            last_exception = LLMQuotaError(
                                f"Quota or rate limit exceeded for {model_config['provider']}",
                                model=model_config["label"], provider=model_config["provider"],
                                retry_after=retry_after
                            )
                            if retry_after is not None and retry_after > budget.remaining:
                                # Retry-After exceeds remaining budget; stop immediately
                                raise last_exception
                        elif status >= 500:
                            last_exception = LLMProviderUnavailableError(
                                f"Provider unavailable (HTTP {status})",
                                model=model_config["label"], provider=model_config["provider"],
                                status_code=status
                            )
                        else:
                            last_exception = LLMError(
                                f"Provider HTTP {status}",
                                model=model_config["label"], provider=model_config["provider"],
                                status_code=status
                            )
                            if status not in _RETRYABLE_STATUS_CODES:
                                break

                if _attempt_metrics.get() is not None:
                    _attempt_metrics.get().fail_last()

                # Retry delay calculation with exponential backoff & jitter
                if attempt + 1 < self.max_attempts and not budget.is_expired:
                    retry_after = getattr(last_exception, "retry_after", None)
                    delay = _calculate_backoff(attempt, self.retry_backoff, retry_after)
                    if delay > budget.remaining:
                        break
                    if delay > 0:
                        await asyncio.sleep(delay)

            if budget.is_expired:
                break

        if last_exception is not None:
            setattr(last_exception, "provider_calls", prior_provider_calls)
            setattr(last_exception, "fallback_count", fallback_count)
            setattr(last_exception, "fallback_reason", fallback_reason)
            if isinstance(last_exception, (LLMError, AIGuardBlocked)):
                raise last_exception
        exc = LLMProviderUnavailableError(f"All LLM providers failed: {last_exception}")
        exc.provider_calls = prior_provider_calls
        exc.fallback_count = fallback_count
        exc.fallback_reason = fallback_reason
        raise exc

    @_track_attempts
    async def generate_tool_turn(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        model_id: str | None = None,
        force_tool: str | None = None,
        deadline: Optional[RequestDeadline] = None,
    ) -> Dict[str, Any]:
        """Return a text turn or structured tool requests, respecting monotonic request budget."""
        candidates = [m for m in self.models if model_id is None or m["id"] == model_id]
        if not candidates:
            raise LLMConfigurationError("No LLM providers configured")

        budget = deadline or RequestDeadline(self.total_timeout)
        budget.check_expired("generate_tool_turn")
        last_exception: Optional[Exception] = None
        client = _resolve_client(self.client)
        requested_model = candidates[0]["label"] if candidates else ""
        fallback_count = 0
        fallback_reason = None
        prior_provider_calls = 0

        for cand_idx, config in enumerate(candidates):
            if cand_idx > 0:
                fallback_count += 1
                fallback_reason = str(last_exception) if last_exception else "Previous candidate failed"
                logger.warning("LLM tool turn fallback: requested=%s fallback_to=%s reason=%s",
                               requested_model, config["label"], fallback_reason)
            if budget.is_expired:
                exc = LLMTimeoutError("Total time budget exhausted across LLM providers")
                exc.provider_calls = prior_provider_calls
                exc.fallback_count = fallback_count
                exc.fallback_reason = fallback_reason
                raise exc

            step_timeout = budget.remaining_for_step(self.provider_timeout, step_name=config["provider"])
            try:
                if config["api"] == "vercel_ai":
                    payload = _bridge_payload(config, messages, tools, force_tool, timeout_ms=int(step_timeout * 1000))
                    async with asyncio.timeout(step_timeout):
                        response = await _post_http(
                            client,
                            config["base_url"], json=payload,
                            headers={"X-Chat-Service-Token": settings.chat_service_token or "", "X-Request-ID": payload.get("request_id") or ""},
                            timeout=step_timeout)
                    _raise_bridge_guard(response)
                    if not response.is_success:
                        call_cnt = 1
                        try:
                            err_data = response.json()
                            if isinstance(err_data, dict) and "provider_calls" in err_data:
                                call_cnt = int(err_data["provider_calls"])
                        except Exception:
                            pass
                        prior_provider_calls += call_cnt
                        status = response.status_code
                        if status in (401, 403):
                            raise LLMConfigurationError("Bridge auth failed", model=config["label"],
                                                        provider=config["provider"], status_code=status)
                        if status == 429:
                            raise LLMQuotaError("Bridge rate limit exceeded", model=config["label"],
                                                provider=config["provider"],
                                                retry_after=parse_retry_after(response.headers.get("Retry-After")))
                        if status >= 500:
                            raise LLMProviderUnavailableError(f"Bridge unavailable (HTTP {status})",
                                                              model=config["label"], provider=config["provider"],
                                                              status_code=status)
                        response.raise_for_status()

                    data = response.json()
                    text = data.get("text", "")
                    calls = data.get("calls", [])
                    if not str(text).strip() and not calls:
                        raise LLMInvalidResponseError("Empty response and no tool calls from bridge",
                                                      model=config["label"], provider=config["provider"])
                    budget.check_expired("generate_tool_turn_accept_result")
                    truncated = False
                    p_tokens = None
                    c_tokens = None
                    t_tokens = None
                    r_tokens = None
                    finish_r = data.get("finish_reason") or data.get("finishReason")
                    truncated = (finish_r == "length")
                    usage = data.get("usage")
                    if isinstance(usage, dict):
                        p_tokens = _extract_token_count(usage, "prompt_tokens", "input_tokens")
                        c_tokens = _extract_token_count(usage, "completion_tokens", "output_tokens")
                        t_tokens = _extract_token_count(usage, "total_tokens")
                        r_tokens = _extract_token_count(usage, "reasoning_tokens")
                    current_calls = data.get("provider_calls", 1) if isinstance(data, dict) else 1
                    total_provider_calls = prior_provider_calls + (int(current_calls) if current_calls is not None else 1)
                    return {
                        "text": text, "calls": calls, "assistant": {},
                        "model": config["label"], "model_id": config["id"],
                        "provider": config["provider"],
                        "requested_model": requested_model,
                        "fallback_count": fallback_count,
                        "fallback_reason": fallback_reason,
                        "truncated": truncated,
                        "prompt_tokens": p_tokens,
                        "completion_tokens": c_tokens,
                        "total_tokens": t_tokens,
                        "reasoning_tokens": r_tokens,
                        "provider_calls": total_provider_calls,
                    }

                if config["api"] == "gemini":
                    payload = self._build_gemini_payload(messages, config["temperature"], config["max_tokens"])
                    payload["tools"] = [{"functionDeclarations": [
                        {"name": item["function"]["name"],
                         "description": item["function"]["description"],
                         "parameters": {key: value for key, value in item["function"]["parameters"].items()
                                        if key != "additionalProperties"}}
                        for item in tools]}] if tools else []
                    payload["toolConfig"] = {"functionCallingConfig": {
                        "mode": "ANY" if force_tool else "AUTO",
                        **({"allowedFunctionNames": [force_tool]} if force_tool else {}),
                    }}
                    url = f"{config['base_url']}?key={config['api_key']}"
                    headers = {"Content-Type": "application/json"}
                else:
                    payload = {
                        "model": config["model"], "messages": messages,
                        "stream": False, "tools": tools,
                        "tool_choice": ({"type": "function", "function": {"name": force_tool}}
                                        if force_tool else "auto"),
                        "parallel_tool_calls": False
                    }
                    if config["provider"] == "openai" and config["model"].lower().startswith("gpt-5"):
                        payload.update(max_completion_tokens=config["max_tokens"], reasoning_effort="minimal")
                    else:
                        payload.update(max_tokens=config["max_tokens"], temperature=config["temperature"])
                    url = config["base_url"]
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {config['api_key']}"
                    }
                    if config["provider"] == "openrouter":
                        if settings.openrouter_site_url:
                            headers["HTTP-Referer"] = settings.openrouter_site_url
                        headers["X-Title"] = "Promption Shop Demo"

                async with asyncio.timeout(step_timeout):
                    response = await _post_http(client, url, headers=headers, json=payload, timeout=step_timeout)
                is_ok = getattr(response, "is_success", None)
                if not (is_ok is True or (is_ok is None and getattr(response, "status_code", 200) < 400)):
                    call_cnt = 1
                    try:
                        err_data = response.json()
                        if isinstance(err_data, dict) and "provider_calls" in err_data:
                            call_cnt = int(err_data["provider_calls"])
                    except Exception:
                        pass
                    prior_provider_calls += call_cnt
                    status = getattr(response, "status_code", 500)
                    if status in (401, 403):
                        raise LLMConfigurationError(f"Auth failed (HTTP {status})",
                                                    model=config["label"], provider=config["provider"],
                                                    status_code=status)
                    if status == 429:
                        resp_headers = getattr(response, "headers", {})
                        retry_hdr = resp_headers.get("Retry-After") if hasattr(resp_headers, "get") else None
                        raise LLMQuotaError(f"Rate limit exceeded",
                                            model=config["label"], provider=config["provider"],
                                            retry_after=parse_retry_after(retry_hdr))
                    if status >= 500:
                        raise LLMProviderUnavailableError(f"Provider unavailable (HTTP {status})",
                                                          model=config["label"], provider=config["provider"],
                                                          status_code=status)
                    if hasattr(response, "raise_for_status"):
                        response.raise_for_status()

                data = response.json()
                if config["api"] == "gemini":
                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    calls = [{"id": part["functionCall"].get("id"), "name": part["functionCall"]["name"],
                              "arguments": part["functionCall"].get("args", {})}
                             for i, part in enumerate(parts) if "functionCall" in part]
                    content = "".join(part.get("text", "") for part in parts).strip()
                    assistant = {"role": "assistant", "gemini_parts": parts}
                else:
                    assistant = data["choices"][0]["message"]
                    calls = [{"id": call["id"], "name": call["function"]["name"],
                              "arguments": call["function"].get("arguments", "{}")}
                             for call in assistant.get("tool_calls", [])]
                    content = assistant.get("content") or ""

                if not str(content).strip() and not calls:
                    raise LLMInvalidResponseError("Empty LLM response without tool calls",
                                                  model=config["label"], provider=config["provider"])

                budget.check_expired("generate_tool_turn_accept_result")
                truncated = False
                p_tokens = None
                c_tokens = None
                t_tokens = None
                r_tokens = None
                if isinstance(data, dict):
                    usage = data.get("usage")
                    if isinstance(usage, dict):
                        p_tokens = _extract_token_count(usage, "prompt_tokens", "input_tokens")
                        c_tokens = _extract_token_count(usage, "completion_tokens", "output_tokens")
                        t_tokens = _extract_token_count(usage, "total_tokens")
                        r_tokens = _extract_token_count(usage, "reasoning_tokens")
                current_calls = data.get("provider_calls", 1) if isinstance(data, dict) else 1
                total_provider_calls = prior_provider_calls + (int(current_calls) if current_calls is not None else 1)
                return {
                    "text": content, "calls": calls, "assistant": assistant,
                    "model": config["label"], "model_id": config["id"],
                    "provider": config["provider"],
                    "requested_model": requested_model,
                    "fallback_count": fallback_count,
                    "fallback_reason": fallback_reason,
                    "truncated": truncated,
                    "prompt_tokens": p_tokens,
                    "completion_tokens": c_tokens,
                    "total_tokens": t_tokens,
                    "reasoning_tokens": r_tokens,
                    "provider_calls": total_provider_calls,
                }

            except (AIGuardBlocked, asyncio.CancelledError):
                raise
            except (httpx.TimeoutException, TimeoutError) as exc:
                prior_provider_calls += 1
                last_exception = LLMTimeoutError(f"Timeout during tool turn after {step_timeout:.1f}s",
                                                 model=config["label"], provider=config["provider"])
                logger.warning("Tool turn timeout provider=%s", config["provider"])
            except (httpx.ConnectError, httpx.NetworkError) as exc:
                prior_provider_calls += 1
                last_exception = LLMConnectivityError(f"Connection failure to {config['provider']}",
                                                      model=config["label"], provider=config["provider"])
                logger.warning("Tool turn connection failure provider=%s", config["provider"])
            except Exception as exc:
                if _attempt_metrics.get() is not None:
                    _attempt_metrics.get().fail_last()
                if not isinstance(exc, LLMError):
                    prior_provider_calls += 1
                last_exception = exc
                logger.warning("Tool turn failed provider=%s error=%s", config["provider"], exc.__class__.__name__)
                if model_id or budget.is_expired:
                    break

        if last_exception is not None:
            setattr(last_exception, "provider_calls", prior_provider_calls)
            setattr(last_exception, "fallback_count", fallback_count)
            setattr(last_exception, "fallback_reason", fallback_reason)
            if isinstance(last_exception, (LLMError, AIGuardBlocked)):
                raise last_exception
        exc = LLMProviderUnavailableError(f"All LLM providers failed: {last_exception}")
        exc.provider_calls = prior_provider_calls
        exc.fallback_count = fallback_count
        exc.fallback_reason = fallback_reason
        raise exc


# Singleton instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get singleton LLMClient instance"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
