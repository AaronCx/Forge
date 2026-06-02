"use client";

import { useRef, useState, type KeyboardEvent, type ChangeEvent } from "react";
import { Paperclip, Mic, ArrowUp, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ComposerProps {
  onSend: (message: string, files: File[]) => void;
  busy?: boolean;
  disabled?: boolean;
  placeholder?: string;
}

// Images + the document types the upload endpoint + extractor accept.
const ACCEPT = "image/*,.pdf,.docx,.txt,.md";

/**
 * Dashboard command composer. Type a task and a dispatcher agent routes it to
 * the right agent/blueprint. Enter sends; Shift+Enter inserts a newline. The
 * mic button is present but disabled until PR-6 (voice) wires it up.
 */
export function Composer({ onSend, busy = false, disabled = false, placeholder }: ComposerProps) {
  const [value, setValue] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const submit = () => {
    const message = value.trim();
    if ((!message && files.length === 0) || busy || disabled) return;
    onSend(message, files);
    setValue("");
    setFiles([]);
  };

  const onFilesPicked = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? []);
    if (picked.length) setFiles((prev) => [...prev, ...picked]);
    // Reset so picking the same file again re-fires onChange.
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
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
      {/* Attachment chips */}
      {files.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-2" aria-label="Attachments">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center gap-1 rounded-md border bg-muted px-2 py-1 text-xs"
            >
              <span className="max-w-[180px] truncate">{f.name}</span>
              <button
                type="button"
                onClick={() => removeFile(i)}
                disabled={busy}
                className="text-muted-foreground hover:text-foreground"
                aria-label={`Remove ${f.name}`}
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={onFilesPicked}
        aria-hidden="true"
        tabIndex={-1}
      />

      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            disabled={disabled || busy}
            onClick={() => fileInputRef.current?.click()}
            title="Attach images or documents"
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
          disabled={busy || disabled || (!value.trim() && files.length === 0)}
          title={disabled ? "Dispatch is disabled in demo mode" : "Send (Enter)"}
          aria-label="Send"
        >
          <ArrowUp />
        </Button>
      </div>
    </div>
  );
}
