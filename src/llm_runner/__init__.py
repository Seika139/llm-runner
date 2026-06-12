"""llm-runner — claude / codex を CLI または SDK 経由で headless 実行する薄いランナー。"""

from llm_runner.base import DEFAULT_TIMEOUT_SECONDS, Runner, extract_json
from llm_runner.cli import ClaudeCli, CodexCli
from llm_runner.errors import (
    BackendNotAvailableError,
    EmptyResponseError,
    LlmRunnerError,
    LlmTimeoutError,
)
from llm_runner.fallback import FallbackRunner
from llm_runner.record import JsonlRecorder, RunRecord
from llm_runner.sdk import ClaudeSdk, CodexSdk

BACKENDS = {
    "claude-cli": ClaudeCli,
    "claude-sdk": ClaudeSdk,
    "codex-cli": CodexCli,
    "codex-sdk": CodexSdk,
}


def get_runner(backend: str, **kwargs) -> Runner:
    """バックエンド名 (例: "claude-cli") から Runner を生成する。

    設定ファイルや環境変数でバックエンドを切り替える利用側のためのファクトリ。
    """
    try:
        cls = BACKENDS[backend]
    except KeyError:
        raise ValueError(f"unknown backend: {backend!r} (有効値: {', '.join(BACKENDS)})") from None
    return cls(**kwargs)


__all__ = [
    "BACKENDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "BackendNotAvailableError",
    "ClaudeCli",
    "ClaudeSdk",
    "CodexCli",
    "CodexSdk",
    "EmptyResponseError",
    "FallbackRunner",
    "JsonlRecorder",
    "LlmRunnerError",
    "LlmTimeoutError",
    "RunRecord",
    "Runner",
    "extract_json",
    "get_runner",
]
