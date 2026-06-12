"""全バックエンド共通のインターフェース。

run() はテンプレートメソッドで、計測・実行記録 (RunRecord)・空応答検知を
一手に引き受ける。各バックエンドは _invoke() (実行) と _backend_version()
(バージョン取得) だけを実装する。
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable

from llm_runner.errors import (
    BackendNotAvailableError,
    EmptyResponseError,
    LlmRunnerError,
    LlmTimeoutError,
)
from llm_runner.record import HEAD_CHARS, RunRecord

DEFAULT_TIMEOUT_SECONDS = 300

Recorder = Callable[[RunRecord], None]


def extract_json(text: str) -> str:
    """応答からコードフェンスや前置きを取り除き、JSON 部分 (object / array) を取り出す。"""
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError(f"応答に JSON が含まれない: {text[:200]!r}")
    start = min(starts)
    closer = "}" if text[start] == "{" else "]"
    end = text.rfind(closer)
    if end <= start:
        raise ValueError(f"応答の JSON が閉じていない: {text[:200]!r}")
    return text[start : end + 1]


class _Invocation:
    """_invoke() が実行の詳細 (exit code / stderr) を run() に伝えるための入れ物。"""

    def __init__(self) -> None:
        self.exit_code: int | None = None
        self.stderr_tail: str | None = None


class Runner(ABC):
    """プロンプトを 1 回投げてテキストを受け取る、という契約だけを定義する。

    会話の継続・ツール使用・ストリーミングは扱わない。それらが必要な場合は
    各 SDK を直接使うこと。
    """

    backend: str  # サブクラスで定義: "claude-cli" など

    def __init__(self, model: str | None = None, recorder: Recorder | None = None) -> None:
        self.model = model
        self.recorder = recorder
        self._version_cache: str | None = None
        self._version_checked = False

    # -- サブクラスが実装する部分 ------------------------------------------

    @abstractmethod
    def _invoke(self, prompt: str, timeout: float, inv: _Invocation) -> str:
        """プロンプトを実行して応答テキストを返す。失敗は統一例外を送出する。"""

    @abstractmethod
    def _backend_version(self) -> str | None:
        """CLI / SDK の実バージョンを返す (取得できなければ None)。"""

    # -- 公開 API -----------------------------------------------------------

    def run(self, prompt: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
        """プロンプトを実行し、最終応答のテキストを返す。

        成功・失敗を問わず recorder に RunRecord を 1 件渡す。

        Raises:
            LlmTimeoutError: timeout 秒以内に完了しなかった
            BackendNotAvailableError: バイナリ / SDK が見つからない
            EmptyResponseError: 実行は成功したが応答が空だった
            LlmRunnerError: その他の実行失敗
        """
        started = datetime.now(timezone.utc)
        clock = time.monotonic()
        inv = _Invocation()
        text = ""
        error: LlmRunnerError | None = None
        try:
            text = self._invoke(prompt, timeout, inv)
            if not text.strip():
                raise EmptyResponseError(f"{self.backend} returned an empty response")
        except LlmRunnerError as e:
            error = e
            raise
        except Exception as e:  # SDK 由来の想定外例外も統一例外に正規化する
            error = LlmRunnerError(f"{type(e).__name__}: {e}")
            raise error from e
        finally:
            self._record(prompt, text, started, clock, inv, error)
        return text

    def run_json(self, prompt: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Any:
        """run() の応答を JSON としてパースして返す。

        コードフェンスや前置き文は取り除くが、スキーマ検証は行わない
        (利用側で Pydantic 等を使って検証すること)。
        パース失敗は ValueError / json.JSONDecodeError を送出する。
        """
        return json.loads(extract_json(self.run(prompt, timeout=timeout)))

    # -- 内部 ----------------------------------------------------------------

    def _record(
        self,
        prompt: str,
        text: str,
        started: datetime,
        clock: float,
        inv: _Invocation,
        error: LlmRunnerError | None,
    ) -> None:
        if self.recorder is None:
            return
        record = RunRecord(
            backend=self.backend,
            model=self.model,
            backend_version=self._cached_version(),
            started_at=started.isoformat(timespec="seconds"),
            duration_ms=int((time.monotonic() - clock) * 1000),
            ok=error is None,
            error_kind=_classify(error),
            error_message=str(error) if error else None,
            exit_code=inv.exit_code,
            stderr_tail=inv.stderr_tail,
            prompt_chars=len(prompt),
            prompt_head=prompt[:HEAD_CHARS],
            response_chars=len(text),
            response_head=text[:HEAD_CHARS],
        )
        try:
            self.recorder(record)
        except Exception:  # 記録の失敗で本処理を壊さない
            pass

    def _cached_version(self) -> str | None:
        if not self._version_checked:
            self._version_checked = True
            try:
                self._version_cache = self._backend_version()
            except Exception:
                self._version_cache = None
        return self._version_cache


def _classify(error: LlmRunnerError | None) -> str | None:
    if error is None:
        return None
    if isinstance(error, LlmTimeoutError):
        return "timeout"
    if isinstance(error, BackendNotAvailableError):
        return "backend_not_available"
    if isinstance(error, EmptyResponseError):
        return "empty_response"
    return "invocation_failed"
