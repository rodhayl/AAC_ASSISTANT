export const MAX_IMAGE_FILE_BYTES = 5 * 1024 * 1024;

export function isValidImageFile(
  file: File,
  maxBytes: number = MAX_IMAGE_FILE_BYTES,
): boolean {
  return file.type.startsWith('image/') && file.size <= maxBytes;
}

export function downloadJson(data: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  // Let the browser consume the blob URL before releasing it. Immediate
  // revocation can cancel downloads in browsers that start navigation lazily.
  setTimeout(() => URL.revokeObjectURL(url), 100);
}
