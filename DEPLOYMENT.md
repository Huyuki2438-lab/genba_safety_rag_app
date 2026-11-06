# 社内配布・共有履歴の設定

現行の配布方式はこの文書ではなく、`scripts/package_distribution.py` が生成する `dist/` 配下の資料が正になります。

- `dist/01_NASへ配置/` … NAS側に置くデータ保管フォルダ一式（工事フォルダ直下の `{export,images,records,reports,usage}` と `.ky_site.json`）
- `dist/02_各PCへ配置/` … 各PCへ配るEXE・`config.json`・`secrets.env`・アプリ共通の`settings/usage_pricing.json`
- `dist/04_管理者向け資料/` … 導入手順・新規現場追加手順・アップデート手順・バックアップ手順・トラブル対応・AIプロンプト参考コピー

導入・更新・新規現場追加・障害対応の具体的な手順は、上記 `dist/04_管理者向け資料/` 内の各txtを参照してください。

## 現行アーキテクチャの要点

- 履歴はSQLiteではなく、**工事フォルダ直下の per-record JSONファイル**（`records/YYYY-MM/<uuid>.json`）で管理します。写真は同じ工事フォルダ直下の `images/` 配下です。旧SQLite方式（`DATABASE_URL`、`scripts/initialize_postgres.py` 等）は廃止済みです。
- 共有先（NASのUNCパス）は各PCの **`config.json`**（`project_id`・`project_name`・`data_root`）で指定します。`.env` の `DATABASE_URL`/`PHOTO_STORAGE_DIR` は現在の配布物には存在しません。
- 料金単価は各PCのEXE配置フォルダ直下の **`settings/usage_pricing.json`** で管理し、工事別の利用台帳は従来どおり **`data_root/usage/YYYY-MM/`** に保存します。共通設定が無い場合だけ、互換性のため現在の工事フォルダ内にある既存の `settings/usage_pricing.json` を読み取ります。複数ファイルの自動統合・削除・上書きは行いません。
- AI呼び出しはVertex AI（Gemini Flash）に一本化されています。認証情報は各PCの `secrets.env`（`VERTEX_API_KEY`・`GEMINI_MODEL`・`GOOGLE_CLOUD_PROJECT`・`GOOGLE_CLOUD_LOCATION`）で管理し、NASや`config.json`には置きません。
- 配布パッケージの作成は `scripts/package_distribution.py` を実行します（開発担当者用）。

## データ保存先の初期設定（config.jsonの手編集は不要）

`config.json` の `data_root` が未設定（空文字）または `config.json` 自体が無い状態でEXEを起動すると、
「初期設定」画面が自動表示されます。利用者はフォルダ選択ダイアログまたはパス直接入力でデータ保存先
（ローカルフォルダ・NAS共有フォルダのUNCパスのどちらも可）を指定でき、接続確認（存在・書き込み・
テストファイル作成/削除）に成功すると保存され、アプリが自動的に再起動して通常画面になります。
`data_root` には `data` フォルダではなく、工事フォルダそのものを指定します。新規配布では工事フォルダ直下に
`export`・`images`・`records`・`reports`・`usage` を置き、`data/` は作成しません。
`project_id`・`project_name`・`secrets.env`（APIキー）はこの画面では扱いません。従来どおり配布前に
`scripts/package_distribution.py` 側で設定するか、`config.json` に既存の値がある場合はそのまま保持されます。

既に `data/` 方式を使用している配布先の設定やデータは、自動変更・自動移行しません。

2回目以降の起動では、設定済みの保存先を自動読込します。保存先に接続できない場合（NAS切断等）は
アプリを終了させず、「再試行」「保存先を変更」を選べる画面を表示します。通常画面の「設定」からも
いつでも保存先の確認・変更ができます。

## 障害時

NASまたは写真フォルダに接続できない時、アプリ本体は終了せず、履歴の読込・保存・削除時に「共有データへ接続できません。ネットワーク接続を確認してください。」等の具体的な日本語メッセージを表示します。復旧後に再度検索またはKY作成を実行してください。詳細は `dist/04_管理者向け資料/トラブル対応.txt` を参照してください。
