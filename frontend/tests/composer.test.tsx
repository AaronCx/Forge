import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

describe("Composer", () => {
  it("sends on Enter and clears, but not on Shift+Enter", async () => {
    const { Composer } = await import("@/components/dashboard/Composer");
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);

    const textarea = screen.getByLabelText("Command composer") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "summarize failures" } });

    // Shift+Enter inserts a newline (does not send).
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();

    // Enter sends (message + empty file list).
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledWith("summarize failures", []);
    expect(textarea.value).toBe("");
  });

  it("does not send empty/whitespace messages", async () => {
    const { Composer } = await import("@/components/dashboard/Composer");
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);

    const textarea = screen.getByLabelText("Command composer");
    fireEvent.change(textarea, { target: { value: "   " } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("disables sending when disabled (e.g. demo mode)", async () => {
    const { Composer } = await import("@/components/dashboard/Composer");
    const onSend = vi.fn();
    render(<Composer onSend={onSend} disabled />);

    const textarea = screen.getByLabelText("Command composer");
    fireEvent.change(textarea, { target: { value: "hi" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("enables attach (PR-5) and keeps mic disabled until PR-6", async () => {
    const { Composer } = await import("@/components/dashboard/Composer");
    render(<Composer onSend={vi.fn()} />);
    expect(screen.getByLabelText("Attach files")).not.toBeDisabled();
    expect(screen.getByLabelText("Voice input")).toBeDisabled();
  });

  it("enables the mic only when onTranscribe is provided", async () => {
    const { Composer } = await import("@/components/dashboard/Composer");
    const { rerender } = render(<Composer onSend={vi.fn()} />);
    expect(screen.getByLabelText("Voice input")).toBeDisabled();

    rerender(<Composer onSend={vi.fn()} onTranscribe={vi.fn(async () => "hi")} />);
    expect(screen.getByLabelText("Voice input")).not.toBeDisabled();
  });

  it("surfaces an error when recording is unsupported in the browser", async () => {
    const { Composer } = await import("@/components/dashboard/Composer");
    render(<Composer onSend={vi.fn()} onTranscribe={vi.fn(async () => "hi")} />);
    // jsdom has no navigator.mediaDevices.getUserMedia.
    fireEvent.click(screen.getByLabelText("Voice input"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/isn.t supported|permission/i);
  });

  it("shows a chip for an attached file and can send with attachments", async () => {
    const { Composer } = await import("@/components/dashboard/Composer");
    const onSend = vi.fn();
    const { container } = render(<Composer onSend={onSend} />);

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByText("notes.txt")).toBeInTheDocument();

    // Sending with only an attachment (no text) is allowed.
    fireEvent.click(screen.getByLabelText("Send"));
    expect(onSend).toHaveBeenCalledWith("", [file]);
  });
});

describe("DispatchThread", () => {
  it("renders nothing when there is no thread", async () => {
    const { DispatchThread } = await import("@/components/dashboard/DispatchThread");
    const { container } = render(
      <DispatchThread thread={null} onClarifyReply={vi.fn()} busy={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows routing header, output, and a run link when done", async () => {
    const { DispatchThread } = await import("@/components/dashboard/DispatchThread");
    render(
      <DispatchThread
        thread={{
          status: "done",
          message: "summarize failures",
          target: { type: "agent", id: "agent-123456789" },
          rationale: "it summarizes failures",
          steps: ["Step 1: read logs"],
          output: "All clear.",
          runId: "run-9",
        }}
        onClarifyReply={vi.fn()}
        busy={false}
      />,
    );

    expect(screen.getByText(/summarize failures/)).toBeInTheDocument();
    expect(screen.getByText(/it summarizes failures/)).toBeInTheDocument();
    expect(screen.getByText("All clear.")).toBeInTheDocument();
    const link = screen.getByText("View in Operations →").closest("a");
    expect(link).toHaveAttribute("href", "/dashboard/ops");
  });

  it("renders a clarify reply box and submits the reply", async () => {
    const { DispatchThread } = await import("@/components/dashboard/DispatchThread");
    const onClarifyReply = vi.fn();
    render(
      <DispatchThread
        thread={{
          status: "clarify",
          message: "make a report",
          steps: [],
          output: "",
          clarifyQuestion: "Which report?",
          threadId: "th-1",
        }}
        onClarifyReply={onClarifyReply}
        busy={false}
      />,
    );

    expect(screen.getByText("Which report?")).toBeInTheDocument();
    const reply = screen.getByLabelText("Clarify reply");
    fireEvent.change(reply, { target: { value: "the weekly one" } });
    fireEvent.click(screen.getByText("Reply"));
    expect(onClarifyReply).toHaveBeenCalledWith("the weekly one", "th-1");
  });

  it("shows the none and error states", async () => {
    const { DispatchThread } = await import("@/components/dashboard/DispatchThread");
    const { rerender } = render(
      <DispatchThread
        thread={{ status: "none", message: "x", steps: [], output: "", noneMessage: "No agent fits." }}
        onClarifyReply={vi.fn()}
        busy={false}
      />,
    );
    expect(screen.getByText("No agent fits.")).toBeInTheDocument();

    rerender(
      <DispatchThread
        thread={{ status: "error", message: "x", steps: [], output: "", errorText: "Boom." }}
        onClarifyReply={vi.fn()}
        busy={false}
      />,
    );
    expect(screen.getByText("Boom.")).toBeInTheDocument();
  });
});
