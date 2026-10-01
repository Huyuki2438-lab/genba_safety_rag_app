import { useState } from "react";
import {
  BACKEND_UNREACHABLE_MESSAGE,
  browseForFolder,
  connectNetworkCredentials,
  requestAppRestart,
  saveDataRoot,
  validateDataRoot,
  waitForAppRestart,
  type CheckResult,
  type StorageType
} from "../lib/storageSetupApi";

type StorageSetupPanelProps = {
  mode: "initial" | "change";
  initialDataRoot?: string | null;
  initialProjectId?: string | null;
  initialProjectName?: string | null;
  initialStorageType?: string | null;
  projectIdLocked?: boolean;
};

type FieldErrors = { projectId?: string; projectName?: string; path?: string; storageType?: string };

const PROJECT_ID_FORBIDDEN = /[\\/:*?"<>|\u0000-\u001f]/;

const guessStorageType = (path: string): StorageType => {
  const text = path.trim();
  return text.startsWith("\\\\") || text.startsWith("//") ? "nas" : "local";
};

const validateFields = (projectId: string, projectName: string, path: string, storageType: string): FieldErrors => {
  const errors: FieldErrors = {};
  const id = projectId.trim();
  if (!id) errors.projectId = "プロジェクト番号を入力してください。";
  else if (id.length > 50) errors.projectId = "プロジェクト番号は50文字以内で入力してください。";
  else if (PROJECT_ID_FORBIDDEN.test(id)) errors.projectId = "プロジェクト番号に使えない文字が含まれています（例: 001）。";
  const name = projectName.trim();
  if (!name) errors.projectName = "プロジェクト名を入力してください。";
  else if (name.length > 200) errors.projectName = "プロジェクト名は200文字以内で入力してください。";
  const dir = path.trim();
  if (!dir) errors.path = "データ保存先を入力または選択してください。";
  else if (!/^([a-zA-Z]:[\\/]|\\\\|\/\/)/.test(dir)) {
    errors.path = "絶対パスで指定してください（例: C:\\KY安全管理\\data　または　\\\\NAS\\共有\\data）。";
  }
  if (storageType !== "local" && storageType !== "nas") errors.storageType = "保存先種別を選択してください。";
  return errors;
};

export function StorageSetupPanel({
  mode,
  initialDataRoot,
  initialProjectId,
  initialProjectName,
  initialStorageType,
  projectIdLocked = false
}: StorageSetupPanelProps) {
  const [path, setPath] = useState(initialDataRoot ?? "");
  const [projectId, setProjectId] = useState(initialProjectId ?? "");
  const [projectName, setProjectName] = useState(initialProjectName ?? "");
  const hasInitialStorageType = initialStorageType === "local" || initialStorageType === "nas";
  const [storageType, setStorageType] = useState<StorageType>(
    hasInitialStorageType ? (initialStorageType as StorageType) : guessStorageType(initialDataRoot ?? "")
  );
  // 利用者が種別を明示的に選んだ後は、パス入力に応じた自動切替をしない。
  const [storageTypeTouched, setStorageTypeTouched] = useState(hasInitialStorageType);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [isBrowsing, setIsBrowsing] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [checkResult, setCheckResult] = useState<CheckResult | null>(null);
  const [browseUnavailable, setBrowseUnavailable] = useState(false);
  const [saved, setSaved] = useState(false);
  const [restartTimedOut, setRestartTimedOut] = useState(false);
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
  // 設定画面(change)ではプロジェクト番号も変更できる。初回設定では、保存先に既存の現場情報があればそれを使う。
  const projectIdIsLocked = mode === "initial" && (projectIdLocked || detectedFromStorage);
  const canSave = !busy && (!isChangingDataRoot || migrationAcked);
  const clearFieldError = (key: keyof FieldErrors): void => setFieldErrors((prev) => ({ ...prev, [key]: undefined }));
  const fieldError = (key: keyof FieldErrors) =>
    fieldErrors[key] ? (
      <p className="setup-wizard__status setup-wizard__status--ng" role="alert">
        {fieldErrors[key]}
      </p>
    ) : null;
  const syncStorageTypeWithPath = (value: string): void => {
    if (!storageTypeTouched) setStorageType(guessStorageType(value));
  };

  const applyCheckResult = (result: CheckResult): void => {
    setCheckResult(result);
    if (mode === "initial" && !projectIdLocked && result.detectedProjectId) {
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
        clearFieldError("path");
        syncStorageTypeWithPath(result.path);
        setMigrationAcked(false);
        setDetectedFromStorage(false);
      }
    } catch (error) {
      // 通信失敗は「フォルダ選択が使えない」のではなくバックエンドとの接続不良なので、別メッセージで区別する。
      setCheckResult({ ok: false, message: error instanceof Error ? error.message : BACKEND_UNREACHABLE_MESSAGE });
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
    setCheckResult(null);
    const errors = validateFields(projectId, projectName, path, storageType);
    setFieldErrors(errors);
    if (Object.values(errors).some(Boolean)) return;
    setIsSaving(true);
    try {
      const result = await saveDataRoot(path.trim(), projectId.trim(), projectName.trim(), storageType);
      applyCheckResult(result);
      if (result.ok) {
        setSaved(true);
        void (async () => {
          await requestAppRestart();
          if (await waitForAppRestart()) window.location.reload();
          else setRestartTimedOut(true);
        })();
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
        {restartTimedOut ? (
          <p>自動で再起動されませんでした。このタブを閉じ、KY安全管理.exeを起動し直してください。</p>
        ) : (
          <p>再起動が完了すると、この画面が自動で切り替わります。そのままお待ちください（通常は数秒〜十数秒）。</p>
        )}
      </div>
    );
  }

  return (
    <div className="setup-wizard__card">
      <h2 className="panel-title">{mode === "initial" ? "初回セットアップ" : "プロジェクト・データ保存設定"}</h2>
      <p className="panel-description">
        危険分析の履歴・写真・PDF・Excelを保存する場所を選びます。パソコン内のフォルダ、または社内NASの共有フォルダ（例：{"\\\\NAS\\共有\\現場安全\\データ"}）のどちらも指定できます。空のフォルダでも、必要なフォルダは自動で作成されます。
      </p>
      {mode === "initial" && (
        <p className="setup-wizard__hint">
          「参照...」でフォルダを選び、プロジェクト番号とプロジェクトネームを入力して「設定して開始」を押してください。
          同じ保存先を使う2台目以降のパソコンでは、保存先を選ぶとプロジェクト番号・プロジェクトネームが自動入力されます。
        </p>
      )}

      <label className="setup-wizard__label">
        プロジェクト番号
        <input
          type="text"
          value={projectId}
          onChange={(event) => {
            setProjectId(event.target.value);
            setCheckResult(null);
            clearFieldError("projectId");
          }}
          placeholder="例：001"
          disabled={busy || projectIdIsLocked}
        />
      </label>
      {fieldError("projectId")}
      {mode === "change" && (initialProjectId ?? "").trim() !== "" && projectId.trim() !== (initialProjectId ?? "").trim() && (
        <p className="setup-wizard__hint">
          プロジェクト番号を変更すると、これまでの履歴は別のプロジェクトのものとして扱われ、一覧に表示されなくなります。
        </p>
      )}
      {mode === "initial" && detectedFromStorage && (
        <p className="setup-wizard__hint">
          この保存先には既に他のパソコンが設定した現場情報が見つかったため、自動的に入力しました。
        </p>
      )}

      <label className="setup-wizard__label">
        プロジェクト名
        <input
          type="text"
          value={projectName}
          onChange={(event) => {
            setProjectName(event.target.value);
            setCheckResult(null);
            clearFieldError("projectName");
          }}
          placeholder="例：芝原改良工事"
          disabled={busy || detectedFromStorage}
        />
      </label>
      {fieldError("projectName")}

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
              clearFieldError("path");
              syncStorageTypeWithPath(event.target.value);
            }}
            placeholder="例：C:\KY安全管理\001_芝原改良工事\data　または　\\NAS\共有\KY安全管理\data"
            disabled={busy}
          />
          <button type="button" className="compact" onClick={() => void handleBrowse()} disabled={busy}>
            {isBrowsing ? "選択中..." : "参照..."}
          </button>
        </div>
      </label>
      {fieldError("path")}

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

      <label className="setup-wizard__label">
        保存先種別
        <select
          value={storageType}
          onChange={(event) => {
            setStorageType(event.target.value as StorageType);
            setStorageTypeTouched(true);
            clearFieldError("storageType");
          }}
          disabled={busy}
        >
          <option value="local">ローカル（このPC内・外付けドライブ等）</option>
          <option value="nas">社内NAS（共有フォルダ）</option>
        </select>
      </label>
      {fieldError("storageType")}

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
          {isSaving ? "再起動中..." : mode === "initial" ? "設定して開始" : "設定を保存して再起動"}
        </button>
      </div>
    </div>
  );
}
