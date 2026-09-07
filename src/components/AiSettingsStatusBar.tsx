import { AI_MODE_OPTIONS } from "../constants/aiProviders";
import type { SafetyAnalysisRuntimeConfig } from "../lib/providers/providerRuntime";
import type { AiMode } from "../types/ai";

type AiSettingsStatusBarProps = {
  mode: AiMode;
  onModeChange: (mode: AiMode) => void;
  runtimeConfig: SafetyAnalysisRuntimeConfig;
};

export function AiSettingsStatusBar({
  mode,
  onModeChange,
  runtimeConfig
}: AiSettingsStatusBarProps) {
  return (
    <section className="status-bar" aria-label="AI設定">
      <div className="status-item status-item--mode">
        <p className="status-item__label">実行先</p>
        <div className="mode-switch" role="radiogroup" aria-label="実行先選択">
          {AI_MODE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={mode === option.value}
              onClick={() => onModeChange(option.value)}
              className={["mode-chip", mode === option.value ? "is-selected" : ""].join(" ")}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="status-item">
        {/* 「実行先」はmode-switchパネルの見出しと重複するため「プロバイダー」に変更 */}
        <span className="status-item__label">プロバイダー</span>
        <span className="status-item__value">{runtimeConfig.providerLabel}</span>
      </div>

      <div className="status-item">
        <span className="status-item__label">モデル</span>
        <span className="status-item__value status-item__value--mono">{runtimeConfig.model}</span>
      </div>

      <div className="status-item">
        <span className="status-item__label">設定状態</span>
        <span className="status-item__value">{runtimeConfig.configStatus.statusLabel}</span>
      </div>
    </section>
  );
}
