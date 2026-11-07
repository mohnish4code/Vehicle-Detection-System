// Mirrors the [api] limits in config.toml so we can complain before uploading.
// The backend enforces them anyway.
export const MAX_FILES = 10;
export const MAX_FILE_MB = 10;
export const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp", "image/bmp", "image/heic", "image/heif"];

export interface Rejected {
  name: string;
  reason: string;
}

export function checkFiles(files: File[]): { accepted: File[]; rejected: Rejected[] } {
  const accepted: File[] = [];
  const rejected: Rejected[] = [];

  for (const file of files) {
    if (file.type && !ACCEPTED_TYPES.includes(file.type)) {
      rejected.push({ name: file.name, reason: "not a JPEG, PNG, WebP, BMP or HEIC image" });
    } else if (file.size > MAX_FILE_MB * 1024 * 1024) {
      rejected.push({ name: file.name, reason: `larger than ${MAX_FILE_MB} MB` });
    } else if (file.size === 0) {
      rejected.push({ name: file.name, reason: "file is empty" });
    } else if (accepted.length >= MAX_FILES) {
      rejected.push({ name: file.name, reason: `only ${MAX_FILES} images per scan` });
    } else {
      accepted.push(file);
    }
  }
  return { accepted, rejected };
}
