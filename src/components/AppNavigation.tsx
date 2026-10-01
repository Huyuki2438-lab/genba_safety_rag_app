export type AppPage = "create" | "history" | "settings";

const TABS: { page: AppPage; label: string }[] = [
  { page: "create", label: "KY作成" },
  { page: "history", label: "履歴" },
  { page: "settings", label: "設定" }
];

type AppNavigationProps = {
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
};

export function AppNavigation({ activePage, onNavigate }: AppNavigationProps) {
  return (
    <nav className="app-navigation" aria-label="メインメニュー">
      {TABS.map(({ page, label }) => (
        <button
          key={page}
          type="button"
          className={`nav-button${page === activePage ? " is-active" : ""}`}
          aria-current={page === activePage ? "page" : undefined}
          onClick={() => onNavigate(page)}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}
