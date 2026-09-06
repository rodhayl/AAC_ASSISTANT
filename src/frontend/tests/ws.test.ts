import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createWSClient } from '../src/lib/ws';

class MockWebSocket {
  static readonly OPEN = 1;
  static instances: MockWebSocket[] = [];
  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn(() => this.onclose?.());

  constructor(url: string) {
    void url;
    MockWebSocket.instances.push(this);
  }
}

describe('createWSClient reconnect lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0);
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('does not reconnect after an explicit close while retry is pending', () => {
    const client = createWSClient('ws://example.test');
    const socket = MockWebSocket.instances[0];

    socket.onclose?.();
    expect(MockWebSocket.instances).toHaveLength(1);

    client.close();
    vi.advanceTimersByTime(1_001);

    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it('reconnects after an unexpected close', () => {
    const client = createWSClient('ws://example.test');
    const socket = MockWebSocket.instances[0];

    socket.onclose?.();
    vi.advanceTimersByTime(1_001);

    expect(MockWebSocket.instances).toHaveLength(2);
    client.close();
  });

  it('keeps only one reconnect timer after repeated close events', () => {
    const client = createWSClient('ws://example.test');
    const socket = MockWebSocket.instances[0];

    socket.onclose?.();
    socket.onclose?.();
    vi.runOnlyPendingTimers();

    expect(MockWebSocket.instances).toHaveLength(2);
    client.close();
  });

  it('ignores a stale socket close after a newer connection exists', () => {
    const client = createWSClient('ws://example.test');
    const firstSocket = MockWebSocket.instances[0];
    firstSocket.onclose?.();
    vi.runOnlyPendingTimers();
    const secondSocket = MockWebSocket.instances[1];

    firstSocket.onclose?.();
    vi.runOnlyPendingTimers();

    expect(MockWebSocket.instances).toHaveLength(2);
    secondSocket.onclose?.();
    client.close();
  });

  it('clears queued payloads when explicitly closed', () => {
    const client = createWSClient('ws://example.test');
    const socket = MockWebSocket.instances[0];
    socket.readyState = 0;

    client.send({ op: 'move' });
    client.close();

    socket.readyState = MockWebSocket.OPEN;
    socket.onopen?.();
    expect(socket.send).not.toHaveBeenCalled();
  });

  it('drops the oldest payload once the offline queue overflows', () => {
    const client = createWSClient('ws://example.test');
    const socket = MockWebSocket.instances[0];
    socket.readyState = 0;

    // Send one more than the cap so the oldest must be evicted.
    for (let i = 0; i < 101; i++) {
      client.send({ op: 'move', seq: i });
    }
    socket.readyState = MockWebSocket.OPEN;
    socket.onopen?.();

    // Only the most recent 100 survive, in their original order (seq 1..100).
    const sent = socket.send.mock.calls.map(c => JSON.parse(c[0]));
    expect(sent).toHaveLength(100);
    expect(sent[0]).toEqual({ op: 'move', seq: 1 });
    expect(sent[99]).toEqual({ op: 'move', seq: 100 });
  });

  it('preserves order while the queue is below the cap', () => {
    const client = createWSClient('ws://example.test');
    const socket = MockWebSocket.instances[0];
    socket.readyState = 0;

    for (let i = 0; i < 3; i++) {
      client.send({ op: 'select', seq: i });
    }
    socket.readyState = MockWebSocket.OPEN;
    socket.onopen?.();

    const sent = socket.send.mock.calls.map(c => JSON.parse(c[0]));
    expect(sent).toEqual([
      { op: 'select', seq: 0 },
      { op: 'select', seq: 1 },
      { op: 'select', seq: 2 },
    ]);
  });

  it('close() empties the queue even after overflow evictions', () => {
    const client = createWSClient('ws://example.test');
    const socket = MockWebSocket.instances[0];
    socket.readyState = 0;

    for (let i = 0; i < 120; i++) {
      client.send({ op: 'move', seq: i });
    }
    client.close();

    socket.readyState = MockWebSocket.OPEN;
    socket.onopen?.();
    expect(socket.send).not.toHaveBeenCalled();
  });
});
