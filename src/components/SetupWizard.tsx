import { useEffect, useState } from "react";
import { fetchSetupStatus, type SetupStatus } from "../lib/storageSetupApi";
import { StorageSetupPanel } from "./StorageSetupPanel";

export function SetupWizard() {
  const [status, setStatus] = useState<SetupStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchSetupStatus()
      .then((result) => {
        if (!cancelled) setStatus(result);
      })
      .catch(() => {
        if (!cancelled) setStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="app-shell setup-wizard">
      <header className="app-header">
        <div className="app-header__inner">
          <h1 className="app-header__title">現場KYアシスト — 初期設定</h1>
          <p className="app-header__subtitle">初めてこのパソコンで起動しました。データ保存先とプロジェクト情報を設定すると利用を開始できます。</p>
        </div>
      </header>
      <main className="app-main">
        <StorageSetupPanel
          mode="initial"
          initialDataRoot={status?.dataRoot ?? null}
          initialProjectId={status?.projectId ?? null}
          initialProjectName={status?.projectName ?? null}
          initialStorageType={status?.storageType ?? null}
          projectIdLocked={status?.projectIdLocked ?? false}
        />
      </main>
    </div>
  );
}
