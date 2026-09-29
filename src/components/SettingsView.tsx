import { useEffect, useState } from "react";
import { fetchSetupStatus } from "../lib/storageSetupApi";
import { StorageSetupPanel } from "./StorageSetupPanel";

type SettingsViewProps = {
  onBack: () => void;
};

export function SettingsView({ onBack }: SettingsViewProps) {
  const [currentDataRoot, setCurrentDataRoot] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchSetupStatus()
      .then((status) => {
        if (!cancelled) setCurrentDataRoot(status.dataRoot);
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="history-page">
      <div className="history-filters">
        <h2>設定</h2>
        <p className="panel-description">現在のデータ保存先を確認・変更できます。</p>
        <p>
          現在のデータ保存先：<strong>{loaded ? currentDataRoot ?? "未設定" : "読み込み中..."}</strong>
        </p>
      </div>

      {loaded && <StorageSetupPanel mode="change" initialDataRoot={currentDataRoot} onCancel={onBack} />}
    </div>
  );
}
