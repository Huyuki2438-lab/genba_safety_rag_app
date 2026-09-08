export function Header() {
  return (
    <header className="app-header">
      <div className="app-header__inner">
        <h1 className="app-header__title">現場安全 危険分析</h1>
        <p className="app-header__subtitle">画像を選び、危険分析を開始すると結果が表示されます。</p>
        <button type="button" onClick={async () => {
          if (!window.confirm("アプリを終了しますか？ 処理中の場合は完了を待ってください。")) return;
          try {
            const r = await fetch("/api/v1/shutdown", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
            if (!r.ok) throw new Error();
            document.body.innerHTML = "<p>KY安全管理を終了しました。このタブを閉じてください。</p>";
          } catch { window.alert("終了できませんでした。起動中のアプリを確認してください。"); }
        }}>アプリを終了</button>
      </div>
    </header>
  );
}
