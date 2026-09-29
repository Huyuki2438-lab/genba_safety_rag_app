import { useState } from "react";
import {
  browseForFolder,
  connectNetworkCredentials,
  requestAppRestart,
  saveDataRoot,
  validateDataRoot,
  type CheckResult
} from "../lib/storageSetupApi";

type StorageSetupPanelProps = {
  mode: "initial" | "change";
  initialDataRoot?: string | null;
  initialProjectId?: string | null;
  initialProjectName?: string | null;
  projectIdLocked?: boolean;
  onCancel?: () => void;
};

export function StorageSetupPanel({
  mode,
  initialDataRoot,
  initialProjectId,
  initialProjectName,
  projectIdLocked = false,
  onCancel
}: StorageSetupPanelProps) {
  const [path, setPath] = useState(initialDataRoot ?? "");
  const [projectId, setProjectId] = useState(initialProjectId ?? "");
  const [projectName, setProjectName] = useState(initialProjectName ?? "");
  const [isBrowsing, setIsBrowsing] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [checkResult, setCheckResult] = useState<CheckResult | null>(null);
  const [browseUnavailable, setBrowseUnavailable] = useState(false);
  const [saved, setSaved] = useState(false);
  const [migrationAcked, setMigrationAcked] = useState(false);
  const [detectedFromStorage, setDetectedFromStorage] = useState(false);
  const [showCredentials, setShowCredentials] = useState(false);
  const [nasUsername, setNasUsername] = useState("");
  const [nasPassword, setNasPassword] = useState("");
  const [isConnectingCreds, setIsConnectingCreds] = useState(false);
  const [credentialResult, setCredentialResult] = useState<CheckResult | null>(null);

  const busy = isBrowsing || isChecking || isSaving || isConnectingCreds;
  const previousDataRoot = (initialDataRoot ?? "").trim();
  const isChangingDataRoot =
    mode === "change" && previousDataRoot !== "" && path.trim() !== "" && path.trim() !== previousDataRoot;
  const isNetworkPath = path.trim().startsWith("\\\\") || path.trim().startsWith("//");
  const projectIdIsLocked = projectIdLocked || detectedFromStorage;
  const projectIdMissing = !projectIdIsLocked && !projectId.trim();
  const canSave =
    !busy && path.trim() !== "" && !projectIdMissing && projectName.trim() !== "" && (!isChangingDataRoot || migrationAcked);

  const applyCheckResult = (result: CheckResult): void => {
    setCheckResult(result);
    if (!projectIdLocked && result.detectedProjectId) {
      setProjectId(result.detectedProjectId);
      setProjectName(result.detectedProjectName || projectName);
      setDetectedFromStorage(true);
    } else {
      setDetectedFromStorage(false);
    }
  };

  const handleBrowse = async (): Promise<void> => {
    setIsBrowsing(true);
    setCheckResult(null);
    try {
      const result = await browseForFolder();
      if (!result.available) {
        setBrowseUnavailable(true);
      } else if (result.path) {
        setPath(result.path);
        setMigrationAcked(false);
        setDetectedFromStorage(false);
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
      applyCheckResult(await validateDataRoot(path));
    } catch (error) {
      setCheckResult({ ok: false, message: error instanceof Error ? error.message : "確認に失敗しました。" });
    } finally {
      setIsChecking(false);
    }
  };

  const handleConnectCredentials = async (): Promise<void> => {
    setIsConnectingCreds(true);
    setCredentialResult(null);
    try {
      setCredentialResult(await connectNetworkCredentials(path, nasUsername, nasPassword));
    } catch (error) {
      setCredentialResult({ ok: false, message: error instanceof Error ? error.message : "接続情報の設定に失敗しました。" });
    } finally {
      setIsConnectingCreds(false);
      setNasPassword("");
    }
  };

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    setCheckResult(null);
    try {
      const result = await saveDataRoot(path, projectId, projectName);
      applyCheckResult(result);
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
        <p>設定を保存しました。設定を反映するため、アプリを再起動しています。</p>
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
        現場名（工事名）
        <input
          type="text"
          value={projectName}
          onChange={(event) => {
            setProjectName(event.target.value);
            setCheckResult(null);
          }}
          placeholder="例：芝原改良工事"
          disabled={busy || detectedFromStorage}
        />
      </label>

      <label className="setup-wizard__label">
        現場ID（project_id）
        <input
          type="text"
          value={projectId}
          onChange={(event) => {
            setProjectId(event.target.value);
            setCheckResult(null);
          }}
          placeholder="例：001"
          disabled={busy || projectIdIsLocked}
        />
      </label>
      {projectIdLocked && (
        <p className="setup-wizard__hint">
          現場IDは一度設定すると変更できません（変更すると、これまでの履歴が別の現場のものとして扱われ表示されなくなります）。
        </p>
      )}
      {!projectIdLocked && detectedFromStorage && (
        <p className="setup-wizard__hint">
          この保存先には既に他のパソコンが設定した現場情報が見つかったため、自動的に入力しました。
        </p>
      )}

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
              setMigrationAcked(false);
              setDetectedFromStorage(false);
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

      {isNetworkPath && (
        <div className="setup-wizard__credentials">
          <button
            type="button"
            className="compact"
            onClick={() => setShowCredentials((value) => !value)}
            disabled={busy}
          >
            {showCredentials ? "資格情報の入力を閉じる" : "NASに別のユーザー名・パスワードが必要な場合"}
          </button>
          {showCredentials && (
            <div className="setup-wizard__credentials-form">
              <p className="setup-wizard__hint">
                このパソコンのWindowsログオンとは別の資格情報でNASに接続する必要がある場合に入力してください。
                パスワードは保存先の接続にのみ使用し、Windowsの資格情報マネージャーに委ねます（本アプリ内には保存しません）。
              </p>
              <label className="setup-wizard__label">
                ユーザー名
                <input
                  type="text"
                  value={nasUsername}
                  onChange={(event) => setNasUsername(event.target.value)}
                  placeholder="例：DOMAIN\\ユーザー名"
                  disabled={busy}
                  autoComplete="username"
                />
              </label>
              <label className="setup-wizard__label">
                パスワード
                <input
                  type="password"
                  value={nasPassword}
                  onChange={(event) => setNasPassword(event.target.value)}
                  disabled={busy}
                  autoComplete="current-password"
                />
              </label>
              <div className="page-actions">
                <button
                  type="button"
                  className="compact"
                  onClick={() => void handleConnectCredentials()}
                  disabled={busy || !nasUsername.trim() || !nasPassword}
                >
                  {isConnectingCreds ? "接続中..." : "この資格情報で接続する"}
                </button>
              </div>
              {credentialResult && (
                <p
                  className={`setup-wizard__status ${credentialResult.ok ? "setup-wizard__status--ok" : "setup-wizard__status--ng"}`}
                  role="alert"
                >
                  {credentialResult.message}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {isChangingDataRoot && (
        <div className="setup-wizard__status setup-wizard__status--ng" role="alert">
          <p>
            ⚠ 保存先を変更しますが、以前の保存先（{previousDataRoot}）にあるデータは自動的にはコピーされません。
            過去の履歴・写真を引き続き使う場合は、保存する前に管理者が手動でファイルをコピーしてください。
          </p>
          <label className="setup-wizard__checkbox">
            <input
              type="checkbox"
              checked={migrationAcked}
              onChange={(event) => setMigrationAcked(event.target.checked)}
              disabled={busy}
            />
            上記を理解し、保存先を変更します
          </label>
        </div>
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
        <button type="button" className="nav-button is-active" onClick={() => void handleSave()} disabled={!canSave}>
          {isSaving ? "保存中..." : "この内容で保存する"}
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
