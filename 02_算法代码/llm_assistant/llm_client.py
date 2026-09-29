# -*- coding: utf-8 -*-
"""Unified LLM client facade for industrial agent use.

v18.7.12 \u2014 single entrypoint that picks backend (llama-server / llama-cpp / rules).

Usage:
    client = LLMClient(backend="llama-server", server_url="http://localhost:8081/v1")
    resp = client.chat(messages=[{"role": "user", "content": "..."}])
"""
from __future__ import annotations
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


@dataclass
class ChatResponse:
    text: str
    reasoning: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    elapsed_s: float = 0.0
    backend: str = "unknown"
    error: Optional[str] = None


class LLMClient:
    """Single facade for 3 backends.

    backends:
      - "llama-server": OpenAI-compatible HTTP (production)
      - "llama-cpp-python": in-process (when running tests/dev)
      - "rules": template-only (always available)
    """

    def __init__(
        self,
        backend: str = "auto",
        server_url: str = "http://localhost:8081/v1",
        model_name: str = "Qwen3.5-4B-Claude-Opus",
        timeout_s: int = 180,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        model_path: Optional[str] = None,
    ):
        self.server_url = server_url.rstrip("/")
        self.model_name = model_name
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model_path = model_path
        self._model_obj = None
        self._llamacpp_backend = False

        if backend == "auto":
            backend = self._detect_backend()
        self.backend = backend

        if self.backend == "llama-cpp-python":
            self._init_llamacpp()

    def _detect_backend(self) -> str:
        """Pick the best backend given current environment."""
        # 1. try llama-server HTTP
        try:
            r = requests.get(self.server_url + "/models", timeout=3)
            if r.ok and r.json().get("data"):
                return "llama-server"
        except Exception:
            pass
        # 2. try in-process llama-cpp
        try:
            import llama_cpp  # noqa: F401
            if self.model_path and Path(self.model_path).exists():
                return "llama-cpp-python"
        except ImportError:
            pass
        # 3. fall back to rules
        return "rules"

    def _init_llamacpp(self) -> None:
        """Load model in-process via llama-cpp-python."""
        try:
            from llama_cpp import Llama
            if not self.model_path or not Path(self.model_path).exists():
                # try default location
                default = Path(r"E:\llm_models\Qwen3.5-4B-Claude-Opus")
                if default.is_dir():
                    ggufs = sorted(default.glob("*.gguf"), key=lambda p: p.stat().st_size, reverse=True)
                    if ggufs:
                        self.model_path = str(ggufs[0])
            if not self.model_path or not Path(self.model_path).exists():
                logger.warning("llama-cpp: no model_path, switching to rules")
                self.backend = "rules"
                return
            self._model_obj = Llama(
                model_path=self.model_path,
                n_ctx=8192,
                n_threads=os.cpu_count() or 4,
                n_gpu_layers=0,
                verbose=False,
            )
            self._llamacpp_backend = True
            logger.info(f"llama-cpp model loaded: {self.model_path}")
        except Exception as e:
            logger.warning(f"llama-cpp init failed: {e}, using rules")
            self.backend = "rules"

    @property
    def is_available(self) -> bool:
        if self.backend == "llama-server":
            try:
                r = requests.get(self.server_url + "/models", timeout=3)
                return r.ok
            except Exception:
                return False
        if self.backend == "llama-cpp-python":
            return self._llamacpp_backend and self._model_obj is not None
        return False  # rules-only

    def health(self) -> Dict[str, Any]:
        if self.backend == "llama-server":
            try:
                r = requests.get(self.server_url + "/models", timeout=3)
                return {
                    "ok": r.ok,
                    "backend": self.backend,
                    "server": self.server_url,
                    "models": [m.get("id") for m in r.json().get("data", [])][:5],
                }
            except Exception as e:
                return {"ok": False, "backend": self.backend, "error": str(e)}
        if self.backend == "llama-cpp-python":
            return {
                "ok": self.is_available,
                "backend": self.backend,
                "model_path": self.model_path,
            }
        return {"ok": False, "backend": self.backend, "note": "rules-only"}

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """Unified chat. Delegates to detected backend.

        Returns ChatResponse with text + optional tool_calls.
        """
        t0 = time.time()
        temp = temperature if temperature is not None else self.temperature
        tok = max_tokens if max_tokens is not None else self.max_tokens

        if self.backend == "llama-server":
            return self._chat_llama_server(messages, tools, temp, tok, t0)
        if self.backend == "llama-cpp-python":
            return self._chat_llamacpp(messages, tools, temp, tok, t0)
        return ChatResponse(
            text="",
            error="no LLM backend available (rules-only)",
            backend="rules",
            elapsed_s=time.time() - t0,
        )

    def _chat_llama_server(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
        max_tokens: int,
        t0: float,
    ) -> ChatResponse:
        body = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = tools
        try:
            r = requests.post(
                self.server_url + "/chat/completions",
                json=body,
                timeout=self.timeout_s,
            )
            r.raise_for_status()
            j = r.json()
            choice = (j.get("choices") or [{}])[0]
            msg = choice.get("message", {})
            text = msg.get("content", "")
            if not text and msg.get("reasoning_content"):
                text = msg.get("reasoning_content", "")
            tool_calls = msg.get("tool_calls") or []
            return ChatResponse(
                text=text,
                reasoning=msg.get("reasoning_content"),
                tool_calls=tool_calls,
                tokens_in=j.get("usage", {}).get("prompt_tokens", 0),
                tokens_out=j.get("usage", {}).get("completion_tokens", 0),
                elapsed_s=time.time() - t0,
                backend="llama-server",
            )
        except Exception as e:
            return ChatResponse(
                text="",
                error=f"llama-server error: {e}",
                backend="llama-server",
                elapsed_s=time.time() - t0,
            )

    def _chat_llamacpp(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
        max_tokens: int,
        t0: float,
    ) -> ChatResponse:
        if not self._llamacpp_backend or self._model_obj is None:
            return ChatResponse(
                text="",
                error="llama-cpp model not loaded",
                backend="llama-cpp-python",
                elapsed_s=time.time() - t0,
            )
        try:
            text_prompt = self._format_chat_prompt(messages, tools)
            out = self._model_obj(
                text_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.9,
                stop=["</s>", "\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b", "\n\n\n"],
            )
            text = out["choices"][0]["text"].strip()
            return ChatResponse(
                text=text,
                tokens_in=0,
                tokens_out=0,
                elapsed_s=time.time() - t0,
                backend="llama-cpp-python",
            )
        except Exception as e:
            return ChatResponse(
                text="",
                error=f"llama-cpp error: {e}",
                backend="llama-cpp-python",
                elapsed_s=time.time() - t0,
            )

    @staticmethod
    def _format_chat_prompt(messages: List[Dict[str, str]], tools: Optional[List]) -> str:
        """Format messages for Qwen3.5 chat template (simplified)."""
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                parts.append(f"<|im_start|>system\n{content}<|im_end|>")
            elif role == "user":
                parts.append(f"<|im_start|>user\n{content}<|im_end|>")
            elif role == "assistant":
                parts.append(f"<|im_start|>assistant\n{content}<|im_end|>")
            elif role == "tool":
                parts.append(f"<|im_start|>tool\n{content}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────
# v18.7.12 — Module-level convenience wrappers used by API endpoints
# ──────────────────────────────────────────────────────────────────────

def detect_backend(prefer: str = "auto") -> str:
    """Probe for available backend; return one of: llama-server / llama-cpp / rules."""
    try:
        client = LLMClient(backend=prefer)
        return client.health().get("backend", "unknown")
    except Exception as e:
        logger.warning("detect_backend failed: %s", e)
        return "rules"


def generate(
    messages: List[Dict[str, str]],
    max_tokens: int = 1024,
    temperature: float = 0.3,
    backend: str = "auto",
) -> tuple:
    """Module-level convenience: returns (raw_text, meta_dict).

    meta_dict has: backend, tokens_in, tokens_out, elapsed_s, error
    """
    client = LLMClient(backend=backend, max_tokens=max_tokens, temperature=temperature)
    try:
        resp = client.chat(messages=messages)
        return resp.text, {
            "backend": resp.backend,
            "tokens_in": resp.tokens_in,
            "tokens_out": resp.tokens_out,
            "elapsed_s": round(resp.elapsed_s, 3),
            "error": resp.error,
        }
    except Exception as e:
        logger.exception("generate failed")
        return "", {"backend": "error", "error": str(e), "elapsed_s": 0.0}
