"use client";

import { useEffect, useRef } from "react";

interface StreamingOutputProps {
  content: string;
}

export function StreamingOutput({ content }: StreamingOutputProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [content]);

  return (
    <div
      ref={containerRef}
      className="max-h-96 overflow-auto rounded-lg bg-muted/50 p-4 font-mono text-sm"
    >
      {content || (
        <span className="text-muted-foreground">
          Output will appear here...
        </span>
      )}
    </div>
  );
}
