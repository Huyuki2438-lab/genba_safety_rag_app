# 社内配布・共有履歴の設定

このアプリは、各PCでローカルのWebViewとFastAPIだけを起動します。履歴を共有するのはPostgreSQLであり、SQLiteファイルをNASに置く方式は使用しません。

## 1. 共有基盤（管理者が一度だけ実施）

1. 社内サーバーにPostgreSQLを用意し、アプリ専用のDBと最小権限のユーザーを作成します。
2. NASに `\\nas-server\\KY写真解析\\data\\photos` を作成します。利用者には作成・読取・変更権限を付与します（削除権限は不要です）。
3. 配布フォルダの `.env` を `.env.shared.example` を元に作成し、`DATABASE_URL` と `PHOTO_STORAGE_DIR` を設定します。秘密情報を含む `.env` はソース管理へ登録しません。
4. 管理者PCで `.venv\\Scripts\\python.exe scripts\\initialize_postgres.py` を一度実行します。正常終了後、`ky_analysis_history` が作成されます。

### 既存のネットワーク／ローカル履歴を引き継ぐ場合

旧版の `history` フォルダ（`analysis_history.json` と履歴写真フォルダを含む）を、ネットワーク上・ローカル上どちらからでも指定して共通DBへ取り込めます。一度取り込むと、以降はどのPCからも同じ履歴・写真を閲覧できます。

```powershell
.venv\Scripts\python.exe scripts\import_legacy_history.py `
  "C:\Users\利用者\AppData\Local\GenbaSafetyRAGApp\history" `
  "\\server\共有\KY写真解析\history"
```

同じフォルダを再指定しても重複登録しない、再実行可能な取込です。取込元の履歴は削除しません。

PostgreSQL側にはネットワークから到達できるよう、DBサーバーのTCP 5432（または組織指定ポート）とpg_hba.confを、利用PC／アプリ用ユーザーに限定して設定してください。

## 2. 配布

`build_exe.ps1` で作る `dist\\KY写真解析\\` 一式を、読み取り専用の `\\server\\共有\\KY写真解析\\release\\` に置きます。各PCへはこのフォルダ一式を `%LOCALAPPDATA%\\KY写真解析\\app\\` に配布し、`KY写真解析.exe` のショートカットをデスクトップへ置く運用を推奨します。

ネットワーク共有上のEXEを直接実行しないでください。初回配布・更新は、ソフトウェア配布ツール、または管理者がローカルへコピーしてから実行します。これによりDLL読込、PyInstaller展開、WindowsのZone情報・実行速度の問題を避けられます。リリースフォルダを更新する際は、利用者がアプリを閉じた後にローカル配布を更新します。

EXEをコード署名し、共有フォルダを組織の信頼済み場所として管理することも推奨します。

## 障害時

DBまたはNASに接続できない時、アプリ本体は終了せず、履歴の読込・保存・削除時に「共有データへ接続できません。ネットワーク接続を確認してください。」を表示します。復旧後に再度検索またはKY作成を実行してください。
