const UNKNOWN_ERROR_MESSAGE = "不明なエラー";

export const readEnvValue = (key: keyof ImportMetaEnv): string => {
  const value = import.meta.env[key];
  return typeof value === "string" ? value.trim() : "";
};

export const getErrorMessage = (error: unknown): string => {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }

  if (typeof error === "string" && error.trim().length > 0) {
    return error;
  }

  return UNKNOWN_ERROR_MESSAGE;
};
