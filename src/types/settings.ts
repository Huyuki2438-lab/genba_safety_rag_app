import type { AiMode } from "./ai";

export type TargetKind = "gemini" | "vertex";

export type TargetSetting = {
  target: AiMode;
  label: string;
  enabled: boolean;
  kind: TargetKind;
  model: string | null;
  missing_keys: string[];
};

export type SettingsResponse = {
  default_target: AiMode | string;
  targets: TargetSetting[];
};
