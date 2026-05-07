"""LLM Core -- Unified LLM session management with streaming support.

Supports OpenAI-compatible APIs (OpenAI, DeepSeek, Claude-compatible).
Handles token counting, retry logic, and SSE streaming.

Provider auth styles:
  - openai/deepseek: Bearer token in Authorization header
  - claude: x-api-key header + anthropic-version header
"""
from __future__ import annotations
import json, time, re, logging, os
from dataclasses import dataclass, field
from typing import Optional, Generator, Callable

log = logging.getLogger("hc_agent.llm")


@dataclass
class LLMMessage:
    role: str           # "system" | "user" | "assistant" | "tool"
    content: str
    tool_call_id: str = ""
    tool_calls: list = field(default_factory=list)


@dataclass
class LLMResponse:
    content: str
    tool_calls: list = field(default_factory=list)  # [{id, name, arguments}]
    finish_reason: str = ""
    usage: dict = field(default_factory=dict)       # {prompt, completion, total}


class LLMCore:
    """Unified LLM communication layer."""
    
    def __init__(self, config):
        self.config = config
        self.llm_cfg = config.llm
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                import httpx
                self._client = httpx.Client(
                    base_url=self._resolve_base_url(),
                    headers=self._build_headers(),
                    timeout=120.0,
                )
            except ImportError:
                raise ImportError("httpx required: pip install httpx")
        return self._client
    
    def _resolve_base_url(self) -> str:
        url = self.llm_cfg.base_url
        if not url:
            provider = self.llm_cfg.provider.lower()
            urls = {
                "openai": "https://api.openai.com/v1",
                "deepseek": "https://api.deepseek.com/v1",
                "claude": "https://api.anthropic.com",
            }
            url = urls.get(provider, "https://api.openai.com/v1")
        return url.rstrip("/")
    
    def _build_headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        provider = self.llm_cfg.provider.lower()
        if provider == "claude":
            h["x-api-key"] = self.llm_cfg.api_key
            h["anthropic-version"] = "2023-06-01"
        else:
            h["Authorization"] = f"Bearer {self.llm_cfg.api_key}"
        return h
    
    def chat(self, messages: list[LLMMessage], tools: list[dict] = None,
             stream: bool = False, on_token: Callable[[str], None] = None) -> LLMResponse:
        """Send chat completion request.
        
        Args:
            on_token: Optional callback called with each text chunk during streaming.
                      If provided, automatically enables streaming mode.
        """
        provider = self.llm_cfg.provider.lower()
        use_stream = stream or (on_token is not None)
        if provider == "claude":
            return self._chat_claude(messages, tools, use_stream, on_token)
        return self._chat_openai(messages, tools, use_stream, on_token)
    
    def _chat_openai(self, messages: list[LLMMessage],
                     tools: list[dict] = None, stream: bool = False,
                     on_token: callable = None) -> LLMResponse:
        """OpenAI-compatible chat completion. Supports SSE streaming via on_token callback."""
        import httpx
        client = self._get_client()
        payload = {
            "model": self.llm_cfg.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": self.llm_cfg.max_tokens,
            "temperature": self.llm_cfg.temperature,
        }
        # Build messages with proper tool_calls / tool_call_id handling
        system_parts = []
        chat_msgs = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
            else:
                entry = {"role": m.role, "content": m.content}
                if m.tool_calls:
                    entry["tool_calls"] = m.tool_calls
                if m.tool_call_id:
                    entry["tool_call_id"] = m.tool_call_id
                chat_msgs.append(entry)
        
        # Merge all system parts into one (MiniMax only supports 1 system msg)
        if system_parts:
            merged_system = {"role": "system", "content": "\n\n".join(system_parts)}
            payload["messages"] = [merged_system] + chat_msgs
        else:
            payload["messages"] = chat_msgs
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        # DEBUG: dump payload for troubleshooting
        try:
            import tempfile, json as _j
            _dbg = os.path.join(os.environ.get("TEMP", "/tmp"), "hc_llm_debug.json")
            with open(_dbg, "w", encoding="utf-8") as _f:
                _j.dump({"url": self.llm_cfg.base_url, "model": self.llm_cfg.model,
                         "payload": payload}, _f, ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass

        url = self._resolve_base_url() + "/chat/completions"
        headers = self._build_headers()

        if stream:
            return self._stream_openai(url, headers, payload, on_token)
        
        # Non-streaming path
        for attempt in range(3):
            try:
                resp = httpx.post(url, json=payload, headers=headers, timeout=120.0)
                resp.raise_for_status()
                data = resp.json()
                return self._parse_openai_response(data)
            except Exception as e:
                log.warning(f"LLM attempt {attempt+1} failed: {e}")
                try:
                    log.warning(f"Raw response: {resp.text[:500]}")
                except Exception:
                    pass
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    raise
    
    def _stream_openai(self, url: str, headers: dict, payload: dict,
                       on_token: callable) -> LLMResponse:
        """SSE streaming for OpenAI-compatible API. Returns final LLMResponse."""
        import httpx
        payload = {**payload, "stream": True}
        
        accumulated_content = ""
        tool_calls_acc = {}  # index -> {id, name, arguments}
        finish_reason = ""
        usage = {}
        
        for attempt in range(3):
            try:
                with httpx.Client(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
                    with client.stream("POST", url, json=payload, headers=headers) as resp:
                        resp.raise_for_status()
                        for line in resp.iter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            
                            choice = chunk.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            
                            # Accumulate text content
                            content_delta = delta.get("content", "")
                            if content_delta:
                                accumulated_content += content_delta
                                if on_token:
                                    on_token(content_delta)
                            
                            # Accumulate tool calls (streamed incrementally)
                            for tc_delta in delta.get("tool_calls", []):
                                idx = tc_delta.get("index", 0)
                                if idx not in tool_calls_acc:
                                    tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                                tc = tool_calls_acc[idx]
                                if tc_delta.get("id"):
                                    tc["id"] = tc_delta["id"]
                                fn = tc_delta.get("function", {})
                                if fn.get("name"):
                                    tc["name"] = fn["name"]
                                if fn.get("arguments"):
                                    tc["arguments"] += fn["arguments"]
                            
                            # Check finish reason
                            fr = choice.get("finish_reason")
                            if fr:
                                finish_reason = fr
                            
                            # Usage may come in the last chunk
                            if chunk.get("usage"):
                                usage = chunk["usage"]
                
                # Build final response
                tool_calls_list = [tool_calls_acc[i] for i in sorted(tool_calls_acc.keys())]
                return LLMResponse(
                    content=accumulated_content,
                    tool_calls=tool_calls_list,
                    finish_reason=finish_reason,
                    usage=usage,
                )
            except Exception as e:
                log.warning(f"Stream attempt {attempt+1} failed: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    raise
    
    def _parse_openai_response(self, data: dict) -> LLMResponse:
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        tool_calls = []
        for tc in (msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            tool_calls.append({
                "id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments", "{}"),
            })
        return LLMResponse(
            content=msg.get("content", "") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", ""),
            usage=data.get("usage", {}),
        )
    
    def _chat_claude(self, messages: list[LLMMessage],
                     tools: list[dict] = None, stream: bool = False) -> LLMResponse:
        """Anthropic Claude API."""
        client = self._get_client()
        # Separate system from conversation
        system_text = ""
        conv_messages = []
        for m in messages:
            if m.role == "system":
                system_text += m.content + "\n"
            else:
                conv_messages.append({"role": m.role, "content": m.content})
        
        payload = {
            "model": self.llm_cfg.model,
            "max_tokens": self.llm_cfg.max_tokens,
            "messages": conv_messages,
        }
        if system_text.strip():
            payload["system"] = system_text.strip()
        if tools:
            payload["tools"] = [self._convert_tool_for_claude(t) for t in tools]
        
        for attempt in range(3):
            try:
                resp = client.post("/v1/messages", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return self._parse_claude_response(data)
            except Exception as e:
                log.warning(f"Claude attempt {attempt+1} failed: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    raise
    
    def _convert_tool_for_claude(self, tool: dict) -> dict:
        fn = tool.get("function", {})
        return {
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {}),
        }
    
    def _parse_claude_response(self, data: dict) -> LLMResponse:
        content = ""
        tool_calls = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {})),
                })
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=data.get("stop_reason", ""),
            usage=data.get("usage", {}),
        )



