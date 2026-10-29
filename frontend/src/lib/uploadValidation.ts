// Mirrors the backend's file_kind(): the type comes from the file name, not the browser's MIME
export const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt'] as const

const BYTES_PER_MB = 1024 * 1024

/** Why this file can't be uploaded, or null if it can. The server checks again; this only saves
 * a pointless upload. `maxUploadMb` is undefined until the server's limit is known. */
export function validateFile(
  file: { name: string; size: number },
  maxUploadMb: number | undefined,
): string | null {
  const name = file.name.toLowerCase()
  if (!ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension) && name !== extension)) {
    return 'Only PDF, DOCX or TXT files are supported.'
  }
  if (file.size === 0) return 'The file is empty.'
  if (maxUploadMb !== undefined && file.size > maxUploadMb * BYTES_PER_MB) {
    return `The file is larger than the ${String(maxUploadMb)} MB upload limit.`
  }
  return null
}
