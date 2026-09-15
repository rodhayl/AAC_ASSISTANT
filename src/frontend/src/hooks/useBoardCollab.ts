import { useCallback, useEffect, useRef } from 'react';
import { config } from '../config';
import { createWSClient } from '../lib/ws';

export type BoardPosition = { x: number; y: number };

type BoardChangeMessage = {
  type?: string;
  payload?: {
    op?: string;
    symbol_id?: number;
    position?: BoardPosition;
  };
};

interface UseBoardCollabOptions {
  boardId?: number;
  token?: string | null;
  onRemoteMove?: (symbolId: number, position: BoardPosition) => void;
}

export function useBoardCollab({
  boardId,
  token,
  onRemoteMove,
}: UseBoardCollabOptions) {
  const clientRef = useRef<ReturnType<typeof createWSClient> | null>(null);
  const remoteMoveRef = useRef(onRemoteMove);
  // Shared across client instances so a token rotation (which forces a new
  // socket with the rotated credential) does not drop moves queued while the
  // old socket was down (A7).
  const pendingMovesRef = useRef<unknown[]>([]);

  useEffect(() => {
    remoteMoveRef.current = onRemoteMove;
  }, [onRemoteMove]);

  // A different board must never flush the previous board's queued moves.
  // The ref is only ever mutated (never reassigned), so capturing the array
  // itself is safe and keeps the cleanup off the mutable ref accessor.
  useEffect(() => {
    const pendingMoves = pendingMovesRef.current;
    return () => {
      pendingMoves.length = 0;
    };
  }, [boardId]);

  useEffect(() => {
    if (!boardId || !token) return;

    const url = `${config.WS_BASE_URL}/collab/boards/${boardId}`;
    const client = createWSClient(url, {
      onMessage: (message) => {
        const wsMessage = message as BoardChangeMessage | null;
        const payload = wsMessage?.payload;
        if (
          wsMessage?.type === 'board_change' &&
          payload?.op === 'move' &&
          payload.symbol_id != null &&
          payload.position
        ) {
          remoteMoveRef.current?.(payload.symbol_id, payload.position);
        }
      },
    }, ['aac-auth', token], { queue: pendingMovesRef.current });
    clientRef.current = client;

    return () => {
      client.close({ clearQueue: false });
      if (clientRef.current === client) {
        clientRef.current = null;
      }
    };
  }, [boardId, token]);

  const sendMove = useCallback((symbolId: number, position: BoardPosition) => {
    clientRef.current?.send({
      op: 'move',
      symbol_id: symbolId,
      position,
    });
  }, []);

  return { sendMove };
}
