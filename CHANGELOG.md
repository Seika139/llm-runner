# CHANGELOG

すべての注目すべき変更はこのファイルに記録されます。

フォーマットは [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づいており、
このプロジェクトは [Semantic Versioning](https://semver.org/lang/ja/) に準拠しています。

## Tagged Releases

## [Unreleased]

### Added

- claude / codex を CLI または SDK 経由で headless 実行する 4 バックエンド (`ClaudeCli` / `ClaudeSdk` / `CodexCli` / `CodexSdk`) を統一インターフェース (`run` / `run_json` + 統一例外) で提供
- バックエンド名から Runner を生成する `get_runner()` ファクトリを追加
- 全実行を成功・失敗を問わず `RunRecord` として記録する仕組みと、JSONL に追記する標準収集先 `JsonlRecorder` を追加
- 空応答を `EmptyResponseError` として検知し、CLI / SDK の実バージョンを毎レコードに記録 (モデル・ツール更新起因の異常を後から分析可能)
- SDK バックエンドの依存を optional extras (`llm-runner[claude-sdk]` / `llm-runner[codex-sdk]`) として分離 (コアは依存ゼロ)
