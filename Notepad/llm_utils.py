from __future__ import annotations

import os
import sys
import threading
from typing import List, Tuple

from llama_cpp import Llama
from llama_cpp_agent import LlamaCppAgent
from llama_cpp_agent.providers import LlamaCppPythonProvider
from llama_cpp_agent.chat_history import BasicChatHistory
from llama_cpp_agent.chat_history.messages import Roles
from llama_cpp_agent.messages_formatter import MessagesFormatter, PromptMarkers

__all__ = [
    "DEFAULT_MODEL_FILENAME",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_N_CTX",
    "MODEL_DIRNAME",
    "count_tokens",
    "estimate_context_usage",
    "get_app_dir",
    "get_model_dir",
    "is_model_loaded",
    "preload_model",
    "reset_model_cache",
    "resolve_model_path",
    "respond",
]

# Gemma 4 E2B on ~3 GB RAM: keep context modest (model weights dominate).
DEFAULT_MODEL_FILENAME = "gemma-4-E2B-it-Q4_K_M.gguf"
MODEL_DIRNAME = "model"
DEFAULT_N_CTX = 4096
DEFAULT_MAX_TOKENS = 2048

# ───────────────────────── Gemma‑3 prompt markers ──────────────────────────
_gemma_3_prompt_markers = {
    Roles.system:    PromptMarkers("", "\n"),
    Roles.user:      PromptMarkers("<start_of_turn>user\n",  "<end_of_turn>\n"),
    Roles.assistant: PromptMarkers("<start_of_turn>model\n", "<end_of_turn>\n"),
    Roles.tool:      PromptMarkers("", ""),
}
_gemma_3_formatter = MessagesFormatter(
    pre_prompt="",
    prompt_markers=_gemma_3_prompt_markers,
    include_sys_prompt_in_first_user_message=True,
    default_stop_sequences=["<end_of_turn>", "<start_of_turn>"],
    strip_prompt=False,
    bos_token="<bos>",
    eos_token="<eos>",
)


_llm: Llama | None = None
_llm_model_path: str | None = None
_load_lock = threading.Lock()


