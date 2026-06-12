import json
import stat
from pathlib import Path

import pytest

from llm_runner import (
    ClaudeCli,
    CodexCli,
    EmptyResponseError,
    JsonlRecorder,
    LlmRunnerError,
    LlmTimeoutError,
)


def make_fake_bin(tmp_path: Path, body: str) -> str:
    """テスト用の偽 CLI。--version に応答し、それ以外は body を実行する。"""
    script = tmp_path / "fake-llm"
    script.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo "9.9.9 (fake)"; exit 0; fi\n'
        "cat > /dev/null\n"  # stdin のプロンプトを読み捨てる
        f"{body}\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


class TestCommandConstruction:
    def test_claude_headless_flags(self, tmp_path):
        runner = ClaudeCli(model="haiku", binary="/usr/bin/claude")
        command = runner._build_command("/usr/bin/claude")
        assert command == [
            "/usr/bin/claude",
            "-p",
            "--output-format",
            "text",
            "--no-session-persistence",
            "--tools",
            "",
            "--model",
            "haiku",
        ]

    def test_codex_headless_flags(self):
        runner = CodexCli(model="gpt-x", binary="/usr/bin/codex", cwd="/work")
        command = runner._build_command("/usr/bin/codex")
        assert command == [
            "/usr/bin/codex",
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--cd",
            "/work",
            "--model",
            "gpt-x",
            "-",
        ]

    def test_binary_resolution_order(self, monkeypatch, tmp_path):
        env_bin = make_fake_bin(tmp_path, "echo from-env")
        monkeypatch.setenv("CLAUDE_BIN", env_bin)
        assert ClaudeCli()._resolve_binary() == env_bin
        # 引数指定が環境変数より優先される
        assert ClaudeCli(binary="/explicit/claude")._resolve_binary() == "/explicit/claude"


class TestRun:
    def test_returns_stdout(self, tmp_path):
        runner = ClaudeCli(binary=make_fake_bin(tmp_path, "echo hello"))
        assert runner.run("prompt") == "hello\n"

    def test_run_json_parses_fenced_output(self, tmp_path):
        body = "echo '```json'; echo '{\"ok\": true}'; echo '```'"
        runner = ClaudeCli(binary=make_fake_bin(tmp_path, body))
        assert runner.run_json("prompt") == {"ok": True}

    def test_nonzero_exit_raises(self, tmp_path):
        runner = ClaudeCli(binary=make_fake_bin(tmp_path, "echo broken >&2; exit 3"))
        with pytest.raises(LlmRunnerError, match="exit 3"):
            runner.run("prompt")

    def test_empty_response_raises(self, tmp_path):
        runner = ClaudeCli(binary=make_fake_bin(tmp_path, "true"))
        with pytest.raises(EmptyResponseError):
            runner.run("prompt")

    def test_timeout_raises(self, tmp_path):
        runner = ClaudeCli(binary=make_fake_bin(tmp_path, "sleep 5; echo late"))
        with pytest.raises(LlmTimeoutError):
            runner.run("prompt", timeout=0.3)


class TestRecording:
    def read_records(self, path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_success_record_includes_version_and_sizes(self, tmp_path):
        log = tmp_path / "runs.jsonl"
        runner = ClaudeCli(
            model="haiku",
            binary=make_fake_bin(tmp_path, "echo hello"),
            recorder=JsonlRecorder(log),
        )
        runner.run("こんにちは")

        (record,) = self.read_records(log)
        assert record["ok"] is True
        assert record["backend"] == "claude-cli"
        assert record["model"] == "haiku"
        assert record["backend_version"] == "9.9.9 (fake)"
        assert record["prompt_chars"] == 5
        assert record["response_head"] == "hello\n"
        assert record["error_kind"] is None

    def test_failure_records_kind_and_stderr(self, tmp_path):
        log = tmp_path / "runs.jsonl"
        runner = ClaudeCli(
            binary=make_fake_bin(tmp_path, "echo 'model deprecated' >&2; exit 1"),
            recorder=JsonlRecorder(log),
        )
        with pytest.raises(LlmRunnerError):
            runner.run("prompt")

        (record,) = self.read_records(log)
        assert record["ok"] is False
        assert record["error_kind"] == "invocation_failed"
        assert record["exit_code"] == 1
        assert "model deprecated" in record["stderr_tail"]

    def test_empty_response_is_recorded_as_its_own_kind(self, tmp_path):
        log = tmp_path / "runs.jsonl"
        runner = ClaudeCli(
            binary=make_fake_bin(tmp_path, "true"), recorder=JsonlRecorder(log)
        )
        with pytest.raises(EmptyResponseError):
            runner.run("prompt")
        (record,) = self.read_records(log)
        assert record["error_kind"] == "empty_response"

    def test_timeout_is_recorded(self, tmp_path):
        log = tmp_path / "runs.jsonl"
        runner = ClaudeCli(
            binary=make_fake_bin(tmp_path, "sleep 5"), recorder=JsonlRecorder(log)
        )
        with pytest.raises(LlmTimeoutError):
            runner.run("prompt", timeout=0.3)
        (record,) = self.read_records(log)
        assert record["error_kind"] == "timeout"

    def test_recorder_failure_does_not_break_run(self, tmp_path):
        def broken_recorder(record):
            raise OSError("disk full")

        runner = ClaudeCli(
            binary=make_fake_bin(tmp_path, "echo hello"), recorder=broken_recorder
        )
        assert runner.run("prompt") == "hello\n"
