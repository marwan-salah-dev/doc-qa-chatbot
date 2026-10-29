interface ImportMetaEnv {
  /** Backend API base URL; defaults to /api (proxied by the Vite dev server). */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
