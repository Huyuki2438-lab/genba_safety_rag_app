# デスクトップアプリ化 (GenbaSafetyRAGApp.exe)

## ビルド手順

```powershell
# 1回だけ: 依存関係インストール
.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install

# ビルド (React build + Playwright Chromium取得 + PyInstaller onedir + アセット配置)
.\build_exe.ps1
```

出力先: `dist\GenbaSafetyRAGApp\` フォルダ一式。このフォルダを丸ごとネットワーク共有へコピーする。

## 配布フォルダ構成

```
GenbaSafetyRAGApp\
  GenbaSafetyRAGApp.exe   ← 利用者がダブルクリックするのはこれ
  _internal\               ← PyInstallerが同梱したPython本体・ライブラリ一式
  dist\                    ← Reactビルド成果物 (index.html, assets/)
  static\                  ← pdf.css等
  templates\                ← report.html等 (Jinja2テンプレート)
  pw-browsers\              ← PDF生成用Chromium(Playwright)を同梱
  .env                      ← APIキー等 (配布時に各拠点用に書き換え可能)
```

## 利用者の操作

1. ネットワーク共有フォルダ (`\\サーバー名\共有フォルダ\GenbaSafetyRAGApp\`) を開く
2. `GenbaSafetyRAGApp.exe` をダブルクリック
3. 専用ウィンドウでアプリが開く
4. 作業する
5. 右上の「×」で終了 (内部サーバー・WebView2・すべて終了)

コマンドプロンプト、ブラウザのアドレスバー、Pythonの存在は一切表示されない。

## 開発時 (これまで通り)

`npm run dev` / `npm run dev:backend` はこれまで通り使用可能。`desktop_app.py` は
配布用のexe起動経路にのみ影響し、開発時の挙動 (BASE_DIR、HISTORY_DIR等) は変更していない。
