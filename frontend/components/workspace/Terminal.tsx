"use client";

import { useEffect, useRef } from "react";
import { API_URL } from "@/lib/constants";

interface TerminalProps {
  workspaceId: string;
  token: string;
}

export function TerminalPanel({ workspaceId, token }: TerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const termRef = useRef<InstanceType<any>>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let terminal: InstanceType<any> = null;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let fitAddon: InstanceType<any> = null;

    async function init() {
      const { Terminal } = await import("@xterm/xterm");
      const { FitAddon } = await import("@xterm/addon-fit");
      const { WebLinksAddon } = await import("@xterm/addon-web-links");

      terminal = new Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
        theme: {
          background: "#1e1e2e",
          foreground: "#cdd6f4",
          cursor: "#f5e0dc",
          black: "#45475a",
          red: "#f38ba8",
          green: "#a6e3a1",
          yellow: "#f9e2af",
          blue: "#89b4fa",
          magenta: "#cba6f7",
          cyan: "#94e2d5",
          white: "#bac2de",
        },
      });

      fitAddon = new FitAddon();
      terminal.loadAddon(fitAddon);
      terminal.loadAddon(new WebLinksAddon());

      terminal.open(containerRef.current!);
      fitAddon.fit();
      termRef.current = terminal;

      // Connect WebSocket
      const wsUrl = API_URL.replace(/^http/, "ws");
      const ws = new WebSocket(`${wsUrl}/ws/terminal/${workspaceId}?token=${encodeURIComponent(token)}`);
      wsRef.current = ws;

      ws.binaryType = "arraybuffer";

      ws.onopen = () => {
        // Send initial resize
        const dims = fitAddon.proposeDimensions();
        if (dims) {
          ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
        }
      };

      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          terminal.write(new Uint8Array(event.data));
        } else {
          terminal.write(event.data);
        }
      };

      terminal.onData((data: string) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(data);
        }
      });

      // Handle resize
      const observer = new ResizeObserver(() => {
        fitAddon.fit();
        const dims = fitAddon.proposeDimensions();
        if (dims && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
        }
      });
      observer.observe(containerRef.current!);

      return () => observer.disconnect();
    }

    const cleanup = init();

    return () => {
      cleanup.then((fn) => fn?.());
      wsRef.current?.close();
      termRef.current?.dispose();
    };
  }, [workspaceId, token]);

  return <div ref={containerRef} className="h-full w-full" />;
}
