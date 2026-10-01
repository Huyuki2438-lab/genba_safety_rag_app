import type { ReactNode } from "react";

type DevicePreviewFrameProps = {
  imagePreviewUrl: string | null;
  toolbar: ReactNode;
  children: ReactNode;
};

export function DevicePreviewFrame({
  imagePreviewUrl,
  toolbar,
  children
}: DevicePreviewFrameProps) {
  return (
    <section className="result-frame">
      <div className="result-frame__header">
        <h2 className="panel-title">4. 分析結果</h2>
        {toolbar}
      </div>

      <div className="preview-surface is-pc">
        {imagePreviewUrl ? (
          <img
            src={imagePreviewUrl}
            alt="分析対象画像のプレビュー"
            className="preview-surface__image"
          />
        ) : (
          <div className="preview-surface__empty" aria-hidden="true" />
        )}
      </div>

      <div className="report-surface is-pc">{children}</div>
    </section>
  );
}
