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
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    downloadJson({ hello: 'world' }, 'export.json');

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(revokeObjectURL).not.toHaveBeenCalled();
    expect(click).toHaveBeenCalledOnce();

    vi.advanceTimersByTime(99);
    expect(revokeObjectURL).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test');
  });

  it('clicks an in-document anchor and detaches it afterwards (H18)', () => {
    vi.useFakeTimers();
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);

    // Recorded from inside the click, where `this` is the anchor being
    // clicked: Firefox ignores a synthetic click on a detached node.
    let attachedWhenClicked = false;
    let clickedDownload = '';
    let clickedHref = '';
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function (this: HTMLAnchorElement) {
        attachedWhenClicked = document.body.contains(this);
        clickedDownload = this.download;
        clickedHref = this.href;
      });

    downloadJson({ hello: 'world' }, 'export.json');

    expect(click).toHaveBeenCalledOnce();
    expect(attachedWhenClicked).toBe(true);
    expect(clickedDownload).toBe('export.json');
    expect(clickedHref.startsWith('blob:')).toBe(true);

    // The anchor is detached once the download has been handed off.
    vi.advanceTimersByTime(100);
    expect(document.querySelectorAll('a')).toHaveLength(0);
  });
});
