import { AppNavigation, type AppPage } from "./AppNavigation";

type HeaderProps = {
  activePage?: AppPage;
  onNavigate?: (page: AppPage) => void;
};

export function Header({ activePage, onNavigate }: HeaderProps) {
  return (
    <header className="app-header">
      <div className="app-header__inner">
        <h1 className="app-header__title">現場KYアシスト</h1>
        {activePage && onNavigate && (
          <AppNavigation activePage={activePage} onNavigate={onNavigate} />
        )}
      </div>
    </header>
  );
}
