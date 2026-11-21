import type { WsMessage } from "../types";
import { API_BASE } from "./api";

export type SocketState = "connecting" | "open" | "closed";

function wsUrl(batchId: string): string {
  const path = `/api/downloader/batches/${encodeURIComponent(batchId)}/ws`;
  if (API_BASE) return API_BASE.replace(/^http/, "ws") + path;
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}${path}`;
}

/** WebSocket monitoring batch dengan reconnect otomatis dan ping keep-alive. */
export class BatchSocket {
  private ws: WebSocket | null = null;
  private closedByUser = false;
  private retry = 0;
  private pingTimer: number | null = null;
  private reconnectTimer: number | null = null;

  constructor(
    private batchId: string,
    private onMessage: (msg: WsMessage) => void,
    private onState: (state: SocketState) => void,
  ) {
    this.connect();
  }

  private connect() {
    this.onState("connecting");
    const ws = new WebSocket(wsUrl(this.batchId));
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      this.onState("open");
      this.pingTimer = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 20000);
    };
    ws.onmessage = (ev) => {
      try {
        this.onMessage(JSON.parse(ev.data) as WsMessage);
      } catch {
        /* abaikan pesan rusak */
      }
    };
    ws.onclose = () => {
      if (this.pingTimer) window.clearInterval(this.pingTimer);
      this.pingTimer = null;
      this.onState("closed");
      if (!this.closedByUser) {
        const delay = Math.min(10000, 1000 * 2 ** this.retry++);
        this.reconnectTimer = window.setTimeout(() => this.connect(), delay);
      }
    };
    ws.onerror = () => ws.close();
  }

  requestSnapshot() {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send("snapshot");
  }

  close() {
    this.closedByUser = true;
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    if (this.pingTimer) window.clearInterval(this.pingTimer);
    this.ws?.close();
  }
}
