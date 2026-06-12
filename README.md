# llm-runner

claude / codex を CLI または SDK 経由で headless 実行する薄いランナー。「プロンプトを 1 回投げてテキスト (または JSON) を受け取る」ことだけを担当し、プロンプト設計・スキーマ検証・キャッシュ・リトライ方針は利用側に残す。

## 設計方針

- **コアは依存ゼロ**: CLI バックエンド 2 種は標準ライブラリのみで動く。SDK バックエンドは optional extras で分離
- **統一インターフェース**: バックエンドを差し替えても利用側のコードは変わらない (`run` / `run_json` + 統一例外)
- **全実行を記録可能**: 成功・失敗を問わず 1 実行 = 1 レコードを recorder に渡し、エラーの収集と後からの分析を保証する

## インストール

```toml
# 利用側の pyproject.toml
dependencies = ["llm-runner"]

[tool.uv.sources]
llm-runner = { git = "https://github.com/Seika139/llm-runner.git", tag = "v0.1.0" }
```

SDK バックエンドを使う場合は extras を指定する: `llm-runner[claude-sdk]` / `llm-runner[codex-sdk]`。

## 使い方

```python
from llm_runner import ClaudeCli, JsonlRecorder, LlmRunnerError

recorder = JsonlRecorder("/var/log/myapp/llm-runs.jsonl")
runner = ClaudeCli(model="haiku", recorder=recorder)

text = runner.run("このテキストを要約してください: ...")
data = runner.run_json("次を JSON で分類してください: ...")  # フェンス除去 + json.loads
```

バックエンドは 4 種類。設定値から動的に選ぶ場合は `get_runner("claude-cli", model="haiku")` を使う。

| クラス      | 経由             | 認証                     | 備考                                                        |
| ----------- | ---------------- | ------------------------ | ----------------------------------------------------------- |
| `ClaudeCli` | `claude -p`      | マシンの claude ログイン | ツール全無効・セッション残さず。`CLAUDE_BIN` でパス上書き可 |
| `ClaudeSdk` | claude-agent-sdk | 同上                     | extras `claude-sdk` が必要                                  |
| `CodexCli`  | `codex exec`     | マシンの codex ログイン  | read-only サンドボックス。`CODEX_BIN` でパス上書き可        |
| `CodexSdk`  | openai-codex     | 同上                     | extras `codex-sdk` が必要。下記の注意を参照                 |

## エラーハンドリング

バックエンドを問わず統一例外を送出する。

| 例外                       | 意味                                                                        |
| -------------------------- | --------------------------------------------------------------------------- |
| `LlmTimeoutError`          | タイムアウト                                                                |
| `BackendNotAvailableError` | CLI バイナリ / SDK パッケージが見つからない (メッセージに導入手順を含む)    |
| `EmptyResponseError`       | 実行は成功扱いだが応答が空 (CLI 仕様変更などの「静かな故障」を顕在化させる) |
| `LlmRunnerError`           | 上記以外の実行失敗 (基底クラス)                                             |

## 実行記録 (RunRecord)

`recorder` に callable を渡すと、成功・失敗を問わず全実行が記録される。標準実装の `JsonlRecorder` は 1 行 1 JSON で追記する。

レコードには `backend` / `model` / `backend_version` (CLI・SDK の実バージョン) / `duration_ms` / `error_kind` / `stderr_tail` などが含まれ、次のような分析ができる。

```bash
# エラー種別ごとの件数
jq -r 'select(.ok | not) | .error_kind' llm-runs.jsonl | sort | uniq -c

# CLI のバージョンが変わった時期を特定する (挙動変化の切り分け)
jq -r '[.started_at, .backend_version] | @tsv' llm-runs.jsonl | uniq -f1

# 応答が空・劣化していないかの監視
jq -r 'select(.response_chars < 10) | .started_at' llm-runs.jsonl
```

`backend_version` と `stderr_tail` を毎回残すのは、**モデルや CLI の更新起因の異常を後から特定可能にする**ため。deprecation 警告は stderr に現れ、挙動変化はバージョン境界に現れる。

## openai-codex (codex-sdk) の注意

PyPI の `openai-codex` は同梱バイナリ `openai-codex-cli-bin` に依存するが、glibc Linux 向け wheel が提供されない。glibc 環境の利用側は pyproject で同梱バイナリ依存を外し、PATH の `codex` CLI を使わせること (llm-runner はこれを前提に `codex_bin` を自動解決する)。

```toml
# 利用側の pyproject.toml
[[tool.uv.dependency-metadata]]
name = "openai-codex"
requires-dist = []
```

## テスト

```bash
uv run pytest
uv run ruff check .
```
