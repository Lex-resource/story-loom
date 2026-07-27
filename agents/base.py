import asyncio
from typing import Any, Optional
from config import settings

from agents.constants import (
    DEFAULT_LLM_JSON_MAX_TOKENS,
    DEFAULT_LLM_JSON_TEMPERATURE,
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_LLM_TEMPERATURE,
    JSON_FALLBACK_MAX_RETRIES,
    PAYLOAD_DEBUG_SIZE_THRESHOLD,
    PROMPT_TOKEN_WARNING_THRESHOLD,
)
from agents.broadcasting import broadcast_llm_log, broadcast_prompt_token_warning
from agents.llm_call_state import apply_api_usage, finalize_call_metrics, reset_call_metrics
from agents.llm_transport import LLMTransportOptions, OpenAICompatibleTransport
from agents.prompt_utils import (
    UNTRUSTED_CONTENT_SYSTEM_REMINDER,
    safe_format,
    sanitize_untrusted_content,
    strip_emojis,
)
from agents.llm_json import LLMJSONParsingError, parse_llm_json_response
from agents.prompt_templates import invalidate_prompt_cache, load_prompt_template
from agents.providers import resolve_active_provider, resolve_backup_provider
from agents.retry_policy import compute_retry_delay
from agents.usage import record_agent_usage, record_backup_model_flag


