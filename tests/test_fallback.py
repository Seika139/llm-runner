import json
from pathlib import Path

import pytest

from llm_runner import (
    BackendNotAvailableError,
    ClaudeCli,
    CodexCli,
    FallbackRunner,
    JsonlRecorder,
    LlmRunnerError,
)
from test_cli_runners import make_fake_bin


def unavailable_runner() -> ClaudeCli:
    return ClaudeCli(binary="/nonexistent/claude")


class TestFallbackRunner:
    def test_falls_back_when_backend_not_available(self, tmp_path: Path):
        runner = FallbackRunner(
            [unavailable_runner(), CodexCli(binary=make_fake_bin(tmp_path, "echo from-codex"))]
        )
        assert runner.run("prompt") == "from-codex\n"

    def test_run_json_works_through_fallback(self, tmp_path: Path):
        runner = FallbackRunner(
            [unavailable_runner(), CodexCli(binary=make_fake_bin(tmp_path, "echo '{\"ok\": 1}'"))]
        )
        assert runner.run_json("prompt") == {"ok": 1}

    def test_does_not_fall_back_on_invocation_failure_by_default(self, tmp_path: Path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        runner = FallbackRunner(
            [
                ClaudeCli(binary=make_fake_bin(tmp_path / "a", "exit 1")),
                CodexCli(binary=make_fake_bin(tmp_path / "b", "echo should-not-run")),
            ]
        )
        # 実行失敗 (exit 1) は既定ではフォールバック対象外なのでそのまま送出される
        with pytest.raises(LlmRunnerError, match="exit 1"):
            runner.run("prompt")

    def test_custom_fall_through_extends_conditions(self, tmp_path: Path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        first_bin = make_fake_bin(tmp_path / "a", "exit 1")
        second_bin = make_fake_bin(tmp_path / "b", "echo rescued")
        runner = FallbackRunner(
            [ClaudeCli(binary=first_bin), CodexCli(binary=second_bin)],
            fall_through=(LlmRunnerError,),  # 実行失敗でも次へ進む
        )
        assert runner.run("prompt") == "rescued\n"

    def test_raises_last_error_when_all_fail(self):
        runner = FallbackRunner([unavailable_runner(), CodexCli(binary="/nonexistent/codex")])
        with pytest.raises(BackendNotAvailableError, match="codex"):
            runner.run("prompt")

    def test_empty_runners_rejected(self):
        with pytest.raises(ValueError):
            FallbackRunner([])

    def test_each_attempt_is_recorded_by_its_runner(self, tmp_path: Path):
        log = tmp_path / "runs.jsonl"
        recorder = JsonlRecorder(log)
        runner = FallbackRunner(
            [
                ClaudeCli(binary="/nonexistent/claude", recorder=recorder),
                CodexCli(binary=make_fake_bin(tmp_path, "echo ok"), recorder=recorder),
            ]
        )
        runner.run("prompt")

        records = [json.loads(line) for line in log.read_text().splitlines()]
        assert [(r["backend"], r["ok"]) for r in records] == [
            ("claude-cli", False),
            ("codex-cli", True),
        ]
        assert records[0]["error_kind"] == "backend_not_available"
