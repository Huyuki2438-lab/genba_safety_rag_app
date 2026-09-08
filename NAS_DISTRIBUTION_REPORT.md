# KY安全管理 社内配布版 作業報告

作業日：2026年9月8日〜9日。ソース変更・EXEビルド・配布フォルダ生成を実施。実NASへの本番配置は行っていません。NASへは検証用の一意フォルダだけを作成し、試験後に削除しました。

1. 現行構成の調査結果

React 19 / TypeScript / Viteの画面、FastAPIのバックエンド。従来はpywebviewからローカルuvicornを起動し、ウィンドウ終了で停止していました。PyInstaller onedir方式でPythonランタイム、Playwright、Chromium、フロントのdist、テンプレート等を配布していました。

履歴はSQLAlchemyのky_analysis_historyテーブル。列はid、created_at、updated_at、deleted_at、created_by、site_name、work_content、main_risk、image_name、image_mime_type、photo_relative_path、mode、provider_display_label、model、markdown。現在の.envはNAS上のSQLiteと別のphotosを指定しており、複数PCから同じDBを更新する構成でした。旧形式としてanalysis_history.jsonと履歴別フォルダも残っていました。

写真はUUID名で保存していましたが、履歴DBと写真の確定順序、通信断後の写真削除、共有SQLiteへの更新が課題でした。PDFは既存HTML/CSSをPlaywrightで変換してダウンロードする処理で、共有保存やexportはありませんでした。APIキーは.envのGEMINI_A_API_KEY等からバックエンドが取得していました。Gemini/VertexのHTTP URLにキーを付け、外部エラー詳細を表示・ログ出力する経路もありました。

localhostは各PC内部のUI/API通信に使用します。ログはLOCALAPPDATA、従来のPDF用ブラウザは大容量の同梱フォルダでした。ViteとEXEの出力先distが重なっていたため、フロント出力をfrontend_buildへ分離しました。着手時点で既存の未コミット変更がありました。元.envと元履歴・写真は保持し、Gitへの追加・コミット・公開は行っていません。

2. 変更したファイル

- 保存：backend/app/repositories/history_repository.py、services/history_service.py、api/v1/history.py、core/shared_storage.py（新規）。
- 設定・秘密情報：backend/app/core/config.py、core/secrets.py（新規）、core/ai/base.py、core/ai/providers/gemini.py、vertex.py、services/analysis_service.py、api/v1/analysis.py、.gitignore。
- PDF・配信：backend/app/api/v1/pdf.py、schemas/pdf.py、api/ui.py、main.py。
- 画面：src/App.tsx、components/Header.tsx、HistoryView.tsx、ResultTabs.tsx、hooks/useGeminiSafetyAnalysis.ts、lib/analysisHistoryApi.ts、index.css。
- 配布：desktop_app.py、desktop_app.spec、build_exe.ps1、vite.config.ts、requirements.txt、scripts/package_distribution.py（新規）。
- 移行・検証：scripts/migrate_sqlite_history.py、test_shared_storage.py、test_distribution.py、test_real_nas.py（いずれも新規）、既存のimport_legacy_history.py、initialize_postgres.py。
- 資料：DEPLOYMENT.md、BUILD_DESKTOP_APP.md、.env.shared.exampleに旧方式の廃止案内を追加。この報告書とdist/03_管理者向け資料を生成。

3. 主な変更内容

1履歴＝1JSONとし、records/年月/UUID.jsonにschema_version=1、record_id、project_id、created_at、既存の解析情報を保存します。SQLite・DBサーバーは通常実行で使用しません。写真・PDF・ZIPにもUUIDを使用し、PDFはreports/履歴ID/UUID.pdfへ保存して他PCから参照できます。exportは写真・解析JSON・対応PDFのZIPです。

同一フォルダ内の一時ファイルへ書き込み、flush/fsync後に正式名へrenameします。Windowsのrenameで既存ファイルへの上書きを拒否します。履歴は写真の保存後に公開します。削除では元JSONを書き換えず、.deleted印を別保存します。通信断で確定結果が不明な場合に孤立写真が残ることはありますが、確定済み履歴の写真を誤削除しない方式です。

履歴検索は50件ずつのページング、写真の遅延読込、再生成可能なPCメモリーキャッシュを使用します。キャッシュはファイルの更新時刻・サイズで検証し、他PCの追加・削除を検索時に再確認します。各現場のproject_idが異なる履歴は表示しません。NAS権限による現場分離も併用してください。

EXEは1ファイルでランタイムを内包し、既定のブラウザを自動起動します。画面の「アプリを終了」でサーバーを停止し、二重起動時は既存アプリの画面を開きます。UNC・ネットワークドライブ上からのEXE実行は拒否します。NAS切断時に別のローカル保存先へ自動切替することはありません。

4. distの絶対パス

C:\Users\doboku31\Desktop\AI・開発\genba_safety_rag_app\dist