class FallbackLLMCore:
    """Multi-model fallback wrapper with spring-back to primary.

    Similar to GenericAgent's MixinSession: tries primary LLMCore first,
    on failure rotates to next backup model. After a full round of all
    models, waits with exponential backoff before retrying.

    Primary model cools down for `spring_back` seconds, then auto-recovers.

    Usage:
        fallback = FallbackLLMCore(primary, backups, cfg.fallback)
        resp = fallback.ask("hello", system="You are helpful.")
    """

    def __init__(self, primary: LLMCore, backups: list, cfg=None):
        self._primary = primary
        self._backups = backups  # list of LLMCore
        self._all = [primary] + backups
        self._retries = getattr(cfg, "max_retries", 3) if cfg else 3
        self._base_delay = getattr(cfg, "base_delay", 1.5) if cfg else 1.5
        self._spring_sec = getattr(cfg, "spring_back", 300) if cfg else 300
        self._idx = 0  # current active index
        self._fail_ts = 0.0  # timestamp when primary last failed
        import time
        self._time = time

    @classmethod
    def from_config(cls, config):
        """Convenience: build from HCConfig with fallback config.
        
        Usage:
            fb = FallbackLLMCore.from_config(get_config())
            resp = fb.ask("hello")
        """
        from config import LlmConfig
        primary = LLMCore(config)
        backups = []
        fb_cfg = getattr(config, "fallback", None)
        if fb_cfg and fb_cfg.enabled and fb_cfg.models:
            for m in fb_cfg.models:
                sub_cfg = type(config)()  # shallow copy-like
                sub_cfg.llm = LlmConfig(
                    provider=m.provider, model=m.model,
                    api_key=m.api_key, base_url=m.base_url,
                )
                backups.append(LLMCore(sub_cfg))
        return cls(primary, backups, fb_cfg)

    def is_enabled(self) -> bool:
        """Check if fallback has backup models configured."""
        return len(self._backups) > 0

    def _model_name(self, idx):
        core = self._all[idx]
        cfg = core.llm_cfg
        return f"{cfg.provider}/{cfg.model}"

    def _try_spring_back(self):
        """If primary cooled down, spring back to it."""
        if self._idx == 0:
            return
        if self._fail_ts and (self._time.time() - self._fail_ts > self._spring_sec):
            log.info(f"[Fallback] Primary cooled down, springing back to {self._model_name(0)}")
            self._idx = 0
            self._fail_ts = 0.0

    def ask(self, prompt: str, system: str = None, temperature: float = None,
            max_tokens: int = None, tools=None, json_mode: bool = False) -> object:
        """Ask with automatic fallback on failure."""
        import time

        self._try_spring_back()

        n = len(self._all)
        last_err = None

        for rnd in range(self._retries + 1):
            for step in range(n):
                idx = (self._idx + step) % n
                core = self._all[idx]
                name = self._model_name(idx)
                try:
                    log.info(f"[Fallback] Trying {name} (round {rnd}, step {step})")
                    resp = core.ask(prompt, system=system, temperature=temperature,
                                    max_tokens=max_tokens, tools=tools, json_mode=json_mode)
                    # Success: if we moved away from primary, note it
                    if idx != 0 and self._idx == 0:
                        self._fail_ts = time.time()
                        log.info(f"[Fallback] Primary failed, switched to {name}")
                    self._idx = idx
                    return resp
                except Exception as e:
                    last_err = e
                    log.warning(f"[Fallback] {name} failed: {e}")
                    if idx == 0 and self._fail_ts == 0:
                        self._fail_ts = time.time()
                    continue  # try next model in this round

            # All models failed in this round
            if rnd < self._retries:
                delay = self._base_delay * (2 ** rnd)
                log.warning(f"[Fallback] Round {rnd} exhausted, retry in {delay:.1f}s")
                time.sleep(delay)

        raise RuntimeError(f"All {n} models failed after {self._retries} retries. Last error: {last_err}")

    def send(self, messages, tools=None, stream: bool = True, **kwargs):
        """Send messages with automatic fallback."""
        import time

        self._try_spring_back()

        n = len(self._all)
        last_err = None

        for rnd in range(self._retries + 1):
            for step in range(n):
                idx = (self._idx + step) % n
                core = self._all[idx]
                name = self._model_name(idx)
                try:
                    log.info(f"[Fallback] send via {name} (round {rnd}, step {step})")
                    resp = core.send(messages, tools=tools, stream=stream, **kwargs)
                    if idx != 0 and self._idx == 0:
                        self._fail_ts = time.time()
                    self._idx = idx
                    return resp
                except Exception as e:
                    last_err = e
                    log.warning(f"[Fallback] {name} send failed: {e}")
                    if idx == 0 and self._fail_ts == 0:
                        self._fail_ts = time.time()
                    continue

            if rnd < self._retries:
                delay = self._base_delay * (2 ** rnd)
                log.warning(f"[Fallback] send round {rnd} exhausted, retry in {delay:.1f}s")
                time.sleep(delay)

        raise RuntimeError(f"All models failed on send. Last error: {last_err}")

    # Delegate other attributes to primary
    def __getattr__(self, name):
        return getattr(self._primary, name)
