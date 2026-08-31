"""llm-runner の統一例外。

利用側はバックエンド (cli / sdk, claude / codex) を問わず、これらの例外だけを
ハンドリングすればよい。
"""

from __future__ import annotations

import re

_RATE_LIMIT_RE = re.compile(
    r"(?:rate[ _-]?limit|usage[ _-]?limit|quota exceeded|too many requests|"
    r"you(?:'|’)ve hit your limit|status(?:_code)?[=: ]+429|http(?: error)? 429)",
    re.IGNORECASE,
)


class LlmRunnerError(Exception):
    """実行失敗の基底例外 (非ゼロ終了、SDK 内部エラーなど)。"""


class LlmTimeoutError(LlmRunnerError):
    """タイムアウト。"""

    def __init__(self, timeout: float) -> None:
        super().__init__(f"timed out after {timeout} seconds")
        self.timeout = timeout


class BackendNotAvailableError(LlmRunnerError):
    """CLI バイナリや SDK パッケージが見つからない。

    message にインストール手順のヒントを含める。
    """


class RateLimitError(LlmRunnerError):
    """プロバイダーの rate / usage limit により実行できない。"""


def is_rate_limit_error(value: object) -> bool:
    """CLI の stderr や SDK 例外が rate limit を表すかを保守的に判定する。"""
    for attr in ("status_code", "status"):
        if getattr(value, attr, None) == 429:
            return True
    code = getattr(value, "code", None)
    if isinstance(code, str) and code.lower().replace("-", "_") in {
        "rate_limit",
        "rate_limit_error",
        "too_many_requests",
    }:
        return True
    return bool(_RATE_LIMIT_RE.search(str(value)))


class EmptyResponseError(LlmRunnerError):
    """実行は成功扱いで終わったが、応答テキストが空だった。

    CLI / SDK の仕様変更やモデル側の異常で「静かに何も返らなくなる」事故を
    エラーとして顕在化させるための例外。
    """
