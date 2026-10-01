import { useEffect, useState } from "react";
import { fetchSetupStatus, type SetupStatus } from "../lib/storageSetupApi";
import { StorageSetupPanel } from "./StorageSetupPanel";

export function SettingsView() {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchSetupStatus()
      .then((result) => {
        if (!cancelled) setStatus(result);
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
        <p className="panel-description">現在のデータ保存先・現場名を確認・変更できます。</p>
        <p>
          現在のデータ保存先：<strong>{loaded ? status?.dataRoot ?? "未設定" : "読み込み中..."}</strong>
        </p>
      </div>

      {loaded && (
        <StorageSetupPanel
          mode="change"
          initialDataRoot={status?.dataRoot ?? null}
          initialProjectId={status?.projectId ?? null}
          initialProjectName={status?.projectName ?? null}
          initialStorageType={status?.storageType ?? null}
        />
      )}
    </div>
  );
}
