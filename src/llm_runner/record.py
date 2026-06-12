"""実行記録 (RunRecord) とその収集先 (recorder)。

全バックエンドの run() は成功・失敗を問わず 1 実行 = 1 レコードを生成する。
利用側は recorder (RunRecord を受け取る callable) を Runner に渡すことで、
エラーログの収集と後からの分析を保証できる。

レコードには model 指定と CLI / SDK の実バージョンが毎回含まれるため、
「バージョンが変わった時期からエラーが増えた」「deprecation 警告が stderr に
出始めた」といったモデル・ツール更新起因の異常を後から特定できる。
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

# プロンプト・応答はサイズと秘匿性の都合で先頭だけ記録する
HEAD_CHARS = 200


@dataclass
class RunRecord:
    backend: str  # "claude-cli" | "claude-sdk" | "codex-cli" | "codex-sdk"
    model: str | None  # 指定したモデル (None = バックエンドのデフォルト)
    backend_version: str | None  # CLI / SDK の実バージョン
    started_at: str  # ISO 8601 (UTC)
    duration_ms: int
    ok: bool
    error_kind: str | None  # timeout | backend_not_available | empty_response | invocation_failed
    error_message: str | None
    exit_code: int | None  # CLI のみ
    stderr_tail: str | None  # CLI のみ。deprecation 警告などが残る
    prompt_chars: int
    prompt_head: str
    response_chars: int
    response_head: str

    def to_dict(self) -> dict:
        return asdict(self)


class JsonlRecorder:
    """RunRecord を 1 行 1 JSON で追記する標準の収集先。

    使い方::

        recorder = JsonlRecorder("/var/log/myapp/llm-runs.jsonl")
        runner = ClaudeCli(model="haiku", recorder=recorder)

    分析例 (エラー種別ごとの件数)::

        jq -r 'select(.ok | not) | .error_kind' llm-runs.jsonl | sort | uniq -c
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def __call__(self, record: RunRecord) -> None:
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
