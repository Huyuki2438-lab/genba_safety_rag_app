import {
  SETUP_BROWSE_ENDPOINT,
  SETUP_CONNECT_CREDENTIALS_ENDPOINT,
  SETUP_RESTART_ENDPOINT,
  SETUP_SAVE_ENDPOINT,
  SETUP_STATUS_ENDPOINT,
  SETUP_VALIDATE_ENDPOINT
} from "../constants/endpoints";

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

const asJson = async <T,>(response: Response): Promise<T> => {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error((body && (body.detail ?? body.message)) || "通信に失敗しました。");
  }
  return response.json() as Promise<T>;
};

export async function fetchSetupStatus(): Promise<SetupStatus> {
  const response = await fetch(SETUP_STATUS_ENDPOINT);
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
  const response = await fetch(SETUP_BROWSE_ENDPOINT, {
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
  const response = await fetch(SETUP_VALIDATE_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path })
  });
  return toCheckResult(await asJson<CheckResponseBody>(response));
}

export async function saveDataRoot(path: string, projectId: string, projectName: string): Promise<CheckResult> {
  const response = await fetch(SETUP_SAVE_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, project_id: projectId, project_name: projectName })
  });
  return toCheckResult(await asJson<CheckResponseBody>(response));
}

export async function connectNetworkCredentials(path: string, username: string, password: string): Promise<CheckResult> {
  const response = await fetch(SETUP_CONNECT_CREDENTIALS_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, username, password })
  });
  return toCheckResult(await asJson<CheckResponseBody>(response));
}

export async function requestAppRestart(): Promise<void> {
  await fetch(SETUP_RESTART_ENDPOINT, {
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
