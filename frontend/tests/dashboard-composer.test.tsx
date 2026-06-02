import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
vi.mock("@/lib/auth-client", () => ({ getToken: vi.fn(async () => "test-token") }));
vi.mock("@/lib/demo-data", () => ({ isDemoMode: () => false }));

const targets = vi.fn();
const providersList = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    dispatch: { targets: (...a: unknown[]) => targets(...a), send: vi.fn() },
    providers: { list: (...a: unknown[]) => providersList(...a) },
    uploads: { files: vi.fn() },
    transcribe: { send: vi.fn() },
  },
}));

describe("DashboardComposer — disabled state without a provider", () => {
  beforeEach(() => {
    targets.mockReset().mockResolvedValue([]);
    providersList.mockReset();
  });

  it("shows a Connect-a-model CTA and disables the composer when no provider", async () => {
    providersList.mockResolvedValue({ providers: [] });
    const { DashboardComposer } = await import("@/components/dashboard/DashboardComposer");
    render(<DashboardComposer />);

    await waitFor(() => expect(screen.getByTestId("composer-no-provider")).toBeInTheDocument());
    expect(screen.getByText("Connect a model →").closest("a")).toHaveAttribute("href", "/dashboard/connections");
    expect(screen.getByLabelText("Command composer", { selector: "textarea" })).toBeDisabled();
  });

  it("enables the composer when a provider is connected", async () => {
    providersList.mockResolvedValue({ providers: ["ollama"] });
    const { DashboardComposer } = await import("@/components/dashboard/DashboardComposer");
    render(<DashboardComposer />);

    await waitFor(() => expect(providersList).toHaveBeenCalled());
    expect(screen.queryByTestId("composer-no-provider")).toBeNull();
    expect(screen.getByLabelText("Command composer", { selector: "textarea" })).not.toBeDisabled();
  });
});