class AgentBase:
    def __init__(self, model: Optional[str] = None):
        self.model = model
        self.timeout = settings.LLM_TIMEOUT
        self.max_retries = settings.MAX_LLM_RETRIES
        self._transport = OpenAICompatibleTransport(
            timeout=self.timeout,
            debug_enabled=settings.DEBUG,
            log_dir=settings.LOG_DIR,
            payload_size_threshold=PAYLOAD_DEBUG_SIZE_THRESHOLD,
        )

    def _broadcast_llm_log(self, message: str, payload: dict = None, response: dict = None):
        broadcast_llm_log(self, message, payload=payload, response=response)

    async def get_prompt_template(
        self,
        name: str,
        *,
        category: str
    ) -> tuple[str, str]:
        template = await load_prompt_template(name, category=category)
        self.active_prompt_name = f"{name} ({category})"
        return template

    async def call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = DEFAULT_LLM_TEMPERATURE,
        max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
        on_chunk: Optional[Any] = None,
        response_format: Optional[dict] = None,
        _max_retries: Optional[int] = None,
    ) -> str:
        """Call the LLM with automatic retry and backup-provider failover.

        Retry budget semantics
        ----------------------
        ``effective_max_retries`` (defaults to ``self.max_retries``) is the
        number of attempts spent on *each* provider. The total attempt budget
        is ``2 * effective_max_retries``: the first ``effective_max_retries``
        attempts hit the primary provider; on exhaustion we switch to the
        backup provider (if configured) for another ``effective_max_retries``
        attempts. If no backup is available, the last seen exception is
        re-raised immediately after the primary budget is exhausted.

        ``_max_retries`` is an internal override used by ``call_llm_json`` to
        cap the fallback call's budget without mutating ``self.max_retries``
        (which would be unsafe under concurrent use of the same agent
        instance).
        """
        from services.token_count import count_tokens
        start_time = reset_call_metrics(self, system_prompt, user_prompt, count_tokens)

        effective_max_retries = _max_retries if _max_retries is not None else self.max_retries

        from services.settings_store import load_settings
        app_settings = await load_settings()
        active_provider = resolve_active_provider(app_settings, getattr(self, "model", None))
        current_base_url = active_provider.base_url
        current_api_key = active_provider.api_key
        current_model = active_provider.model
        initial_base_url = current_base_url
        using_backup = False

        if self.last_input_tokens > PROMPT_TOKEN_WARNING_THRESHOLD:
            await self._broadcast_prompt_token_warning()

        # Track the last exception so we can re-raise it if all retries are
        # exhausted without a successful return. Without this, falling through
        # the for-loop would implicitly return None and crash callers like
        # call_llm_json which do `raw.strip()` on the result.
        last_exception: Exception | None = None

        for attempt in range(effective_max_retries * 2):
            if attempt >= effective_max_retries and not using_backup:
                switched, current_base_url, current_api_key, current_model = await self._switch_to_backup_provider(
                    app_settings, current_base_url, current_api_key, current_model
                )
                if not switched:
                    # No backup provider configured (or backup also failed).
                    # Re-raise the last seen error instead of falling through
                    # to an implicit `return None`.
                    if last_exception is not None:
                        raise last_exception
                    raise RuntimeError(
                        f"LLM call to {current_model} failed after {attempt} attempts "
                        f"and no backup provider was available."
                    )
                using_backup = True

            fallback_status = "是" if using_backup else "否"
            active_prompt = getattr(self, "active_prompt_name", "Unknown")
            self._broadcast_llm_log(
                message=f"向 {current_model} 发起调用请求... [Prompt: {active_prompt}] [Fallback: {fallback_status}]",
                payload={
                    "model": current_model,
                    "prompt": system_prompt + "\n\n" + user_prompt,
                    "prompt_name": active_prompt,
                    "is_fallback": using_backup
                }
            )
            try:
                result = await self._transport.complete_chat(
                    LLMTransportOptions(
                        model=current_model,
                        base_url=current_base_url,
                        api_key=current_api_key,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format=response_format,
                        on_chunk=on_chunk,
                    )
                )
                self._apply_api_usage(result.usage, result.content, count_tokens)
                self._finalize_call(current_model, result.content, start_time, is_stream=result.is_stream)
                return result.content
            except Exception as e:
                # Remember the last error so we can re-raise it if the loop
                # falls through via the "no backup provider" branch above.
                last_exception = e
                # If we fail and it's not corrected /v1 yet:
                if current_base_url == initial_base_url and not current_base_url.endswith("/v1") and not current_base_url.endswith("/v1/"):
                    current_base_url = current_base_url.rstrip("/") + "/v1"
                    print(f"[AgentBase] API call failed: {e}. Retrying with auto-corrected base URL: {current_base_url}")
                    continue

                max_allowed = effective_max_retries * 2
                if attempt < max_allowed - 1:
                    delay = self._compute_retry_delay(e, attempt, using_backup, effective_max_retries)
                    print(f"[AgentBase] API call failed: {e}. Attempt {attempt + 1}. Retrying in {delay:.2f} seconds...")
                    await asyncio.sleep(delay)
                else:
                    raise

    # ------------------------------------------------------------------
    # call_llm 子方法（从原 288 行上帝方法抽取，消除流式/非流式重复代码）
    # ------------------------------------------------------------------

    async def _broadcast_prompt_token_warning(self) -> None:
        """Prompt token 超阈值时广播预警。"""
        await broadcast_prompt_token_warning(self, PROMPT_TOKEN_WARNING_THRESHOLD)

    async def _switch_to_backup_provider(
        self, app_settings: dict, current_base_url: str, current_api_key: str, current_model: str
    ) -> tuple[bool, str, str, str]:
        """切换到备份 provider。返回 (是否切换成功, 新base_url, 新api_key, 新model)。"""
        try:
            switched, backup = resolve_backup_provider(
                app_settings,
                current_base_url,
                current_api_key,
                current_model,
            )
            if not switched:
                return False, current_base_url, current_api_key, current_model
            current_base_url = backup.base_url
            current_api_key = backup.api_key
            current_model = backup.model
            print(f"[AgentBase] Primary model call failed. Switching to Backup Provider: {backup.provider_name} (Model: {current_model})...")
            pid = getattr(self, 'project_id', None)
            current_ch = getattr(self, 'current_chapter', 0)
            if pid and current_ch:
                await record_backup_model_flag(pid, current_ch, current_model)
            return True, current_base_url, current_api_key, current_model
        except Exception as ex:
            print(f"[AgentBase ERROR] Failed to load backup provider settings: {ex}")
            return False, current_base_url, current_api_key, current_model

    def _apply_api_usage(self, api_usage: Optional[dict], res_str: str, count_tokens) -> None:
        """应用 API 返回的 usage 数据到 self；缺失时本地估算 output_tokens。"""
        apply_api_usage(self, api_usage, res_str, count_tokens)

    def _finalize_call(self, current_model: str, res_str: str, start_time: float, *, is_stream: bool) -> None:
        """记录耗时并广播完成日志（流式/非流式共用，消除重复代码）。"""
        message, response = finalize_call_metrics(self, current_model, res_str, start_time, is_stream=is_stream)
        self._broadcast_llm_log(message=message, response=response)

    def _compute_retry_delay(
        self, e: Exception, attempt: int, using_backup: bool, max_retries: int
    ) -> float:
        """计算重试延迟（含指数退避 + 抖动 + 限流倍率）。

        ``max_retries`` is the per-provider attempt budget (``effective_max_retries``
        from ``call_llm``); the backoff cycle wraps every ``max_retries`` attempts
        so that switching to the backup provider restarts the exponential curve.
        """
        return compute_retry_delay(
            e,
            attempt,
            max_retries,
            base_retry_delay=settings.RETRY_DELAY,
        )


    async def call_llm_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = DEFAULT_LLM_JSON_TEMPERATURE,
        max_tokens: int = DEFAULT_LLM_JSON_MAX_TOKENS,
        on_chunk: Optional[Any] = None,
        response_schema: Optional[Any] = None,
    ) -> dict:
        # Two-phase call strategy:
        #   Phase 1 (JSON mode): full retry budget (2 * self.max_retries
        #     attempts — self.max_retries on primary + self.max_retries on
        #     backup). Requests ``response_format=json_object`` from the API.
        #   Phase 2 (plain-text fallback): if phase 1 raised, retry WITHOUT
        #     the JSON constraint so the model can return text we then parse
        #     manually. The fallback budget is capped via the internal
        #     ``_max_retries=1`` override (= 1 attempt on primary + 1 on
        #     backup = 2 attempts max). We pass it as a parameter instead of
        #     mutating ``self.max_retries`` so concurrent callers sharing the
        #     same agent instance are not affected.
        try:
            raw = await self.call_llm(
                system_prompt,
                user_prompt,
                temperature,
                max_tokens,
                on_chunk=on_chunk,
                response_format={"type": "json_object"}
            )
        except Exception as e:
            print(f"[AgentBase] JSON mode call failed: {e}. Retrying without JSON response_format constraint (budget=1)...")
            raw = await self.call_llm(
                system_prompt,
                user_prompt,
                temperature,
                max_tokens,
                on_chunk=on_chunk,
                _max_retries=JSON_FALLBACK_MAX_RETRIES,
            )
        return await parse_llm_json_response(raw, response_schema)

    async def record_usage(self, db, project_id: Any, chapter_index: int, agent_name: str):
        """
        Record the token usage of the last LLM call into the database.
        """
        await record_agent_usage(self, project_id, chapter_index, agent_name)