def get_app_dir() -> str:
    """Directory of Owl-Bot.exe when frozen; Notepad/ when developing."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_model_dir() -> str:
    """Distribution layout: {app_dir}/model/*.gguf"""
    return os.path.join(get_app_dir(), MODEL_DIRNAME)


def resolve_model_path(model: str | None = None) -> str:
    """Resolve GGUF path: explicit path > {app_dir}/model/ > dev models/."""
    if model and os.path.isfile(model):
        return os.path.abspath(model)

    name = os.path.basename(model) if model else DEFAULT_MODEL_FILENAME
    app_dir = get_app_dir()
    notepad_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(app_dir, MODEL_DIRNAME, name),
        os.path.join(notepad_dir, "models", name),
        os.path.join(notepad_dir, MODEL_DIRNAME, name),
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path

    searched = "\n  ".join(candidates)
    raise FileNotFoundError(f"Model not found: {name}\nSearched:\n  {searched}")


def is_model_loaded(model: str | None = None) -> bool:
    """指定パスのモデルがメモリ上に読み込み済みか。"""
    path = model
    if path and not os.path.isfile(path):
        try:
            path = resolve_model_path(model)
        except FileNotFoundError:
            return False
    elif path and os.path.isfile(path):
        path = os.path.abspath(path)
    elif path is None and _llm_model_path:
        path = _llm_model_path
    if _llm is None or path is None:
        return False
    return os.path.abspath(_llm_model_path or "") == os.path.abspath(path)


def preload_model(model: str | None = None) -> str:
    """モデルをメモリへ読み込む（GUI のバックグラウンド用）。"""
    model_path = resolve_model_path(model)
    _lazy_load_model(model_path)
    return model_path


def reset_model_cache() -> None:
    """モデルパス変更時にキャッシュを破棄する。"""
    global _llm, _llm_model_path
    with _load_lock:
        _llm = None
        _llm_model_path = None


def _lazy_load_model(model_path: str) -> Llama:
    """Load (or return cached) GGUF model from *model_path*."""
    global _llm, _llm_model_path

    model_path = os.path.abspath(model_path)
    with _load_lock:
        if (
            _llm
            and _llm_model_path
            and os.path.abspath(_llm_model_path) == model_path
        ):
            return _llm

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found: {model_path}")

        _llm = Llama(
            model_path=model_path,
            flash_attn=False,
            n_gpu_layers=0,
            n_batch=8,
            n_ubatch=8,
            n_ctx=DEFAULT_N_CTX,
            n_threads=8,
            n_threads_batch=8,
            verbose=False,
        )
        _llm_model_path = model_path
        return _llm


def count_tokens(text: str, model: str | None = None) -> int:
    """テキストのトークン数を数える。未読み込み時は文字数から概算。"""
    if not text:
        return 0
    try:
        if is_model_loaded(model):
            with _load_lock:
                if _llm is not None:
                    return len(_llm.tokenize(text.encode("utf-8"), add_bos=False))
    except Exception:
        pass
    # 日本語混在をざっくり見積もる（1 トークン ≈ 2 文字）
    return max(1, len(text) // 2)


def _build_prompt_text(
    system_message: str,
    history: List[Tuple[str, str]],
    user_message: str,
) -> str:
    """Gemma ターン形式に近い文字列を組み立て、使用量見積もりに使う。"""
    parts: list[str] = []
    if system_message.strip():
        parts.append(system_message.strip())
    for user_msg, assistant_msg in history:
        parts.append(f"<start_of_turn>user\n{user_msg}<end_of_turn>")
        if assistant_msg:
            parts.append(f"<start_of_turn>model\n{assistant_msg}<end_of_turn>")
    parts.append(f"<start_of_turn>user\n{user_message}<end_of_turn>")
    parts.append("<start_of_turn>model")
    return "\n".join(parts)


def estimate_context_usage(
    system_message: str,
    history: List[Tuple[str, str]],
    user_message: str = "",
    *,
    model: str | None = None,
) -> tuple[int, int]:
    """(使用中トークン, 上限 n_ctx) を返す。"""
    prompt_text = _build_prompt_text(system_message, history, user_message)
    used = count_tokens(prompt_text, model)
    return used, DEFAULT_N_CTX


# ───────────────────────────────── respond() ────────────────────────────────

def respond(
    message: str,
    history: List[Tuple[str, str]],
    *,
    model: str | None = None,
    system_message: str = "You are a helpful assistant.",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.7,
    top_p: float = 0.95,
    top_k: int = 40,
    repeat_penalty: float = 1.1,
):

    model_path = resolve_model_path(model)
    llm = _lazy_load_model(model_path)
    provider = LlamaCppPythonProvider(llm)

    agent = LlamaCppAgent(
        provider,
        system_prompt=system_message,
        custom_messages_formatter=_gemma_3_formatter,
        debug_output=False,
    )

    settings = provider.get_provider_default_settings()
    settings.temperature = temperature
    settings.top_k = top_k
    settings.top_p = top_p
    settings.max_tokens = max_tokens
    settings.repeat_penalty = repeat_penalty
    settings.stream = True

    chat_hist = BasicChatHistory()
    for user_msg, assistant_msg in history:
        chat_hist.add_message({"role": Roles.user, "content": user_msg})
        chat_hist.add_message({"role": Roles.assistant, "content": assistant_msg})

    stream = agent.get_chat_response(
        message,
        llm_sampling_settings=settings,
        chat_history=chat_hist,
        returns_streaming_generator=True,
        print_output=False,
    )

    full = ""
    try:
        for tok in stream:
            full += tok
            yield full
    except Exception as exc:
        yield f"[Error] {exc}\n"
