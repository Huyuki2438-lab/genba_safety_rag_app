import { AlertTriangle, Loader2 } from "lucide-react";

type AnalysisPanelProps = {
  isAnalyzing: boolean;
  onAnalyze: () => void;
};

export function AnalysisPanel({ isAnalyzing, onAnalyze }: AnalysisPanelProps) {
  return (
    <section className="analyze-panel">
      <h2 className="panel-title">2. 危険分析</h2>
      <p className="panel-description">選択した画像から危険要因・リスク・対策を抽出します。</p>

      <button
        type="button"
        onClick={onAnalyze}
        disabled={isAnalyzing}
        className="analyze-button"
      >
        {isAnalyzing ? (
          <>
            <Loader2 className="size-5 animate-spin" aria-hidden="true" />
            危険分析を実行中...
          </>
        ) : (
          <>
            <AlertTriangle className="size-5" aria-hidden="true" />
            危険分析を開始
          </>
        )}
      </button>
    </section>
  );
}
