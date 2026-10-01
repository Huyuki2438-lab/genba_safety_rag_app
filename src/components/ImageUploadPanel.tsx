import { useRef, useState } from "react";
import { ImagePlus, Trash2 } from "lucide-react";

type ImageUploadPanelProps = {
  selectedImage: File | null;
  imagePreviewUrl: string | null;
  onImageChange: (file: File | null) => void;
};

const IMAGE_ACCEPT = "image/png,image/jpeg,image/jpg,image/webp,image/gif,image/bmp,image/svg+xml";

export function ImageUploadPanel({
  selectedImage,
  imagePreviewUrl,
  onImageChange
}: ImageUploadPanelProps) {
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFilePick = (fileList: FileList | null) => {
    const selected = fileList?.[0];
    if (!selected) return;
    if (!selected.type.startsWith("image/")) return;
    onImageChange(selected);
  };

  const openFilePicker = () => fileInputRef.current?.click();

  return (
    <section className="upload-panel">
      <h2 className="panel-title">1. 画像を選択</h2>
      <div
        role="button"
        tabIndex={0}
        aria-label="画像をドラッグ＆ドロップ、またはクリックして選択"
        onClick={openFilePicker}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return;
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            openFilePicker();
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragActive(true);
        }}
        onDragLeave={() => setIsDragActive(false)}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragActive(false);
          handleFilePick(event.dataTransfer.files);
        }}
        className={["upload-dropzone", isDragActive ? "is-drag-active" : ""].join(" ")}
      >
        {imagePreviewUrl ? (
          <div className="upload-dropzone__content">
            <img
              src={imagePreviewUrl}
              alt="アップロード済み画像のプレビュー"
              className="upload-preview"
            />
            <div className="upload-meta">
              <p className="upload-filename" title={selectedImage?.name ?? undefined}>
                {selectedImage?.name}
              </p>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  if (fileInputRef.current) fileInputRef.current.value = "";
                  onImageChange(null);
                }}
                className="upload-clear-button"
              >
                <Trash2 className="size-4" aria-hidden="true" />
                画像を外す
              </button>
            </div>
          </div>
        ) : (
          <div className="upload-dropzone__empty">
            <ImagePlus className="size-8" aria-hidden="true" />
            <p>画像をドラッグ＆ドロップ<br />またはクリックして選択</p>
          </div>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={IMAGE_ACCEPT}
        className="hidden"
        onChange={(event) => {
          handleFilePick(event.target.files);
          event.target.value = "";
        }}
      />
    </section>
  );
}
