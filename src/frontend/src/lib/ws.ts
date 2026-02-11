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

  function connect() {
    if (closed) return
    // console.log('[WS] Connecting to', url)
    try {
      socket = new WebSocket(url)
      socket.onopen = () => {
        // console.log('[WS] Connected')
        retries = 0
        if (handlers.onOpen) handlers.onOpen()
        for (const m of queue.splice(0)) {
          try { socket?.send(JSON.stringify(m)) } catch { /* send failed */ }
        }
      }
      socket.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as unknown
          if (handlers.onMessage) handlers.onMessage(msg)
        } catch { /* parse failed */ }
      }
      socket.onclose = () => {
        // console.log('[WS] Closed', ev.code, ev.reason)
        socket = null
        if (handlers.onClose) handlers.onClose()
        if (closed) return // Don't reconnect if explicitly closed
        
        const backoff = Math.min(1000 * Math.pow(2, retries), 15000) + Math.floor(Math.random() * 300)
        retries += 1
        setTimeout(connect, backoff)
      }
    } catch (e) {
      console.error('[WS] Connection error', e)
      const backoff = Math.min(1000 * Math.pow(2, retries), 15000)
      retries += 1
      setTimeout(connect, backoff)
    }
  }

  connect()

  return {
    send: (payload: unknown) => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        try { socket.send(JSON.stringify(payload)) } catch { /* send failed */ }
      } else {
        queue.push(payload)
      }
    },
    close: () => {
      closed = true
      try { socket?.close() } catch { /* close failed */ }
    }
  }
}
