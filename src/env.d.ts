/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GEMINI_API_KEY: string | undefined;
  readonly VITE_GEMINI_A_API_KEY: string | undefined;
  readonly VITE_GEMINI_B_API_KEY: string | undefined;
  readonly VITE_VERTEX_API_KEY: string | undefined;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
