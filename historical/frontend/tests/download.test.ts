import { afterEach, describe, expect, it, vi } from 'vitest';
import { downloadJson, isValidImageFile, MAX_IMAGE_FILE_BYTES } from '../src/lib/download';

describe('download utilities', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('accepts images at or below the size limit and rejects other files', () => {
    expect(isValidImageFile(new File(['x'], 'small.png', { type: 'image/png' }))).toBe(true);
    expect(
      isValidImageFile(
        new File([new Uint8Array(MAX_IMAGE_FILE_BYTES + 1)], 'large.png', { type: 'image/png' }),
      ),
    ).toBe(false);
    expect(isValidImageFile(new File(['x'], 'note.txt', { type: 'text/plain' }))).toBe(false);
  });

  it('downloads formatted JSON and releases the object URL', () => {
    vi.useFakeTimers();
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const click = vi.fn();
    vi.spyOn(document, 'createElement').mockReturnValue({
      href: '',
      download: '',
      click,
    } as unknown as HTMLAnchorElement);

    downloadJson({ hello: 'world' }, 'export.json');

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(revokeObjectURL).not.toHaveBeenCalled();
    expect(click).toHaveBeenCalledOnce();

    vi.advanceTimersByTime(99);
    expect(revokeObjectURL).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test');
  });
});
