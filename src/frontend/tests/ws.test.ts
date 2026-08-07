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
});
