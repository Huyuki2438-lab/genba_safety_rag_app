import { Header } from "./Header";

type StorageUnavailableScreenProps = {
  message: string | null;
  onRetry: () => void;
  onChangeStorage: () => void;
};

export function StorageUnavailableScreen({ message, onRetry, onChangeStorage }: StorageUnavailableScreenProps) {
  return (
    <div className="app-shell setup-wizard">
      <Header />
      <main className="app-main">
        <div className="setup-wizard__card" role="alert">
          <h2 className="panel-title">データ保存先に接続できません</h2>
          <p className="setup-wizard__status setup-wizard__status--ng">
            {message ?? "保存先にアクセスできません。ネットワーク接続またはフォルダのアクセス権を確認してください。"}
          </p>
          <div className="page-actions">
            <button type="button" className="nav-button is-active" onClick={onRetry}>
              再試行
            </button>
            <button type="button" className="compact" onClick={onChangeStorage}>
              保存先を変更
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
