"use client";

import { useEffect, useRef } from "react";
import { DEMO_TERMINAL_TRANSCRIPT } from "@/lib/demo-data";

const PROMPT = "\x1b[36mforge@scraper-agent\x1b[0m:\x1b[34m~\x1b[0m$ ";

/**
 * Renders a pre-recorded terminal session inside an xterm.js instance so the
 * Workspace IDE has a populated terminal even with no backend connection.
 */
export function DemoTerminal() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let term: any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let fit: any;
    let timers: ReturnType<typeof setTimeout>[] = [];

    async function init() {
      const { Terminal } = await import("@xterm/xterm");
      const { FitAddon } = await import("@xterm/addon-fit");

      term = new Terminal({
        cursorBlink: false,
        disableStdin: true,
        fontSize: 13,
        fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
        theme: {
          background: "#1e1e2e",
          foreground: "#cdd6f4",
        },
      });
      fit = new FitAddon();
      term.loadAddon(fit);
      if (disposed) {
        term.dispose();
        return;
      }
      term.open(containerRef.current!);
      fit.fit();

      term.writeln(
        "\x1b[2mDemo terminal — pre-recorded session. Typing is disabled until a Forge runtime is connected.\x1b[0m"
      );
      term.write("\r\n");

      function play(line: { input?: string; output?: string; delay: number }) {
        timers.push(
          setTimeout(() => {
            if (disposed) return;
            if (line.input !== undefined) {
              term.write(PROMPT + line.input + "\r\n");
            }
            if (line.output !== undefined) {
              term.write(line.output);
            }
          }, line.delay)
        );
      }

      DEMO_TERMINAL_TRANSCRIPT.forEach(play);
      timers.push(
        setTimeout(() => {
          if (!disposed) term.write(PROMPT);
        }, 2000)
      );
    }

    init();

    function handleResize() {
      try {
        fit?.fit();
      } catch {
        // ignore
      }
    }
    window.addEventListener("resize", handleResize);

    return () => {
      disposed = true;
      window.removeEventListener("resize", handleResize);
      timers.forEach(clearTimeout);
      timers = [];
      term?.dispose();
    };
  }, []);

  return <div ref={containerRef} className="h-full w-full" />;
}
