import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

vi.mock("@/lib/auth-client", () => ({ getToken: vi.fn(async () => "test-token") }));
vi.mock("@/lib/backend-context", () => ({ useBackendMode: () => ({ mode: "live", backendUrl: "" }) }));

const prefsGet = vi.fn();
const prefsUpdate = vi.fn();
const providersList = vi.fn();
const agentsList = vi.fn();
const runsList = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    preferences: { get: (...a: unknown[]) => prefsGet(...a), update: (...a: unknown[]) => prefsUpdate(...a) },
    providers: { list: (...a: unknown[]) => providersList(...a) },
    agents: { list: (...a: unknown[]) => agentsList(...a) },
    runs: { list: (...a: unknown[]) => runsList(...a) },
  },
}));

const basePrefs = {
  user_id: "u1", default_model: null, default_provider: null,
  onboarded_at: null, use_case: null, custom_instructions: null, getting_started_dismissed: false,
};

describe("GettingStarted", () => {
  beforeEach(() => {
    prefsGet.mockReset();
    prefsUpdate.mockReset().mockResolvedValue({});
    providersList.mockReset().mockResolvedValue({ providers: [] });
    agentsList.mockReset().mockResolvedValue([]);
    runsList.mockReset().mockResolvedValue([]);
  });

  it("shows the checklist with incomplete items for a fresh account", async () => {
    prefsGet.mockResolvedValue(basePrefs);
    const { GettingStarted } = await import("@/components/dashboard/GettingStarted");
    render(<GettingStarted />);

    await waitFor(() => expect(screen.getByTestId("getting-started")).toBeInTheDocument());
    expect(screen.getByText("Connect a model")).toBeInTheDocument();
    expect(screen.getByText("Add an agent")).toBeInTheDocument();
    expect(screen.getByText("0/5 done — finish setting up Forge.")).toBeInTheDocument();
  });

  it("auto-hides when the core items are all done", async () => {
    prefsGet.mockResolvedValue(basePrefs);
    providersList.mockResolvedValue({ providers: ["ollama"] });
    agentsList.mockResolvedValue([{ id: "a1" }]);
    runsList.mockResolvedValue([{ id: "r1" }]);
    const { GettingStarted } = await import("@/components/dashboard/GettingStarted");
    const { container } = render(<GettingStarted />);

    await waitFor(() => expect(prefsGet).toHaveBeenCalled());
    await waitFor(() => expect(container.querySelector('[data-testid="getting-started"]')).toBeNull());
  });

  it("dismiss persists the flag and hides the card", async () => {
    prefsGet.mockResolvedValue(basePrefs);
    const { GettingStarted } = await import("@/components/dashboard/GettingStarted");
    render(<GettingStarted />);

    await waitFor(() => expect(screen.getByTestId("getting-started")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("Dismiss getting started"));

    await waitFor(() => expect(screen.queryByTestId("getting-started")).toBeNull());
    expect(prefsUpdate).toHaveBeenCalledWith({ getting_started_dismissed: true }, "test-token");
  });

  it("stays hidden when already dismissed in preferences", async () => {
    prefsGet.mockResolvedValue({ ...basePrefs, getting_started_dismissed: true });
    const { GettingStarted } = await import("@/components/dashboard/GettingStarted");
    const { container } = render(<GettingStarted />);
    await waitFor(() => expect(prefsGet).toHaveBeenCalled());
    expect(container.querySelector('[data-testid="getting-started"]')).toBeNull();
  });
});
