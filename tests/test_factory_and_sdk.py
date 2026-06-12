import pytest

from llm_runner import (
    BACKENDS,
    BackendNotAvailableError,
    ClaudeSdk,
    CodexSdk,
    get_runner,
)


class TestFactory:
    def test_creates_runner_by_name(self):
        runner = get_runner("claude-cli", model="haiku")
        assert runner.backend == "claude-cli"
        assert runner.model == "haiku"

    def test_unknown_backend_raises_with_valid_values(self):
        with pytest.raises(ValueError, match="claude-cli"):
            get_runner("gemini-cli")

    def test_all_backends_are_registered(self):
        assert set(BACKENDS) == {"claude-cli", "claude-sdk", "codex-cli", "codex-sdk"}


class TestSdkNotInstalled:
    """SDK extras 未導入の環境では、導入方法を含むエラーになることを保証する。

    実行環境に SDK が入っているかに依存しないよう、import 失敗を
    monkeypatch で再現して検証する。
    """

    @pytest.fixture(autouse=True)
    def no_sdk(self, monkeypatch):
        def fail(module: str):
            raise ImportError(f"No module named {module!r}")

        monkeypatch.setattr("llm_runner.sdk.import_module", fail)

    def test_claude_sdk_raises_with_install_hint(self):
        with pytest.raises(BackendNotAvailableError, match=r"llm-runner\[claude-sdk\]"):
            ClaudeSdk().run("prompt")

    def test_codex_sdk_raises_with_install_hint(self):
        with pytest.raises(BackendNotAvailableError, match=r"llm-runner\[codex-sdk\]"):
            CodexSdk().run("prompt")