5. NASへコピーするフォルダ

dist\01_NASへ配置\KY安全管理

コピー先：\\landisk-ee6245\disk1\
コピー後：\\landisk-ee6245\disk1\KY安全管理

実環境を確認した結果、landisk-ee6245の既存共有はdisk1であり、KY安全管理という共有名は存在しませんでした。そのため要件書の例へdisk1を加え、フォルダコピーで導入できるconfigにしています。

6. 各PCへコピーするフォルダ

dist\02_各PCへ配置\KY安全管理

各PCのデスクトップ等、ローカルディスクへフォルダごとコピーしてEXEをダブルクリックします。Python・Node.js・DBサーバーのインストールや利用者のコマンド操作は不要です。

7. NAS側の最終構成

```text
KY安全管理/
  001_芝原改良工事/data/
    records/年月/UUID.json
    images/migrated/UUID.<画像拡張子>
    reports/履歴UUID/PDFのUUID.pdf
    export/
  template_project/data/
    records/
    images/
    reports/
    export/
  README_NAS.txt
```

既存の共有SQLiteから履歴1件・写真1件を読み取り専用で移行しました。旧ローカル履歴の本文・写真ハッシュが一致することを確認し、対応PDF1件も保存しました。本文・写真・PDFは原本と照合済みです。元DB・写真・PDFは変更していません。同じSQLite移行を再実行しても履歴が増えないことを確認しました。

8. PC側の最終構成

```text
KY安全管理/
  KY安全管理.exe
  config.json
  secrets.env
  README.txt
```

ログは各PCの%LOCALAPPDATA%\KY安全管理\logs。PDF作成用の一時プロファイル等はPCの一時領域です。配布フォルダに開発環境・ソース・テスト・Chromium本体は含めません。旧dist内容はbuild/previous_distribution_日時へ保全しました。

9. config.jsonの設定

```json
{
  "project_id": "001",
  "project_name": "芝原改良工事",
  "data_root": "\\\\landisk-ee6245\\disk1\\KY安全管理\\001_芝原改良工事\\data"
}
```

EXE横からUTF-8で読み込みます。絶対パスを必須にし、3項目以外を拒否します。変更後はアプリを終了して再起動してください。

10. secrets.env

既存の実Gemini APIキーをGEMINI_API_KEYとして設定済みです。既存のモデル・予備接続設定もPC側だけに保持しています。元キーの変更・削除・失効・再発行は行っていません。元.envとの一致を値を表示せずに検証しました。

キーはHTTPヘッダーで送信し、URLへ含めません。ログは例外種別だけ、画面は日本語の一般的なエラーを返します。既知キーが解析テキスト・履歴・PDFコンテキストへ混入してもマスクする処理を追加しました。distとsecrets.envはGit除外を確認済みです。画面、JSON、PDF、ZIP内容、ログ、配布アセットの検証でキーの混入は検出されませんでした。

11. 新規現場追加

NASのtemplate_projectをコピー・改名し、各PCのconfig.jsonの3項目だけを合わせます。同じEXEを使用します。既存現場のproject_idは変更しないでください。

12. 複数PC同時利用

各PCでローカルEXEを実行し、同じ現場のconfigを使用します。「履歴」の検索で他PCの新しい記録を取得できます。ファイルを共通の1つに追記する処理や共有SQLiteへの更新はありません。

13. アップデート

アプリ終了後、各PCのEXEだけを差し替えます。config.json、secrets.env、NASデータは保持します。新しいNASテンプレートを既存現場へ上書きしないでください。旧schema_version=1の履歴を新EXEで読むことを確認済みです。

14. バックアップ

各現場フォルダ全体をNASの世代バックアップ・別媒体へ保存します。recordsだけでなくimages、reports、export、.deleted印も対象です。整合したコピーを取るときは全PCを終了してください。secrets.envはNASに置かず会社の管理者用保管場所で別管理します。

15. NAS障害時の挙動

接続・権限・容量の問題は日本語のエラーとして返し、保存成功とは表示しません。分析結果の保存失敗時には画面に結果を保持し、復旧後にAIを呼び直さず保存を再試行できます。確定直後の通信断は結果不明となり得るため、再試行前に履歴を確認します。

破損・未対応形式JSONと.uploadingは一覧から除外します。写真やPDFの欠損では履歴本文を残し、該当ファイルの取得を404とします。exportに必要な写真がない場合は失敗を返します。NAS復旧後の検索・保存に再起動は不要です。UNCパス自体を変更する場合はconfigを直して再起動します。

16. テスト結果

