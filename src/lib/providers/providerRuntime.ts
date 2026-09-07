import { getAiModeMeta } from "../../constants/aiProviders";
import { SETTINGS_ENDPOINT } from "../../constants/endpoints";
import { getSafetyAnalysisModelForProvider } from "../../constants/safetyModels";
import type { AiMode, AIProviderType } from "../../types/ai";
import type { SettingsResponse, TargetSetting } from "../../types/settings";

type ServerRequiredEnvKey =
  | "GEMINI_A_API_KEY"
  | "GEMINI_A_MODEL"
  | "GEMINI_B_API_KEY"
  | "GEMINI_B_MODEL"
  | "VERTEX_API_KEY"
  | "VERTEX_MODEL"
  | "VERTEX_PROJECT_ID"
  | "VERTEX_LOCATION";

const REQUIRED_SERVER_ENV_KEYS_BY_MODE: Readonly<
  Record<AiMode, readonly ServerRequiredEnvKey[]>
> = {
  gemini_a: ["GEMINI_A_API_KEY", "GEMINI_A_MODEL"],
  gemini_b: ["GEMINI_B_API_KEY", "GEMINI_B_MODEL"],
  vertex: [
    "VERTEX_API_KEY",
    "VERTEX_MODEL",
    "VERTEX_PROJECT_ID",
    "VERTEX_LOCATION"
  ]
};

const MODEL_ENV_KEY_BY_MODE: Readonly<Record<AiMode, ServerRequiredEnvKey>> = {
  gemini_a: "GEMINI_A_MODEL",
  gemini_b: "GEMINI_B_MODEL",
  vertex: "VERTEX_MODEL"
};

const isTargetSetting = (value: unknown): value is TargetSetting => {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<TargetSetting>;
  return (
    typeof candidate.target === "string" &&
    typeof candidate.label === "string" &&
    typeof candidate.enabled === "boolean" &&
    (candidate.kind === "gemini" || candidate.kind === "vertex")
  );
};

const normalizeSettingsResponse = (value: unknown): SettingsResponse | null => {
  if (!value || typeof value !== "object") return null;

  const candidate = value as Partial<SettingsResponse>;
  const rawTargets = Array.isArray(candidate.targets) ? candidate.targets : [];
  const targets = rawTargets
    .filter((target): target is TargetSetting => isTargetSetting(target))
    .map((target) => ({
      ...target,
      model: typeof target.model === "string" ? target.model : null,
      missing_keys: Array.isArray(target.missing_keys)
        ? target.missing_keys
            .filter((key): key is string => typeof key === "string")
            .map((key) => key.trim())
            .filter((key) => key.length > 0)
        : []
    }));

  return {
    default_target:
      typeof candidate.default_target === "string" ? candidate.default_target : "",
    targets
  };
};

const findTargetSetting = (
  mode: AiMode,
  settings: SettingsResponse | null | undefined
): TargetSetting | null => {
  if (!settings) return null;
  return settings.targets.find((target) => target.target === mode) ?? null;
};

const resolveMissingKeys = (
  mode: AiMode,
  targetSetting: TargetSetting | null
): ServerRequiredEnvKey[] => {
  const requiredKeys = [...REQUIRED_SERVER_ENV_KEYS_BY_MODE[mode]];
  if (!targetSetting) return requiredKeys;
  if (targetSetting.enabled) return [];

  if (targetSetting.missing_keys.length > 0) {
    return targetSetting.missing_keys.filter(
      (key): key is ServerRequiredEnvKey =>
        (REQUIRED_SERVER_ENV_KEYS_BY_MODE[mode] as readonly string[]).includes(key)
    );
  }

  const modelEnvKey = MODEL_ENV_KEY_BY_MODE[mode];
  if (targetSetting.model && targetSetting.model.trim().length > 0) {
    return requiredKeys.filter((key) => key !== modelEnvKey);
  }

  return requiredKeys;
};

const toConfigStatusDetail = (isReady: boolean, missingKeys: readonly string[]): string => {
  if (isReady) {
    return "必要な環境変数は設定済みです。";
  }
  return `未設定の環境変数: ${missingKeys.join(", ")}`;
};

const resolveModelForMode = (
  mode: AiMode,
  settings: SettingsResponse | null | undefined
): string => {
  const targetSetting = findTargetSetting(mode, settings);
  if (targetSetting?.model && targetSetting.model.trim().length > 0) {
    return targetSetting.model;
  }

  const modeMeta = getAiModeMeta(mode);
  return getSafetyAnalysisModelForProvider(modeMeta.providerType);
};

export type ProviderConfigStatus = {
  isReady: boolean;
  statusLabel: "利用可能" | "設定不足";
  statusDetail: string;
  missingKeys: ServerRequiredEnvKey[];
};

export type SafetyAnalysisRuntimeConfig = {
  mode: AiMode;
  providerType: AIProviderType;
  providerLabel: string;
  providerDisplayLabel: string;
  modeLabel: string;
  modeDescription: string;
  model: string;
  configStatus: ProviderConfigStatus;
};

export const fetchSettings = async (): Promise<SettingsResponse | null> => {
  try {
    const response = await fetch(SETTINGS_ENDPOINT);
    if (!response.ok) {
      return null;
    }
    const data: unknown = await response.json();
    return normalizeSettingsResponse(data);
  } catch {
    return null;
  }
};

export const getProviderConfigStatus = (
  mode: AiMode,
  settings: SettingsResponse | null | undefined
): ProviderConfigStatus => {
  const targetSetting = findTargetSetting(mode, settings);
  const missingKeys = resolveMissingKeys(mode, targetSetting);
  const isReady = targetSetting?.enabled === true;

  return {
    isReady,
    statusLabel: isReady ? "利用可能" : "設定不足",
    statusDetail: toConfigStatusDetail(isReady, missingKeys),
    missingKeys
  };
};

export const getSafetyAnalysisRuntimeConfig = (
  mode: AiMode,
  settings?: SettingsResponse | null
): SafetyAnalysisRuntimeConfig => {
  const modeMeta = getAiModeMeta(mode);

  return {
    mode,
    providerType: modeMeta.providerType,
    providerLabel: modeMeta.providerLabel,
    providerDisplayLabel: `${modeMeta.providerLabel} (${modeMeta.modeLabel})`,
    modeLabel: modeMeta.modeLabel,
    modeDescription: modeMeta.modeDescription,
    model: resolveModelForMode(mode, settings),
    configStatus: getProviderConfigStatus(mode, settings)
  };
};
