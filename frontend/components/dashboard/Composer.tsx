"use client";

import { useRef, useState, type KeyboardEvent, type ChangeEvent } from "react";
import { Paperclip, Mic, ArrowUp, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ComposerProps {
  onSend: (message: string, files: File[]) => void;
  // When provided, the mic button is enabled: it records audio and calls this
  // to get a transcript (PR-6). Omitted/undefined → mic stays disabled.
  onTranscribe?: (blob: Blob) => Promise<string>;
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
export function Composer({ onSend, onTranscribe, busy = false, disabled = false, placeholder }: ComposerProps) {
  const [value, setValue] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [micError, setMicError] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

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

  const startRecording = async () => {
    setMicError("");
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setMicError("Recording isn’t supported in this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (!onTranscribe || blob.size === 0) return;
        setTranscribing(true);
        try {
          const text = await onTranscribe(blob);
          if (text) {
            setValue((prev) => (prev ? `${prev} ${text}` : text));
            textareaRef.current?.focus();
          }
        } catch (err) {
          setMicError(err instanceof Error ? err.message : "Transcription failed.");
        } finally {
          setTranscribing(false);
        }
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      setMicError("Microphone permission denied.");
    }
  };

  const toggleMic = () => {
    if (recording) {
      mediaRecorderRef.current?.stop();
      setRecording(false);
    } else {
      void startRecording();
    }
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
            variant={recording ? "destructive" : "ghost"}
            size="icon"
            disabled={!onTranscribe || disabled || busy || transcribing}
            onClick={toggleMic}
            title={
              !onTranscribe
                ? "Voice input unavailable"
                : recording
                  ? "Stop recording"
                  : "Record a voice command"
            }
            aria-label={recording ? "Stop recording" : "Voice input"}
            aria-pressed={recording}
          >
            <Mic className={recording ? "animate-pulse" : undefined} />
          </Button>
          {recording && (
            <span className="ml-1 flex items-center gap-1 text-xs text-destructive" role="status">
              <span className="h-2 w-2 animate-pulse rounded-full bg-destructive" />
              Recording…
            </span>
          )}
          {transcribing && (
            <span className="ml-1 text-xs text-muted-foreground" role="status">
              Transcribing…
            </span>
          )}
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
      {micError && (
        <p className="mt-1 text-xs text-destructive" role="alert">
          {micError}
        </p>
      )}
    </div>
  );
}
