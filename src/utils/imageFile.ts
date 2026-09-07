const DEFAULT_IMAGE_MIME_TYPE = "image/jpeg";

export const getImageMimeType = (file: File): string => {
  const mimeType = file.type?.trim();
  return mimeType.length > 0 ? mimeType : DEFAULT_IMAGE_MIME_TYPE;
};

export const fileToBase64 = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onerror = () => {
      reject(new Error("選択した画像ファイルの読み込みに失敗しました。"));
    };

    reader.onload = () => {
      if (typeof reader.result !== "string") {
        reject(new Error("画像ファイルデータの解析に失敗しました。"));
        return;
      }

      const [, base64] = reader.result.split(",", 2);
      if (!base64) {
        reject(new Error("画像ファイルのBase64変換に失敗しました。"));
        return;
      }

      resolve(base64);
    };

    reader.readAsDataURL(file);
  });
};
