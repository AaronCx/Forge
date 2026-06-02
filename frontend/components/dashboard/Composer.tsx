"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { Paperclip, Mic, ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ComposerProps {
  onSend: (message: string) => void;
  busy?: boolean;
  disabled?: boolean;
  placeholder?: string;
}

/**
 * Dashboard command composer. Type a task and a dispatcher agent routes it to
 * the right agent/blueprint. Enter sends; Shift+Enter inserts a newline. The
 * attach + mic buttons are present but disabled until PR-5 (uploads) / PR-6
 * (voice) wire them up.
 */
export function Composer({ onSend, busy = false, disabled = false, placeholder }: ComposerProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const message = value.trim();
    if (!message || busy || disabled) return;
    onSend(message);
    setValue("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="rounded-xl border bg-card p-3 shadow-sm">
      <Textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={2}
        placeholder={
          placeholder ?? "Describe a task — e.g. “summarize the latest run failures” — and it’ll route to the right agent."
        }
        className="min-h-[44px] resize-none border-0 bg-transparent p-1 shadow-none focus-visible:ring-0"
        aria-label="Command composer"
      />
      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            disabled
            title="Attach files (coming soon)"
            aria-label="Attach files"
          >
            <Paperclip />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            disabled
            title="Voice input (coming soon)"
            aria-label="Voice input"
          >
            <Mic />
          </Button>
        </div>
        <Button
          type="button"
          size="icon"
          onClick={submit}
          disabled={busy || disabled || !value.trim()}
          title={disabled ? "Dispatch is disabled in demo mode" : "Send (Enter)"}
          aria-label="Send"
        >
          <ArrowUp />
        </Button>
      </div>
    </div>
  );
}
