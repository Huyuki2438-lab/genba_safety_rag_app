/** API エンドポイント定数。変更は必ずここだけ行うこと。 */

export const ANALYZE_ENDPOINT = "/api/v1/analyze" as const;
export const HISTORY_ENDPOINT = "/api/v1/history" as const;
export const SETTINGS_ENDPOINT = "/api/v1/settings" as const;
export const PDF_ENDPOINT = "/api/v1/pdf" as const;
export const EXCEL_ENDPOINT = "/api/v1/excel" as const;

export const SETUP_STATUS_ENDPOINT = "/api/v1/setup/status" as const;
export const SETUP_BROWSE_ENDPOINT = "/api/v1/setup/browse" as const;
export const SETUP_VALIDATE_ENDPOINT = "/api/v1/setup/validate" as const;
export const SETUP_SAVE_ENDPOINT = "/api/v1/setup/save" as const;
export const SETUP_RESTART_ENDPOINT = "/api/v1/setup/restart" as const;
