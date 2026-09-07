/**
 * HTML文字列から危険なコードパターンを正規表現で除去する簡易サニタイザー。
 *
 * 【除去対象】
 * - <script> タグ（インラインスクリプト）
 * - onXxx="..." / onXxx='...' 形式のインラインイベントハンドラ
 * - href="javascript:..." / src="javascript:..." 形式のJSプロトコルURL
 *
 * 【現状の限界・既知の非対応パターン】
 * 正規表現ベースのため、以下のような変種には対応していない:
 * - クォートなしのイベントハンドラ（例: onerror=alert(1)）
 * - <style> タグ経由のCSSインジェクション（例: background:url(javascript:...)）
 * - <iframe>, <object>, <embed> などの埋め込みタグ
 * - data: URL を使ったコンテンツインジェクション
 *
 * 【推奨改善策】
 * AIの出力を dangerouslySetInnerHTML に渡すユースケースでは、
 * より堅牢なサニタイズライブラリの導入を強く推奨する:
 *
 *   npm install dompurify
 *   npm install --save-dev @types/dompurify
 *
 * 導入後は以下のように置き換え:
 *   import DOMPurify from "dompurify";
 *   export const sanitizeHtml = (html: string): string => DOMPurify.sanitize(html);
 *
 * 現状は依存ライブラリを増やさない方針のため正規表現実装を維持しているが、
 * セキュリティ要件が高まった際は早期に移行すること。
 */
const SCRIPT_TAG_PATTERN = /<script[\s\S]*?>[\s\S]*?<\/script>/gi;
const INLINE_HANDLER_DQ_PATTERN = /\son\w+="[^"]*"/gi;
const INLINE_HANDLER_SQ_PATTERN = /\son\w+='[^']*'/gi;
const JS_URL_DQ_PATTERN = /\s(href|src)="\s*javascript:[^"]*"/gi;
const JS_URL_SQ_PATTERN = /\s(href|src)='\s*javascript:[^']*'/gi;

export const sanitizeHtml = (html: string): string => {
  return html
    .replace(SCRIPT_TAG_PATTERN, "")
    .replace(INLINE_HANDLER_DQ_PATTERN, "")
    .replace(INLINE_HANDLER_SQ_PATTERN, "")
    .replace(JS_URL_DQ_PATTERN, "")
    .replace(JS_URL_SQ_PATTERN, "");
};
