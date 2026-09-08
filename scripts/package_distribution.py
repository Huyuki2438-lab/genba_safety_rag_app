"""Assemble the company-only deployment; never print secrets or overwrite NAS data."""
from pathlib import Path
import json
import os
import shutil
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
NAS = DIST / "01_NASへ配置" / "KY安全管理"
PC = DIST / "02_各PCへ配置" / "KY安全管理"
DOCS = DIST / "03_管理者向け資料"

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8-sig")

def main():
    env = {**dotenv_values(ROOT / ".env"), **{k: v for k, v in os.environ.items() if k.startswith("GEMINI_")}}
    key = env.get("GEMINI_A_API_KEY") or env.get("GEMINI_API_KEY")
    if not key or key.startswith("<"):
        raise SystemExit("Existing real Gemini key was not found; package not created")
    binary = ROOT / "build" / "portable" / "KY安全管理.exe"
    if not binary.is_file():
        raise SystemExit("Build EXE first")
    for project in ("001_芝原改良工事", "template_project"):
        for folder in ("records", "images", "reports", "export"):
            (NAS / project / "data" / folder).mkdir(parents=True, exist_ok=True)
    PC.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, PC / binary.name)
    # Preserve per-site configuration on subsequent builds.
    if not (PC / "config.json").exists():
        write(PC / "config.json", json.dumps({"project_id": "001", "project_name": "芝原改良工事",
            "data_root": r"\\landisk-ee6245\disk1\KY安全管理\001_芝原改良工事\data"}, ensure_ascii=False, indent=2))
    secret = "GEMINI_API_KEY=" + key + "\n"
    for name in ("GEMINI_A_MODEL", "GEMINI_B_API_KEY", "GEMINI_B_MODEL", "VERTEX_API_KEY", "VERTEX_MODEL", "VERTEX_PROJECT_ID", "VERTEX_LOCATION"):
        if env.get(name):
            secret += name + "=" + env[name] + "\n"
    # dotenv expects UTF-8 without BOM.
    (PC / "secrets.env").write_text(secret, encoding="utf-8")
    write(PC / "README.txt", """
【KY安全管理 使用方法】
1. この「KY安全管理」フォルダを各PCのローカルディスクへコピーします。
2. 「KY安全管理.exe」をダブルクリックします。ブラウザが自動で開きます。初回は数十秒かかることがあります。
3. 写真を選び、通常どおりKY分析を行います。保存された履歴は同じ現場のPCで共有されます。
4. PDF保存ではNASに保存すると同時に、このPCへダウンロードします。
5. 使用後は画面上の「アプリを終了」を押してください。ブラウザのタブを閉じるだけでは終了しません。
APIキーは設定済みです。通常、設定変更は不要です。フォルダは社内のみで扱ってください。
共有フォルダに接続できない場合は、社内ネットワークおよびNASへの接続を確認してください。
動作環境：Windows 10/11 64bit、Microsoft Edge。Python・Node.jsの追加インストールは不要です。
""")
    write(NAS / "README_NAS.txt", """
【NAS管理者向け】
01_NASへ配置内の「KY安全管理」をNASのdisk1共有内へフォルダとして配置します。
例：\\\\landisk-ee6245\\disk1\\KY安全管理
NASはデータ保管だけを担当します。EXE、secrets.env、APIキー、ログは置きません。
利用者には各現場のdata以下で一覧表示・読み取り・作成・書き込み・名前変更・削除の権限が必要です。
新しい現場はtemplate_projectをコピーして「002_○○工事」等へ改名します。
各PCのconfig.jsonのproject_id、project_name、data_rootをその現場に合わせ、アプリを再起動します。
project_idは途中変更しないでください。違うIDの履歴は混在防止のため表示されません。
現場削除は全員のアプリを終了し、バックアップと保存期間を確認して管理者が行ってください。
バックアップ対象は現場フォルダ全体（records/images/reports/exportと削除印）です。
NAS交換時は全員終了→フォルダ全体コピー→権限再設定→各PCのdata_root変更→履歴・写真・PDF確認。
既存現場へ空テンプレートを上書きする更新は行わないでください。
同じフォルダ内の一時ファイルから正式ファイルへのrenameで公開します。SMB/NASの永続化保証は機種・設定に依存します。
切断で保存結果が不明になった場合は、復旧後に履歴を検索してから再保存してください。
""")
    write(DOCS / "導入手順.txt", """
【初回導入】
1. 01_NASへ配置のKY安全管理をNASへコピーし、共有名と権限を設定します。
2. 02_各PCへ配置のKY安全管理/config.jsonを実際のUNCパスに合わせます。APIキーはsecrets.envに設定済みです。
   初期値は確認できたNASのdisk1共有です。NAS名・共有名が異なる場合は配布前に変更が必要です。
3. このPC用フォルダ（EXE、config.json、secrets.env、README.txtの4ファイル）を各PCへコピーします。
4. EXEをダブルクリック。写真→分析→履歴→PDF保存→別PCで同じ履歴・写真・PDFを確認します。
5. 両PCから同時に保存し、履歴が2件増えることを確認します。実NASでこの受入確認を行ってください。
6. 「アプリを終了」を押します。同一PCの二重起動では既存アプリのブラウザを開きます。
Windows 10/11 64bitとMicrosoft Edgeが必要です。Python、Node.js、DBサーバーは不要です。
NAS上のEXEからの直接実行は拒否します。ネットワークドライブも同様です。
ログは各PCの%LOCALAPPDATA%\\KY安全管理\\logsです。APIキーは記録しません。
旧SQLiteをそのまま新recordsへ置いても読めません。元データを保全し、開発担当者がscripts/migrate_sqlite_history.pyで読み取り専用移行できます。
旧analysis_history.json形式にはscripts/import_legacy_history.pyが対応します。移行後に件数・写真を照合してください。
""")
    write(DOCS / "新規現場追加手順.txt", """
【新規現場】
1. NASのtemplate_projectをコピーし「002_○○工事」などへ改名します。
2. PC用フォルダを用意し、config.jsonをメモ帳で変更してUTF-8で保存します。
   project_id：002など一意のID、project_name：工事名、data_root：現場/dataへの絶対UNCパス。
   JSON内のバックスラッシュは2個ずつ記載します。APIキーはconfig.jsonへ書きません。
3. 同じ現場を使う全PCへ、同じ3項目のconfig.jsonを配布します。EXEは全現場共通です。
4. EXE起動後、現場名と履歴を確認します。設定変更時はアプリを終了して再起動します。
フォルダ権限も現場別に管理してください。IDによる表示分離はNASのアクセス権限の代わりではありません。
""")
    write(DOCS / "アップデート手順.txt", """
【更新】
1. 全PCで「アプリを終了」を押します。NASの現場データをバックアップします。
2. 各PCのconfig.jsonとsecrets.envを保持し、KY安全管理.exeだけを新しいものに差し替えます。
3. NAS側の現場フォルダは変更しません。01_NASへ配置を既存データへ上書きしないでください。
4. 既存履歴、写真、PDFが読めることと、新規保存を確認します。
5. 問題があればEXEだけを前の版へ戻します。データ形式はschema_version=1です。
未対応のschema_versionや破損JSONは一覧から除外されます。旧版へ戻す前に互換性を確認してください。
開発担当者の再ビルドはbuild_exe.ps1です。生成物とsecrets.envをGitへ追加しないでください。
""")
    write(DOCS / "バックアップ手順.txt", """
【バックアップ・復元】
NAS管理機能の世代付きスナップショット・別媒体への定期バックアップを設定します。
対象はKY安全管理の各現場フォルダ全体です。recordsだけでは写真・PDFを復元できません。
全PCのアプリを終了した状態でバックアップすれば、保存途中を含む不整合を避けられます。
削除印（.deleted）も保管します。これを失うと削除した履歴が再表示されます。
復元は全PC終了→対象現場一式を復元→権限確認→履歴・写真・PDFを照合、の順です。
secrets.envはNASへ置かず、会社指定の管理者用保管場所で別管理してください。
.uploadingは未完了ファイルです。全PC終了とバックアップ後に管理者が確認して整理できます。
通信断後の孤立写真・PDFは自動削除しません。保存済み履歴を壊さないことを優先します。
""")
    write(DOCS / "トラブル対応.txt", """
【共有フォルダに接続できない】
エクスプローラーでconfig.jsonのdata_rootを開き、LAN・VPN・NAS電源・共有名・権限を確認します。
NAS復旧後は履歴の検索ボタンで再読込します。アプリはローカルデータへの自動切替をしません。
【保存失敗】
共有先の書き込み・名前変更権限と空き容量を確認します。保存成功とは表示しません。
保存完了直後の切断ではNASに保存済みの可能性があります。まず履歴を検索し、重複保存を避けてください。未保存ならKY画面の「分析結果の保存を再試行」を押します（AI再呼出なし）。
【破損JSON】
不正JSON・未対応schema_versionは表示されません。元ファイルを保全しバックアップから復元します。
一時ファイル（.uploading）は履歴一覧に表示されません。
【写真・PDFが見つからない】
元の履歴本文は残ります。管理者がバックアップから対象ファイルを復元します。
写真がない状態ではexportが失敗します。PDFがない履歴はKY画面で再表示してPDFを再生成できます。
【PDF失敗】
Microsoft Edgeがインストールされ起動できること、会社の実行制限、NASの権限・容量を確認します。
【起動・二重起動・終了】
EXE・config.json・secrets.envをローカルPCの同じフォルダへ置きます。
既に起動中ならブラウザが開きます。タブを閉じただけの場合もEXEの再実行で戻れます。
終了は画面の「アプリを終了」です。分析中は完了を待ちます。通常の終了でサーバーとPDF用子プロセスを停止します。
【NAS移設】
全データを移行し、各PCのdata_rootのみ変更します。project_idは維持します。
【API接続】
インターネット・会社のプロキシ・APIの利用上限を管理者が確認します。
secrets.envを画面共有・メール・公開リポジトリへ掲載しないでください。
""")
    print("Distribution assembled; real API key configured (value hidden)")
    print("PC package files:", len(list(PC.iterdir())))
    print("PC package MiB:", round(sum(p.stat().st_size for p in PC.rglob('*') if p.is_file()) / 1024**2, 2))

if __name__ == "__main__":
    main()
