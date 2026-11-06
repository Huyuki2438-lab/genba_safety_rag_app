export type AppPage = "create" | "history" | "usage" | "settings";

const TABS: { page: AppPage; label: string }[] = [
  { page: "create", label: "KY作成" },
  { page: "history", label: "履歴" },
  { page: "settings", label: "設定" },
  { page: "usage", label: "利用料金管理" }
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
          className={`nav-button${page === "usage" ? " nav-button--usage" : ""}${page === activePage ? " is-active" : ""}`}
          aria-current={page === activePage ? "page" : undefined}
          onClick={() => onNavigate(page)}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}
