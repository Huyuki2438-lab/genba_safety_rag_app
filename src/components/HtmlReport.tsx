type HtmlReportProps = {
  html: string;
};

/**
 * サニタイズ済みのHTML文字列をそのまま描画するコンポーネント。
 *
 * 【入力の構造について】
 * `html` は renderMarkdownToHtml() の戻り値であり、内部で MarkdownReport を
 * renderToStaticMarkup() したものが渡される。
 * MarkdownReport は最外周に <div class="analysis-markdown"> を持つため、
 * このコンポーネントが生成する DOM は以下のような二重構造になる:
 *
 *   <div>                          ← HtmlReport のラッパー div
 *     <div class="analysis-markdown">  ← renderMarkdownToHtml() が付与
 *       ...Markdownの内容...
 *     </div>
 *   </div>
 *
 * 外側の div はスタイル上ニュートラルな存在であり、
 * CSS は .analysis-markdown に対して適用されるため実害はない。
 * ただし将来的に外側 div が不要であれば、renderMarkdownToHtml() が返す
 * HTML文字列の構造を見直すことを検討すること。
 *
 * 【セキュリティ】
 * `html` は sanitizeHtml() を通過しているが、現状の実装は正規表現ベースの
 * 簡易サニタイズにとどまる。より堅牢にするには DOMPurify 等の導入を推奨。
 * （詳細は src/utils/sanitizeHtml.ts のコメントを参照）
 */
export function HtmlReport({ html }: HtmlReportProps) {
  if (!html.trim()) return null;

  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
