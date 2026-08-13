export type WSHandlers = {
  onOpen?: () => void
  onMessage?: (data: unknown) => void
  onClose?: () => void
}

export function createWSClient(url: string, handlers: WSHandlers = {}) {
  let socket: WebSocket | null = null
  const queue: unknown[] = []
  let retries = 0
  let closed = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleReconnect(backoff: number) {
    if (closed) return
    if (reconnectTimer !== null) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, backoff)
  }

  function connect() {
    if (closed) return
    try {
      const nextSocket = new WebSocket(url)
      socket = nextSocket
      nextSocket.onopen = () => {
        if (socket !== nextSocket || closed) return
        retries = 0
        if (handlers.onOpen) handlers.onOpen()
        for (const m of queue.splice(0)) {
          try { nextSocket.send(JSON.stringify(m)) } catch { /* send failed */ }
        }
      }
      nextSocket.onmessage = (ev) => {
        if (socket !== nextSocket || closed) return
        try {
          const msg = JSON.parse(ev.data) as unknown
          if (handlers.onMessage) handlers.onMessage(msg)
        } catch { /* parse failed */ }
      }
      nextSocket.onclose = () => {
        // A superseded socket may close after a newer connection exists. Its
        // callbacks must not tear down or reconnect the active connection.
        if (socket !== nextSocket) return
        socket = null
        if (handlers.onClose) handlers.onClose()
        if (closed) return

        const backoff = Math.min(1000 * Math.pow(2, retries), 15000) + Math.floor(Math.random() * 300)
        retries += 1
        scheduleReconnect(backoff)
      }
    } catch (e) {
      console.error('[WS] Connection error', e)
      const backoff = Math.min(1000 * Math.pow(2, retries), 15000)
      retries += 1
      scheduleReconnect(backoff)
    }
  }

  connect()

  return {
    send: (payload: unknown) => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        try { socket.send(JSON.stringify(payload)) } catch { /* send failed */ }
      } else if (!closed) {
        queue.push(payload)
      }
    },
    close: () => {
      closed = true
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      queue.length = 0
      try { socket?.close() } catch { /* close failed */ }
      socket = null
    }
  }
}
