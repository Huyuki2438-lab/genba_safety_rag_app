"""Assemble a new company-only deployment without exposing credentials."""
import argparse
from pathlib import Path
import json
import re
import shutil
import uuid
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
NAS = DIST / "01_NASへ配置"
PC = DIST / "02_各PCへ配置"
MANUAL_SRC = ROOT / "利用マニュアル"
MANUAL_DIST = DIST / "03_マニュアル"
DOCS = DIST / "04_管理者向け資料"
PROMPTS_SRC = ROOT / "backend" / "app" / "core" / "prompts" / "templates"
PROMPTS_DIST = DOCS / "AIプロンプト"
PRICING_SRC = ROOT / "settings" / "usage_pricing.json"
COPY_ENV = ROOT / "コピー.env"
SECRET_FIELDS = (
    "VERTEX_API_KEY",
    "GEMINI_MODEL",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
)
_API_KEY_PATTERN = re.compile(r"[A-Za-z0-9._~!$%&()*+,\-/:;=?@\[\]^`{|}]{20,200}")
_MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{1,127}")
_PROJECT_PATTERN = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]")
_LOCATION_PATTERN = re.compile(r"[a-z][a-z0-9-]{1,62}[a-z0-9]")
NAS_UNC_ROOT = r"I:\マイドライブ\KY安全管理"
SITE_FOLDERS = ("export", "images", "records", "reports", "usage")
DEFAULT_DATA_ROOT = NAS_UNC_ROOT + r"\001_芝原改良工事"

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8-sig")


def create_site_structure(path, project_id=None, project_name=None):
    """Create a new distribution skeleton without nesting it under data/."""
    for folder in SITE_FOLDERS:
        (path / folder).mkdir(parents=True, exist_ok=True)
    if project_id:
        marker = json.dumps(
            {"project_id": project_id, "project_name": project_name or ""},
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        marker_path = path / ".ky_site.json"
        if not marker_path.exists():
            marker_path.write_text(marker, encoding="utf-8")


def default_config():
    return {
        "project_id": "001",
        "project_name": "芝原改良工事",
        "data_root": DEFAULT_DATA_ROOT,
    }


def install_pricing_config(pc_dir, source=PRICING_SRC):
    """Install the app-wide pricing file without replacing an existing one."""
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(f"Pricing settings not found: {source}")
    target = Path(pc_dir) / "settings" / "usage_pricing.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(source, target)
    return target


def load_distribution_secrets(source=COPY_ENV):
    """Read and validate deploy-time settings without logging their values."""
    source = Path(source)
    if not source.is_file():
        raise ValueError(f"Secrets source file was not found: {source.name}")
    values = dotenv_values(source, interpolate=False)
    missing = [name for name in SECRET_FIELDS if not (values.get(name) or "").strip()]
    if missing:
        raise ValueError("Required settings are missing from secrets source: " + ", ".join(missing))

    clean = {name: values[name].strip() for name in SECRET_FIELDS}
    key = clean["VERTEX_API_KEY"]
    placeholder = key.startswith("<") or key.lower() in {
        "changeme", "replace-me", "your-api-key", "your_api_key"
    }
    if placeholder or not _API_KEY_PATTERN.fullmatch(key):
        raise ValueError("VERTEX_API_KEY has an invalid format")
    if not _MODEL_PATTERN.fullmatch(clean["GEMINI_MODEL"]):
        raise ValueError("GEMINI_MODEL has an invalid format")
    if not _PROJECT_PATTERN.fullmatch(clean["GOOGLE_CLOUD_PROJECT"]):
        raise ValueError("GOOGLE_CLOUD_PROJECT has an invalid format")
    if not _LOCATION_PATTERN.fullmatch(clean["GOOGLE_CLOUD_LOCATION"]):
        raise ValueError("GOOGLE_CLOUD_LOCATION has an invalid format")
    return clean


def write_secrets_env(pc_dir, values):
    """Create secrets.env once; callers must supply a new staging directory."""
    target = Path(pc_dir) / "secrets.env"
    if target.exists():
        raise FileExistsError("Refusing to overwrite secrets.env")
    content = "".join(f"{name}={values[name]}\n" for name in SECRET_FIELDS)
    target.write_text(content, encoding="utf-8")
    return target


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Assemble a new distribution candidate from コピー.env."
    )
    parser.add_argument(
        "--distribution-output",
        required=True,
        type=Path,
        help="Path for a new distribution candidate; an existing path is rejected.",
    )
    return parser.parse_args(argv)


