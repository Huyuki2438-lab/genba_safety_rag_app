> この文書の旧配布方式は廃止しました。現行版は `dist/04_管理者向け資料` と `NAS_DISTRIBUTION_REPORT.md` を参照してください。NAS上のSQLiteの共通更新は使用しません。

# KY安全管理.exe のビルド

## 前提

- Windows 10/11、Microsoft Edge
- Vertex AIの設定値（`VERTEX_API_KEY`・`GEMINI_MODEL`・`GOOGLE_CLOUD_PROJECT`・`GOOGLE_CLOUD_LOCATION`）を入れた `.env`
- Node.js と Python仮想環境

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
.\build_exe.ps1
```

`build_exe.ps1` はReactのビルド、PyInstallerのonedirビルド（`build\portable\KY安全管理.exe`）、`scripts\package_distribution.py` による配布物の組み立て（`dist\` 配下）を順に行います。

出力される `dist\02_各PCへ配置\KY安全管理` フォルダ一式（EXE・`config.json`・`secrets.env`）をローカルPCへ配布してください。`_internal` がPython/DLL依存ファイルです。

## 配布前の素材確認

ビルド処理は `static` と `templates` を丸ごとコピーせず、実行に必要な
`static/pdf.css`、アプリアイコン2種、`templates/report.html` だけを同梱します。
`history`、現場写真、ユーザー生成PDF、第三者サービスのスクリーンショット、
ローカル用サンプルは配布物に含めません。アプリアイコンを含む配布素材の権利情報は
[ASSET_PROVENANCE.md](ASSET_PROVENANCE.md) で確認・記録してください。

共有DB／NASの設定と配布手順は [DEPLOYMENT.md](DEPLOYMENT.md) を参照してください。
