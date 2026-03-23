/**
 * WebSocket client for workspace real-time file sync.
 */

import { API_URL } from "@/lib/constants";

export interface FileChangeEvent {
  type: "file_changed" | "file_created" | "file_deleted" | "file_renamed";
  path: string;
  content?: string;
  change_type: string;
  source?: string;
  old_path?: string;
  new_path?: string;
}

type ChangeCallback = (event: FileChangeEvent) => void;

export class WorkspaceSocket {
  private ws: WebSocket | null = null;
  private callbacks: ChangeCallback[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private workspaceId = "";
  private token = "";

  connect(workspaceId: string, token: string): void {
    this.workspaceId = workspaceId;
    this.token = token;
    this._connect();
  }

  private _connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    const wsUrl = API_URL.replace(/^http/, "ws");
    const url = `${wsUrl}/ws/workspace/${this.workspaceId}?token=${encodeURIComponent(this.token)}`;

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectDelay = 1000;
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as FileChangeEvent;
        for (const cb of this.callbacks) {
          cb(data);
        }
      } catch {
        // ignore parse errors
      }
    };

    this.ws.onclose = () => {
      this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  private _scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
      this._connect();
    }, this.reconnectDelay);
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  onFileChange(callback: ChangeCallback): () => void {
    this.callbacks.push(callback);
    return () => {
      this.callbacks = this.callbacks.filter((cb) => cb !== callback);
    };
  }

  sendFileSave(path: string, content: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "file_save", path, content }));
    }
  }
}