- ソース回帰テスト：12件成功。2プロセス同時保存70件、1,000件の検索・ページング、切断/復旧、権限/容量/通信断の模擬障害、同名上書き防止、削除競合、破損・欠損・現場分離、秘密情報マスクを確認。
- 実NAS：\\landisk-ee6245\disk1の一意の試験フォルダで2プロセス同時保存30件、別リポジトリから全件読込。日本語・空白のUNC、UUID付き添付、破損/途中ファイルの除外、フォルダ切断相当/復旧を確認。試験用データは削除済み。
- 実API：配布EXEを2つ起動し、実キーでGeminiに同時2件接続。いずれも解析応答が正常。合成画像による接続試験であり、KYの内容精度の評価ではありません。
- EXE統合：Python/NodeをPATHから除いた隔離コピーで起動、二重起動、同時保存、他インスタンスの写真・PDF閲覧、export、切断・復旧、破損/欠損、画面の履歴再表示、終了/ローカルポート閉鎖を確認。
- PDF：日本語の文字抽出、検証用の1ページPDFと画面操作から生成した既存の5セクション構成のPDFを描画して目視確認。Microsoft Edgeで既存のHTML/CSS方式を継続。
- 移行：既存1件の本文一致、写真・PDFのハッシュ一致、再移行で重複なし。
- ビルド：TypeScript/Vite、PyInstaller成功。ViteのJSサイズ警告は残りますが、ビルドエラーはありません。

最終EXEの再検証結果・容量は末尾の検証記録を参照してください。

17. 配布容量

PC側約52.24MiB。NAS側約0.87MiB（既存履歴・写真・PDFを含む）。配布用Chromium本体を除き、Microsoft Edgeを利用することで容量を抑えています。各PCにPython・Node.jsを追加インストールする必要はありません。PDF処理用の内部ランタイムはEXEに同梱しています。

18. 残る制約と確認範囲

- 対応環境はWindows 10/11 64bitとMicrosoft Edgeです。Edgeの存在と企業ポリシーによる自動実行制限を各配布PCで確認してください。初回起動は一時展開のため数十秒かかる場合があります。
- 実際の別PC2台による試験、Python/Nodeが一度もインストールされていないクリーンOS、物理LAN抜線、NAS電源断・実容量枯渇は未実施です。2つの独立EXE・実SMB試験と模擬障害で代替した範囲を区別しています。
- SMBのキャッシュ・rename・永続化はNAS機種と設定に依存し、電源断まで含むトランザクション保証はありません。保存確定の応答が失われる場合や孤立添付が残る場合があります。
- ブラウザタブを閉じるだけではサーバーは停止しません。「アプリを終了」を使用します。分析やPDF生成中は完了を待ってください。
- 履歴は更新日時・サイズによるメモリーキャッシュを使用します。大量履歴の初回検索速度はNASの応答速度に影響されます。
- APIの利用料金・上限・接続可否は利用中の契約に依存します。キーは社内PC用フォルダに平文で保持する、依頼どおりの構成です。
- 本番NASへのコピーと各PCへの配布は担当者が行います。配布先で最初の写真分析・保存・別PCからの閲覧を確認してください。

参照した公式資料：
- PlaywrightのMicrosoft Edgeチャンネル：https://playwright.dev/python/docs/browsers
- Windowsのファイル移動APIとSMB対応：https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw

最終検証記録（2026年9月9日確定）

最終配布EXEによる統合テスト26チェックがすべて成功しました。テスト用フォルダの再renameがWindowsに拒否されたため、画面の保存再試行は保存APIの503応答を注入して検証しました。データルートの切断相当・復旧、実NASでの同時保存・再接続は別の試験で確認済みです。

保存失敗時にはエラーと分析結果を同時に表示し、成功応答を待って保存完了を確認しました。保存の再試行時にAI呼出しは増えません。最終EXEで移行済みの履歴とPDFを読み込めること、EXE終了とローカルポート閉鎖を確認しました。

検証に使用したEXEと配布EXEのSHA-256は一致しています：
fa5e66ec2f2ef9296bd144fd7fb5aced4009cc5640ab7bc92bdd217d4c67919b

PC用4ファイル合計：54775159 bytes（約52.24MiB / 54.78MB）。
EXE内にPythonランタイムとPDF用内部ランタイムがあり、.env・secrets.env・SQLite DB・Chromium本体が含まれないことをアーカイブ一覧で検証しました。

検証チェック一覧：
- two isolated EXEs start without Python/Node on PATH
- secrets.env enables primary AI target
- duplicate launch exits
- simultaneous saves succeed
- UUID filenames do not collide
- PC B reads PC A history
- shared photo readable
- PDF generated and saved to NAS folder
- PC B reads shared PDF
- export ZIP shared
- corrupt and incomplete JSON skipped
- NAS disconnect reports failure
- NAS reconnect works without restart
- missing photo does not hide history
- missing PDF is a readable error
- history table remains visible with detail open
- history detail and reopen UI
- PDF button downloads saved shared report
- failed save retains result and offers retry
- save retry succeeds without another AI call
- new EXE reads migrated existing history and PDF
- shutdown response
- shutdown response
- both EXE processes exit
- local ports closed
- no secret in logs/history/PDF/export/UI
