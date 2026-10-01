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
    <div className="settings-page">
      <section className="settings-card">
        <div className="settings-card__summary">
          <h2>設定</h2>
          <p className="panel-description">現在の保存先とプロジェクト情報を確認・変更できます。</p>
          <p className="settings-card__current-path">
            現在の保存先：<strong>{loaded ? status?.dataRoot ?? "未設定" : "読み込み中..."}</strong>
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
      </section>
    </div>
  );
}
