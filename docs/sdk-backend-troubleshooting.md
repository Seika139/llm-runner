# SDK バックエンドのトラブルシューティング記録

llm-runner の前身である検証プロジェクト (sandbox/llm-python-sample) で 4 バックエンド (`claude-cli` / `claude-sdk` / `codex-cli` / `codex-sdk`) を実証した際に判明した失敗要因と対処の記録。llm-runner の設計判断 (claude-agent-sdk の採用、openai-codex の同梱バイナリ除外、外部 codex CLI の利用) の根拠であり、SDK バックエンドが将来壊れたときの一次資料として残す。

## 検証時の環境

- OS: Ubuntu (glibc) on VPS / Linux 6.14
- Python: 3.14 (uv 管理)
- Claude CLI: 2.1.165
- Codex CLI: 0.135.0 (`codex-cli`)
- uv: 0.11.16

## 結論サマリ

| パターン     | 当初 | 原因                                                                         | 対処後                       |
| ------------ | ---- | ---------------------------------------------------------------------------- | ---------------------------- |
| `codex-cli`  | ✅   | —                                                                            | ✅                           |
| `claude-cli` | ✅   | —                                                                            | ✅                           |
| `codex-sdk`  | ❌   | `openai-codex` の同梱バイナリ wheel が glibc 非対応で sync 不可              | ✅ 外部 codex CLI を使用     |
| `claude-sdk` | ❌   | deprecated な `claude-code-sdk` が新メッセージ `rate_limit_event` を解釈不可 | ✅ `claude-agent-sdk` へ移行 |

## 失敗1: claude-sdk — `MessageParseError: Unknown message type: rate_limit_event`

llm-runner が `claude-agent-sdk` を採用している理由。

### 原因

- deprecated な `claude-code-sdk` (PyPI 最新でも 0.0.25) を使っていた。
- `claude-code-sdk` 0.0.25 の `message_parser.py` は `user / assistant / system / result / stream_event` の 5 種類しか `match` せず、未知タイプを `MessageParseError` で raise する。
- 現行の Claude CLI 2.1.165 はストリームに新メッセージ `rate_limit_event` を流すため、古い SDK が解釈できず即座に落ちる。
- 後継の `claude-agent-sdk` 0.2.91 は `case "rate_limit_event":` を持ち、さらに `case _: return None` で未知タイプを前方互換にスキップする。

### 切り分けを誤らせた罠

- 検証スクリプトの `except` 節が `sdk_package` を文字列 `"claude_agent_sdk"` でハードコードして返していた。
- そのため実際は `claude_code_sdk` が落ちていても、結果 JSON 上は `sdk_package: claude_agent_sdk` と表示され、「agent_sdk が rate_limit_event を扱えない」という誤った仮説に時間を取られた。
- `Unknown message type:` という raise 文字列は `claude_code_sdk` にしか存在しないことに気付き、初めて実体が code_sdk だと確定できた。
- 教訓: **エラー時のメタ情報をハードコードしない**。どのコードパスが落ちたかを示す値は実測値を返す。llm-runner の `RunRecord.backend_version` が「設定値ではなく実測したバージョン」を記録するのはこの教訓に基づく。

## 失敗2: codex-sdk — `ModuleNotFoundError: No module named 'openai_codex'`

llm-runner の pyproject に `[[tool.uv.dependency-metadata]]` がある理由。

### 原因

- `openai-codex` (0.1.0b3) は本体バイナリパッケージ `openai-codex-cli-bin` (==0.137.0a4) に依存する。
- `openai-codex-cli-bin` の wheel は `musllinux` / `macosx` / `win` 向けのみで、glibc Linux (`manylinux`) 向けが存在しない。
- そのため `uv sync` / `uv add openai-codex` が依存解決に失敗し、SDK がそもそも入らない。

### 重要な発見: SDK は外部 codex CLI を駆動できる

- `openai_codex` SDK の実体は `codex app-server --listen stdio://` を `subprocess` で起動し、JSON-RPC over stdio で対話するクライアント。
- バイナリ解決は `client.py` の `resolve_codex_bin()` が担当し、`CodexConfig.codex_bin` を指定するとそのパスを使う。未指定時のみ `openai-codex-cli-bin` の同梱バイナリを探す。
- 既存の Codex CLI 0.135.0 は `codex app-server` サブコマンドを持つ。`CodexConfig(codex_bin="$(which codex)")` を渡すと SDK が外部バイナリを起動し、glibc 環境でも正常応答 (`final_response`) を返すことを実機確認した。
- llm-runner の `CodexSdk` はこの方式 (PATH / `CODEX_BIN` の codex を `codex_bin` に指定) を標準動作にしている。

### 副次的注意点

- SDK 0.1.0b3 が期待する cli-bin は 0.137.0a4 だが、外部 CLI は 0.135.0。`app-server` プロトコルに互換性があり動作した。**CLI を更新したら codex-sdk の疎通を再確認すること** (プロトコル不整合で `turn failed` 等になり得る)。`RunRecord` の `backend_version` を見れば、CLI 更新と失敗増加の相関を後から特定できる。
- この方式は「`codex` が PATH にあり、ログイン済み」という前提に依存する。CI 等で codex CLI が無い環境では `BackendNotAvailableError` になる (FallbackRunner 利用時は次のバックエンドへ進む)。

## 調査時にハマった環境的な罠

- `uv run --group <g>` は実行のたびに pyproject 定義へ環境を再同期する。検証のために `uv pip uninstall` したパッケージが `uv run` で復活し、「直したのに直らない」状態に見えた。
  - 対処: SDK 入れ替えの検証中は `uv run --no-sync` を使い、自動再同期を止める。
