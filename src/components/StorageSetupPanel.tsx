import { useState } from "react";
import {
  browseForFolder,
  requestAppRestart,
  saveDataRoot,
  validateDataRoot,
  type CheckResult
} from "../lib/storageSetupApi";

type StorageSetupPanelProps = {
  mode: "initial" | "change";
  initialDataRoot?: string | null;
  onCancel?: () => void;
};

export function StorageSetupPanel({ mode, initialDataRoot, onCancel }: StorageSetupPanelProps) {
  const [path, setPath] = useState(initialDataRoot ?? "");
  const [isBrowsing, setIsBrowsing] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [checkResult, setCheckResult] = useState<CheckResult | null>(null);
  const [browseUnavailable, setBrowseUnavailable] = useState(false);
  const [saved, setSaved] = useState(false);

  const busy = isBrowsing || isChecking || isSaving;

  const handleBrowse = async (): Promise<void> => {
    setIsBrowsing(true);
    setCheckResult(null);
    try {
      const result = await browseForFolder();
      if (!result.available) {
        setBrowseUnavailable(true);
      } else if (result.path) {
        setPath(result.path);
      }
    } catch {
      setBrowseUnavailable(true);
    } finally {
      setIsBrowsing(false);
    }
  };

  const handleValidate = async (): Promise<void> => {
    setIsChecking(true);
    setCheckResult(null);
    try {
      setCheckResult(await validateDataRoot(path));
    } catch (error) {
      setCheckResult({ ok: false, message: error instanceof Error ? error.message : "確認に失敗しました。" });
    } finally {
      setIsChecking(false);
    }
  };

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    setCheckResult(null);
    try {
      const result = await saveDataRoot(path);
      setCheckResult(result);
      if (result.ok) {
        setSaved(true);
        void requestAppRestart();
      }
    } catch (error) {
      setCheckResult({ ok: false, message: error instanceof Error ? error.message : "保存に失敗しました。" });
    } finally {
      setIsSaving(false);
    }
  };

  if (saved) {
    return (
      <div className="setup-wizard__card" role="status">
        <h2 className="panel-title">設定が完了しました</h2>
        <p>データ保存先を設定しました。設定を反映するため、アプリを再起動しています。</p>
        <p>まもなく新しいウィンドウが自動的に開きます。開いたら、この画面は閉じてください。</p>
      </div>
    );
  }

  return (
    <div className="setup-wizard__card">
      <h2 className="panel-title">{mode === "initial" ? "データ保存先の初期設定" : "データ保存先の設定"}</h2>
      <p className="panel-description">
        危険分析の履歴・写真・PDF・Excelを保存する場所を選びます。パソコン内のフォルダ、または社内NASの共有フォルダ（例：{"\\\\NAS\\共有\\現場安全\\データ"}）のどちらも指定できます。
      </p>

      <label className="setup-wizard__label">
        データ保存先
        <div className="setup-wizard__path-row">
          <input
            type="text"
            value={path}
            onChange={(event) => {
              setPath(event.target.value);
              setCheckResult(null);
              setSaved(false);
            }}
            placeholder="例：C:\\KYデータ　または　\\\\NAS\\共有\\現場安全\\データ"
            disabled={busy}
          />
          <button type="button" className="compact" onClick={() => void handleBrowse()} disabled={busy}>
            {isBrowsing ? "選択中..." : "参照..."}
          </button>
        </div>
      </label>

      {browseUnavailable && (
        <p className="setup-wizard__hint">
          このパソコンではフォルダ選択画面を使用できません。上の欄に保存先のパスを直接入力してください。
        </p>
      )}

      {checkResult && (
        <p className={`setup-wizard__status ${checkResult.ok ? "setup-wizard__status--ok" : "setup-wizard__status--ng"}`} role="alert">
          {checkResult.message}
        </p>
      )}

      <div className="page-actions">
        <button type="button" className="compact" onClick={() => void handleValidate()} disabled={busy || !path.trim()}>
          {isChecking ? "確認中..." : "接続を確認"}
        </button>
        <button type="button" className="nav-button is-active" onClick={() => void handleSave()} disabled={busy || !path.trim()}>
          {isSaving ? "保存中..." : "この保存先を設定する"}
        </button>
        {mode === "change" && onCancel && (
          <button type="button" className="compact" onClick={onCancel} disabled={busy}>
            戻る
          </button>
        )}
      </div>
    </div>
  );
}
