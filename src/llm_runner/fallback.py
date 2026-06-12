"""複数の Runner を順に試す composite。

「リストを順に試す」という汎用的な仕組みだけを提供し、順序と
フォールバック条件 (policy) は利用側が引数で決める。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from llm_runner.base import DEFAULT_TIMEOUT_SECONDS, Runner
from llm_runner.errors import BackendNotAvailableError

logger = logging.getLogger(__name__)


class FallbackRunner(Runner):
    """Runner のリストを順に試し、最初に成功した応答を返す。

    既定では `BackendNotAvailableError` (バイナリ / SDK が無いという環境の問題)
    のときだけ次の Runner へ進む。タイムアウトや実行失敗は一時的な混雑や
    プロンプト起因の可能性があり、別バックエンドへ進むべきかはタスク次第の
    ため、対象にしたい場合は fall_through で明示する。

    実行記録は各 Runner が自身の recorder に残す (失敗した試行も含む) ので、
    フォールバックの発生は記録から追跡できる。

    使い方::

        runner = FallbackRunner([ClaudeCli(model="haiku"), CodexCli()])
        data = runner.run_json(prompt)
    """

    backend = "fallback"

    def __init__(
        self,
        runners: Sequence[Runner],
        fall_through: tuple[type[Exception], ...] = (BackendNotAvailableError,),
    ) -> None:
        if not runners:
            raise ValueError("runners が空")
        super().__init__()
        self.runners = list(runners)
        self.fall_through = tuple(fall_through)

    def run(self, prompt: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
        last_error: Exception | None = None
        for runner in self.runners:
            try:
                return runner.run(prompt, timeout=timeout)
            except self.fall_through as e:
                logger.warning("%s が失敗、次のバックエンドへフォールバック: %s", runner.backend, e)
                last_error = e
        assert last_error is not None
        raise last_error

    # composite は子 Runner に委譲するため、テンプレートメソッドの実装点は使わない
    def _invoke(self, prompt: str, timeout: float, inv) -> str:
        raise NotImplementedError

    def _backend_version(self) -> str | None:
        return None
