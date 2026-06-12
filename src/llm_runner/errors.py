"""llm-runner の統一例外。

利用側はバックエンド (cli / sdk, claude / codex) を問わず、これらの例外だけを
ハンドリングすればよい。
"""

from __future__ import annotations


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


class EmptyResponseError(LlmRunnerError):
    """実行は成功扱いで終わったが、応答テキストが空だった。

    CLI / SDK の仕様変更やモデル側の異常で「静かに何も返らなくなる」事故を
    エラーとして顕在化させるための例外。
    """
