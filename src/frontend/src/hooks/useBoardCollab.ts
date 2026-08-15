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

  useEffect(() => {
    remoteMoveRef.current = onRemoteMove;
  }, [onRemoteMove]);

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
    }, ['aac-auth', token]);
    clientRef.current = client;

    return () => {
      client.close();
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
