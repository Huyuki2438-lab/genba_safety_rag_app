import {
  SETUP_BROWSE_ENDPOINT,
  SETUP_CONNECT_CREDENTIALS_ENDPOINT,
  SETUP_RESTART_ENDPOINT,
  SETUP_SAVE_ENDPOINT,
  SETUP_STATUS_ENDPOINT,
  SETUP_VALIDATE_ENDPOINT
} from "../constants/endpoints";

export type StorageType = "local" | "nas";

export type SetupStatus = {
  configured: boolean;
  dataRoot: string | null;
  storageType: string | null;
  reachable: boolean;
  reachableMessage: string | null;
  projectId: string | null;
  projectName: string | null;
  projectIdLocked: boolean;
};

export type CheckResult = {
  ok: boolean;
  message: string;
  detectedProjectId?: string | null;
  detectedProjectName?: string | null;
};

export const BACKEND_UNREACHABLE_MESSAGE = "アプリ内部の通信に失敗しました。バックエンドの起動状態を確認してください。";

/** バックエンドAPIへ接続できなかった(接続拒否・サーバー停止・ポート不一致など)ことを表す。 */
export class BackendUnreachableError extends Error {
  constructor() {
    super(BACKEND_UNREACHABLE_MESSAGE);
    this.name = "BackendUnreachableError";
  }
}

/** fetchの生の "Failed to fetch" を利用者画面へ出さないため、通信失敗を専用エラーへ変換する。 */
const apiFetch = async (input: string, init?: RequestInit): Promise<Response> => {
  try {
    return await fetch(input, init);
  } catch {
    throw new BackendUnreachableError();
  }
};

const asJson = async <T,>(response: Response): Promise<T> => {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body && (body.detail ?? body.message);
    throw new Error(
      typeof detail === "string" && detail
        ? detail
        : `アプリ内部でエラーが発生しました（HTTP ${response.status}）。アプリを再起動しても直らない場合は管理者へ連絡してください。`
    );
  }
  return response.json() as Promise<T>;
};

export async function fetchSetupStatus(): Promise<SetupStatus> {
  const response = await apiFetch(SETUP_STATUS_ENDPOINT);
  const data = await asJson<{
    configured: boolean;
    data_root: string | null;
    storage_type: string | null;
    reachable: boolean;
    reachable_message: string | null;
    project_id: string | null;
    project_name: string | null;
    project_id_locked: boolean;
  }>(response);
  return {
    configured: data.configured,
    dataRoot: data.data_root,
    storageType: data.storage_type,
    reachable: data.reachable,
    reachableMessage: data.reachable_message,
    projectId: data.project_id,
    projectName: data.project_name,
    projectIdLocked: data.project_id_locked
  };
}

export async function browseForFolder(): Promise<{ path: string | null; available: boolean }> {
  const response = await apiFetch(SETUP_BROWSE_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}"
  });
  return asJson(response);
}

type CheckResponseBody = {
  ok: boolean;
  message: string;
  detected_project_id: string | null;
  detected_project_name: string | null;
};

const toCheckResult = (data: CheckResponseBody): CheckResult => ({
  ok: data.ok,
  message: data.message,
  detectedProjectId: data.detected_project_id,
  detectedProjectName: data.detected_project_name
});

export async function validateDataRoot(path: string): Promise<CheckResult> {
  const response = await apiFetch(SETUP_VALIDATE_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path })
  });
  return toCheckResult(await asJson<CheckResponseBody>(response));
}

export async function saveDataRoot(
  path: string,
  projectId: string,
  projectName: string,
  storageType: StorageType
): Promise<CheckResult> {
  const response = await apiFetch(SETUP_SAVE_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, project_id: projectId, project_name: projectName, storage_type: storageType })
  });
  return toCheckResult(await asJson<CheckResponseBody>(response));
}

export async function connectNetworkCredentials(path: string, username: string, password: string): Promise<CheckResult> {
  const response = await apiFetch(SETUP_CONNECT_CREDENTIALS_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, username, password })
  });
  return toCheckResult(await asJson<CheckResponseBody>(response));
}

export async function requestAppRestart(): Promise<void> {
  await apiFetch(SETUP_RESTART_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}"
  }).catch(() => {});
  await fetch("/api/v1/shutdown", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}"
  }).catch(() => {});
}
