import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

type ClientCall = {
  url: string;
  options: { queue?: unknown[] };
  closeArgs: Array<{ clearQueue?: boolean } | undefined>;
  sent: unknown[];
};

const clients = vi.hoisted(() => [] as ClientCall[]);

vi.mock('../src/lib/ws', () => ({
  createWSClient: (
    url: string,
    _handlers: unknown,
    _protocols: unknown,
    options: { queue?: unknown[] } = {},
  ) => {
    const entry: ClientCall = { url, options, closeArgs: [], sent: [] };
    clients.push(entry);
    return {
      send: (payload: unknown) => {
        entry.sent.push(payload);
      },
      close: (closeOptions?: { clearQueue?: boolean }) => {
        entry.closeArgs.push(closeOptions);
      },
      pending: () => options.queue ?? [],
    };
  },
}));

import { useBoardCollab } from '../src/hooks/useBoardCollab';

describe('useBoardCollab queue ownership across reconnects', () => {
  beforeEach(() => {
    clients.length = 0;
  });

  it('hands the same pending-move queue to the replacement client on a token rotation (A7)', () => {
    const { rerender } = renderHook(
      ({ token }: { token: string }) => useBoardCollab({ boardId: 3, token }),
      { initialProps: { token: 'token-1' } },
    );

    const first = clients[0];
    expect(first.options.queue).toEqual([]);

    rerender({ token: 'token-2' });

    const second = clients[1];
    // The rotated credential needs a new socket, but the moves queued while
    // the old one was down must flush on the new socket rather than vanish.
    expect(second.options.queue).toBe(first.options.queue);
    // The superseded client must not empty the shared queue on teardown.
    expect(first.closeArgs.at(-1)).toEqual({ clearQueue: false });
  });

  it('drops the queue when the hook switches boards', () => {
    const { rerender } = renderHook(
      ({ boardId }: { boardId: number }) => useBoardCollab({ boardId, token: 'token-1' }),
      { initialProps: { boardId: 3 } },
    );

    const first = clients[0];
    first.options.queue?.push({ op: 'move', symbol_id: 1, position: { x: 0, y: 0 } });

    rerender({ boardId: 4 });

    expect(clients[1].options.queue).toEqual([]);
  });
});
