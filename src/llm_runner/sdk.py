"""SDK バックエンド (claude-agent-sdk / openai-codex)。

どちらも optional extras でインストールする:

    uv add "llm-runner[claude-sdk]"
    uv add "llm-runner[codex-sdk]"

公開 API は同期。SDK 側の async は内部に隠蔽する。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import shutil
from importlib import import_module, metadata

from llm_runner.base import Runner, _Invocation
from llm_runner.errors import BackendNotAvailableError, LlmTimeoutError


def _import_or_raise(module: str, extra: str):
    try:
        return import_module(module)
    except ImportError as e:
        raise BackendNotAvailableError(
            f"{module} がインストールされていない。`uv add \"llm-runner[{extra}]\"` で導入すること。"
        ) from e


def _package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


class ClaudeSdk(Runner):
    """Claude Agent SDK (claude-agent-sdk) 経由の実行。

    ツールは全無効にし、query() が返すメッセージの result を結合して返す。
    """

    backend = "claude-sdk"

    def __init__(self, model: str | None = None, recorder=None, cwd: str | None = None) -> None:
        super().__init__(model=model, recorder=recorder)
        self.cwd = cwd

    def _invoke(self, prompt: str, timeout: float, inv: _Invocation) -> str:
        sdk = _import_or_raise("claude_agent_sdk", "claude-sdk")

        options_values: dict[str, object] = {"allowed_tools": []}
        if self.model:
            options_values["model"] = self.model
        if self.cwd:
            options_values["cwd"] = self.cwd
        options = sdk.ClaudeAgentOptions(**options_values)

        async def collect() -> str:
            results: list[str] = []
            async for message in sdk.query(prompt=prompt, options=options):
                result = getattr(message, "result", None)
                if result:
                    results.append(str(result))
            return "\n".join(results)

        try:
            return asyncio.run(asyncio.wait_for(collect(), timeout=timeout))
        except TimeoutError as e:
            raise LlmTimeoutError(timeout) from e

    def _backend_version(self) -> str | None:
        return _package_version("claude-agent-sdk")


class CodexSdk(Runner):
    """OpenAI Codex SDK (openai-codex) 経由の実行。

    PyPI の openai-codex は同梱バイナリ (openai-codex-cli-bin) の glibc Linux
    向け wheel が無いため、PATH (または CODEX_BIN) の codex CLI を codex_bin と
    して使う。利用側 pyproject での依存除外方法は README を参照。
    """

    backend = "codex-sdk"

    def __init__(self, model: str | None = None, recorder=None, binary: str | None = None) -> None:
        super().__init__(model=model, recorder=recorder)
        self.binary = binary

    def _invoke(self, prompt: str, timeout: float, inv: _Invocation) -> str:
        sdk = _import_or_raise("openai_codex", "codex-sdk")
        codex_bin = self.binary or os.environ.get("CODEX_BIN") or shutil.which("codex")
        if not codex_bin:
            raise BackendNotAvailableError(
                "`codex` CLI が見つからない (openai-codex は外部バイナリが必要)。"
                "PATH に追加するか、環境変数 CODEX_BIN か binary 引数でパスを指定すること。"
            )

        def call() -> str:
            config = sdk.CodexConfig(codex_bin=codex_bin)
            thread_args: dict[str, object] = {"sandbox": sdk.Sandbox.read_only}
            if self.model:
                thread_args["model"] = self.model
            with sdk.Codex(config=config) as codex:
                thread = codex.thread_start(**thread_args)
                result = thread.run(prompt)
            return str(getattr(result, "final_response", None) or result)

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(call)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as e:
            executor.shutdown(wait=False, cancel_futures=True)
            raise LlmTimeoutError(timeout) from e
        finally:
            executor.shutdown(wait=False)

    def _backend_version(self) -> str | None:
        return _package_version("openai-codex")
