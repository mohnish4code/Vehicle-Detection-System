/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend URL. Leave unset to use /api on the same origin (Vite proxy / nginx). */
  readonly VITE_API_URL?: string;
}
