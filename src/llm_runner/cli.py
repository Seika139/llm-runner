"""CLI バックエンド (claude / codex)。標準ライブラリのみで動く。"""

from __future__ import annotations

import os
import shutil
import subprocess

from llm_runner.base import Runner, _Invocation
from llm_runner.errors import BackendNotAvailableError, LlmRunnerError, LlmTimeoutError

STDERR_TAIL_CHARS = 500


class _CliRunner(Runner):
    """subprocess 実行の共通部。サブクラスはコマンド構築だけを定義する。"""

    command_name: str  # "claude" | "codex"
    bin_env_var: str  # PATH に無い環境 (systemd 等) 向けの上書き用環境変数

    def __init__(
        self,
        model: str | None = None,
        recorder=None,
        binary: str | None = None,
    ) -> None:
        super().__init__(model=model, recorder=recorder)
        self.binary = binary

    def _resolve_binary(self) -> str:
        path = self.binary or os.environ.get(self.bin_env_var) or shutil.which(self.command_name)
        if not path:
            raise BackendNotAvailableError(
                f"`{self.command_name}` CLI が見つからない。PATH に追加するか、"
                f"環境変数 {self.bin_env_var} か binary 引数でパスを指定すること。"
            )
        return path

    def _build_command(self, binary: str) -> list[str]:
        raise NotImplementedError

    def _invoke(self, prompt: str, timeout: float, inv: _Invocation) -> str:
        command = self._build_command(self._resolve_binary())
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            inv.stderr_tail = _tail(e.stderr)
            raise LlmTimeoutError(timeout) from e
        except OSError as e:
            raise BackendNotAvailableError(f"`{command[0]}` を起動できない: {e}") from e
        inv.exit_code = completed.returncode
        inv.stderr_tail = _tail(completed.stderr)
        if completed.returncode != 0:
            raise LlmRunnerError(
                f"{self.command_name} CLI が失敗 (exit {completed.returncode}): "
                f"{inv.stderr_tail or '(stderr なし)'}"
            )
        return completed.stdout

    def _backend_version(self) -> str | None:
        completed = subprocess.run(
            [self._resolve_binary(), "--version"],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        version = completed.stdout.strip() or completed.stderr.strip()
        return version or None


def _tail(value: str | bytes | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    value = value.strip()
    return value[-STDERR_TAIL_CHARS:] if value else None


class ClaudeCli(_CliRunner):
    """`claude -p` による headless 実行。

    - ツールは全無効 (--tools "")。分類・要約など純テキストタスク用
    - セッションは残さない (--no-session-persistence)
    """

    backend = "claude-cli"
    command_name = "claude"
    bin_env_var = "CLAUDE_BIN"

    def _build_command(self, binary: str) -> list[str]:
        command = [
            binary,
            "-p",
            "--output-format",
            "text",
            "--no-session-persistence",
            "--tools",
            "",
        ]
        if self.model:
            command += ["--model", self.model]
        return command


class CodexCli(_CliRunner):
    """`codex exec` による headless 実行 (read-only サンドボックス)。"""

    backend = "codex-cli"
    command_name = "codex"
    bin_env_var = "CODEX_BIN"

    def __init__(
        self,
        model: str | None = None,
        recorder=None,
        binary: str | None = None,
        cwd: str | None = None,
    ) -> None:
        super().__init__(model=model, recorder=recorder, binary=binary)
        self.cwd = cwd or os.getcwd()

    def _build_command(self, binary: str) -> list[str]:
        command = [
            binary,
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--cd",
            self.cwd,
        ]
        if self.model:
            command += ["--model", self.model]
        command.append("-")
        return command
