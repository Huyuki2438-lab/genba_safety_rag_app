import { StorageSetupPanel } from "./StorageSetupPanel";

export function SetupWizard() {
  return (
    <div className="app-shell setup-wizard">
      <header className="app-header">
        <div className="app-header__inner">
          <h1 className="app-header__title">現場安全 危険分析 — 初期設定</h1>
          <p className="app-header__subtitle">初めてこのパソコンで起動しました。データ保存先を設定してください。</p>
        </div>
      </header>
      <main className="app-main">
        <StorageSetupPanel mode="initial" />
      </main>
    </div>
  );
}
