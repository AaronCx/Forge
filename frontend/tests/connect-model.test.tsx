import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/auth-client", () => ({
  getToken: vi.fn(async () => "test-token"),
}));

const verify = vi.fn();
const connect = vi.fn();
vi.mock("@/lib/api", () => ({
  api: { providers: { verify: (...a: unknown[]) => verify(...a), connect: (...a: unknown[]) => connect(...a) } },
}));

describe("ConnectModel", () => {
  beforeEach(() => {
    verify.mockReset();
    connect.mockReset();
  });

  it("has a Skip control that calls onSkip", async () => {
    const { ConnectModel } = await import("@/components/onboarding/ConnectModel");
    const onSkip = vi.fn();
    render(<ConnectModel onConnected={vi.fn()} onSkip={onSkip} />);
    fireEvent.click(screen.getByText("Skip"));
    expect(onSkip).toHaveBeenCalled();
  });

  it("renders cloud / local / custom tabs", async () => {
    const { ConnectModel } = await import("@/components/onboarding/ConnectModel");
    render(<ConnectModel onConnected={vi.fn()} onSkip={vi.fn()} />);
    expect(screen.getByRole("tab", { name: /cloud/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /local/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /custom/i })).toBeInTheDocument();
  });

  it("verifies, shows the model picker, and connects", async () => {
    const { ConnectModel } = await import("@/components/onboarding/ConnectModel");
    const onConnected = vi.fn();
    verify.mockResolvedValue({ ok: true, models: [{ id: "gpt-4o-mini", name: "gpt-4o-mini" }] });
    connect.mockResolvedValue({ ok: true, provider: "openai", default_model: "gpt-4o-mini" });

    render(<ConnectModel onConnected={onConnected} onSkip={vi.fn()} />);

    // Default tab is cloud; verify reveals the model picker.
    fireEvent.click(screen.getByText("Verify"));
    await waitFor(() => expect(screen.getByLabelText("Model")).toBeInTheDocument());
    expect(verify).toHaveBeenCalledWith(expect.objectContaining({ kind: "cloud" }), "test-token");

    fireEvent.click(screen.getByText("Connect & continue"));
    await waitFor(() => expect(onConnected).toHaveBeenCalled());
    expect(connect).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "cloud", model: "gpt-4o-mini" }),
      "test-token",
    );
  });

  it("shows an error when verification fails", async () => {
    const { ConnectModel } = await import("@/components/onboarding/ConnectModel");
    verify.mockResolvedValue({ ok: false, error: "Invalid API key" });

    render(<ConnectModel onConnected={vi.fn()} onSkip={vi.fn()} />);
    fireEvent.click(screen.getByText("Verify"));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid API key");
  });
});