def _assemble_into(stage, env):
    global DIST, NAS, PC, MANUAL_DIST, DOCS, PROMPTS_DIST
    DIST = stage
    NAS = DIST / "01_NASへ配置"
    PC = DIST / "02_各PCへ配置"
    MANUAL_DIST = DIST / "03_マニュアル"
    DOCS = DIST / "04_管理者向け資料"
    PROMPTS_DIST = DOCS / "AIプロンプト"

    binary = ROOT / "build" / "portable" / "KY安全管理.exe"
    if not binary.is_file():
        raise FileNotFoundError("Build EXE first")
    if not PROMPTS_SRC.is_dir():
        raise FileNotFoundError("Gemini prompt templates not found")
    create_site_structure(NAS / "001_芝原改良工事", "001", "芝原改良工事")
    # The template has no marker because its site ID/name are assigned after it is copied.
    create_site_structure(NAS / "template_project")
    PC.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, PC / binary.name)
    install_pricing_config(PC)
    # Reference copy of the prompts sent to Vertex AI, for admin review (EXE already embeds these).
    if PROMPTS_DIST.exists():
        shutil.rmtree(PROMPTS_DIST)
    shutil.copytree(PROMPTS_SRC, PROMPTS_DIST)
    # User manual (PDF only) shipped beside the other distribution folders.
    manual = MANUAL_SRC / "現場KYアシスト_利用マニュアル.pdf"
    if not manual.is_file():
        raise FileNotFoundError("User manual PDF not found in 利用マニュアル")
    MANUAL_DIST.mkdir(parents=True, exist_ok=True)
    for stale in MANUAL_DIST.glob("現場KYアシスト_利用マニュアル.html"):
        stale.unlink()
    shutil.copy2(manual, MANUAL_DIST / manual.name)
    # Preserve per-site configuration on subsequent builds.
    if not (PC / "config.json").exists():
        write(PC / "config.json", json.dumps(default_config(), ensure_ascii=False, indent=2))
    write_secrets_env(PC, env)
    write(PC / "README.txt", """
【KY安全管理 使用方法】
1. この「02_各PCへ配置」内のファイルを各PCのローカルディスクの任意のフォルダへコピーします。
2. 「KY安全管理.exe」をダブルクリックします。専用のアプリウィンドウが開きます。初回は数十秒かかることがあります。
3. 写真を選び、通常どおりKY分析を行います。保存された履歴は同じ現場のPCで共有されます。
4. PDF保存ではNASに保存すると同時に、このPCへダウンロードします。
5. 使用後はウィンドウ右上の「×」で閉じてください。ウィンドウを閉じるとアプリ本体も終了します。
APIキーは設定済みです。通常、設定変更は不要です。フォルダは社内のみで扱ってください。
共有フォルダに接続できない場合は、社内ネットワークおよびNASへの接続を確認してください。
動作環境：Windows 10/11 64bit、Microsoft Edge。Python・Node.jsの追加インストールは不要です。
""")
    write(NAS / "README_NAS.txt", """
【NAS管理者向け】
01_NASへ配置内の各現場フォルダ（001_芝原改良工事等）を次のフォルダの直下へ配置します。
例：I:\\マイドライブ\\KY安全管理
NASはデータ保管だけを担当します。EXE、secrets.env、APIキー、ログは置きません。
利用者には各工事フォルダ直下で一覧表示・読み取り・作成・書き込み・名前変更・削除の権限が必要です。
新しい現場はtemplate_projectをコピーして「002_○○工事」等へ改名します。
各PCのconfig.jsonのproject_id、project_name、data_rootをその現場に合わせ、アプリを再起動します。
project_idは途中変更しないでください。違うIDの履歴は混在防止のため表示されません。
現場削除は全員のアプリを終了し、バックアップと保存期間を確認して管理者が行ってください。
バックアップ対象は工事フォルダ全体（export/images/records/reports/usage、.ky_site.jsonと削除印）です。
NAS交換時は全員終了→フォルダ全体コピー→権限再設定→各PCのdata_root変更→履歴・写真・PDF確認。
既存現場へ空テンプレートを上書きする更新は行わないでください。
同じフォルダ内の一時ファイルから正式ファイルへのrenameで公開します。SMB/NASの永続化保証は機種・設定に依存します。
切断で保存結果が不明になった場合は、復旧後に履歴を検索してから再保存してください。
""")
    write(DOCS / "導入手順.txt", """
【初回導入】
1. 01_NASへ配置内の各現場フォルダをNASの保存先フォルダ直下へコピーし、共有名と権限を設定します。
2. 02_各PCへ配置のconfig.jsonを実際のUNCパスに合わせます。APIキーはsecrets.envに設定済みです。
   初期値：I:\\マイドライブ\\KY安全管理\\001_芝原改良工事
   data_rootにはdataフォルダではなく、工事フォルダそのものを指定します。
   NAS名・共有名・現場フォルダが異なる場合は配布前に変更が必要です。
3. このPC用フォルダ（EXE、config.json、secrets.env、settings、README.txt）を各PCへコピーします。
4. EXEをダブルクリック。写真→分析→履歴→PDF保存→別PCで同じ履歴・写真・PDFを確認します。
5. 両PCから同時に保存し、履歴が2件増えることを確認します。実NASでこの受入確認を行ってください。
6. ウィンドウ右上の「×」で終了します。同一PCで再度EXEを起動すると、既存のアプリウィンドウが前面に表示されます。
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
   project_id：002など一意のID、project_name：工事名、data_root：工事フォルダそのものの絶対UNCパス。
   data_rootの末尾にdataを付けません。既存のdata方式の設定は自動変更・移行しません。
   JSON内のバックスラッシュは2個ずつ記載します。APIキーはconfig.jsonへ書きません。
3. 同じ現場を使う全PCへ、同じ3項目のconfig.jsonを配布します。EXEは全現場共通です。
4. EXE起動後、現場名と履歴を確認します。設定変更時はアプリを終了して再起動します。
フォルダ権限も現場別に管理してください。IDによる表示分離はNASのアクセス権限の代わりではありません。
""")
    write(DOCS / "アップデート手順.txt", """
【更新】
1. 全PCでアプリウィンドウ右上の「×」で終了します。NASの現場データをバックアップします。
2. 各PCのconfig.json・secrets.env・settingsを保持し、KY安全管理.exeだけを新しいものに差し替えます。
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
    write(DOCS / "AIプロンプト" / "README.txt", """
【AIプロンプトについて】
このフォルダはKY安全管理.exeがVertex AI（Gemini Flash）へ送信するプロンプトの参考コピーです。
kiken_yochi_system.jinja2：分析ルール・出力形式を定めるシステムプロンプト。
kiken_yochi_user.jinja2：画像分析時に付加するユーザープロンプト。
実際にアプリが使用するのはEXE内に組み込まれた版です。このフォルダを編集してもアプリの動作は変わりません。
プロンプトの変更が必要な場合は開発担当者へ連絡し、再ビルドを依頼してください。
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
EXE・config.json・secrets.env・settingsフォルダをローカルPCの同じ配布フォルダへ置きます。
既に起動中なら、既存のアプリウィンドウが前面に表示されます。
終了はウィンドウ右上の「×」です。処理中に閉じた場合は、サーバーが進行中の処理を完了させてから終了します。
【NAS移設】
全データを移行し、各PCのdata_rootのみ変更します。project_idは維持します。
【API接続】
インターネット・会社のプロキシ・APIの利用上限を管理者が確認します。
secrets.envを画面共有・メール・公開リポジトリへ掲載しないでください。
""")
    write(DOCS / "作業報告.txt", (ROOT / "NAS_DISTRIBUTION_REPORT.md").read_text(encoding="utf-8"))
    print("Distribution assembled; real Vertex AI API key configured (value hidden)")
    print("AI prompt files copied:", len(list(PROMPTS_DIST.glob('*.jinja2'))))
    print("PC package files:", len(list(PC.iterdir())))
    print("PC package MiB:", round(sum(p.stat().st_size for p in PC.rglob('*') if p.is_file()) / 1024**2, 2))


def assemble_distribution(output, secrets_source=COPY_ENV):
    """Build in a temporary sibling and publish only after full success."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Distribution output already exists: {output}")

    # Validate credentials before creating output. Deliberately do not consult
    # .env, existing secrets.env files, or process environment variables.
    env = load_distribution_secrets(secrets_source)
    stage = output.parent / f".{output.name}.assembling-{uuid.uuid4().hex}"
    try:
        _assemble_into(stage, env)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise FileExistsError(f"Distribution output already exists: {output}")
        stage.replace(output)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return output


def main(argv=None):
    args = parse_args(argv)
    try:
        output = assemble_distribution(args.distribution_output)
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
        raise SystemExit(f"Distribution package was not created: {exc}") from None
    print("Distribution candidate created:", output)


if __name__ == "__main__":
    main()
