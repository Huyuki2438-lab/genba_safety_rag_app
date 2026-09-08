> この文書の旧配布方式は廃止しました。現行版は `dist/03_管理者向け資料` と `NAS_DISTRIBUTION_REPORT.md` を参照してください。NAS上のSQLiteの共通更新は使用しません。

# 社内配布・共有履歴の設定

このアプリは、各PCでローカルのWebViewとFastAPIだけを起動します。履歴の索引はNAS上の共通SQLiteファイル、写真は同じNAS上の共通フォルダで管理します。

## 1. 共有基盤（管理者が一度だけ実施）

1. NASに `\\landisk-87a5d6\\disk1\\KY検出システムデータ\\photos` を作成します。利用者には作成・読取・変更権限を付与します（削除権限は不要です）。
2. 開発版と配布フォルダの `.env` に、`.env.shared.example` と同じ `DATABASE_URL` と `PHOTO_STORAGE_DIR` を設定します。両者が同じSQLiteファイルと写真フォルダを参照することが統一の条件です。
3. 管理者PCで `.venv\\Scripts\\python.exe scripts\\initialize_postgres.py` を一度実行します。正常終了後、NAS上に `ky_analysis_history.sqlite3` と `ky_analysis_history` テーブルが作成されます。

### 既存のネットワーク／ローカル履歴を引き継ぐ場合

旧版の `history` フォルダ（`analysis_history.json` と履歴写真フォルダを含む）を、ネットワーク上・ローカル上どちらからでも指定して共通DBへ取り込めます。一度取り込むと、以降はどのPCからも同じ履歴・写真を閲覧できます。

```powershell
.venv\Scripts\python.exe scripts\import_legacy_history.py `
  "C:\Users\利用者\AppData\Local\GenbaSafetyRAGApp\history" `
  "\\server\共有\KY写真解析\history"
```

同じフォルダを再指定しても重複登録しない、再実行可能な取込です。取込元の履歴は削除しません。

SQLiteは同時に1件だけ書き込めるため、解析の保存・削除が同時に発生した場合はアプリが最大30秒待機します。NAS側でこのフォルダの作成・変更権限を利用者へ付与してください。

## 2. 配布

`build_exe.ps1` で作る `dist\\KY写真解析\\` 一式を、読み取り専用の `\\server\\共有\\KY写真解析\\release\\` に置きます。各PCへはこのフォルダ一式を `%LOCALAPPDATA%\\KY写真解析\\app\\` に配布し、`KY写真解析.exe` のショートカットをデスクトップへ置く運用を推奨します。

ネットワーク共有上のEXEを直接実行しないでください。初回配布・更新は、ソフトウェア配布ツール、または管理者がローカルへコピーしてから実行します。これによりDLL読込、PyInstaller展開、WindowsのZone情報・実行速度の問題を避けられます。リリースフォルダを更新する際は、利用者がアプリを閉じた後にローカル配布を更新します。

EXEをコード署名し、共有フォルダを組織の信頼済み場所として管理することも推奨します。

## 障害時

DBまたはNASに接続できない時、アプリ本体は終了せず、履歴の読込・保存・削除時に「共有データへ接続できません。ネットワーク接続を確認してください。」を表示します。復旧後に再度検索またはKY作成を実行してください。
