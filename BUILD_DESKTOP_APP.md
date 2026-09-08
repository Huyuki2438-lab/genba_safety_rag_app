> この文書の旧配布方式は廃止しました。現行版は `dist/03_管理者向け資料` と `NAS_DISTRIBUTION_REPORT.md` を参照してください。NAS上のSQLiteの共通更新は使用しません。

# KY写真解析.exe のビルド

## 前提

- Windows 10/11、Edge WebView2 Runtime
- PostgreSQLとNASの設定値を入れた `.env`
- Node.js と Python仮想環境

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
.\build_exe.ps1
```

出力は `dist\KY写真解析\KY写真解析.exe` と依存ファイル一式です。`build_exe.ps1` はReactのビルド、PDF生成用Chromiumの取得、PyInstallerのonedirビルドを順に行います。

`KY写真解析.exe` だけを取り出さず、`dist\KY写真解析` フォルダ全体をローカルPCへ配布してください。`pw-browsers` がPDF生成用、`_internal` がPython/DLL依存ファイルです。

## 配布前の素材確認

ビルド処理は `static` と `templates` を丸ごとコピーせず、実行に必要な
`static/pdf.css`、アプリアイコン2種、`templates/report.html` だけを同梱します。
`history`、現場写真、ユーザー生成PDF、第三者サービスのスクリーンショット、
ローカル用サンプルは配布物に含めません。アプリアイコンを含む配布素材の権利情報は
[ASSET_PROVENANCE.md](ASSET_PROVENANCE.md) で確認・記録してください。

共有DB／NASの設定と配布手順は [DEPLOYMENT.md](DEPLOYMENT.md) を参照してください。
