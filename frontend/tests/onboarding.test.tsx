import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/lib/auth-client", () => ({
  getToken: vi.fn(async () => "test-token"),
}));

const templates = vi.fn();
const finish = vi.fn();
const updatePrefs = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    agents: { templates: (...a: unknown[]) => templates(...a) },
    onboarding: { finish: (...a: unknown[]) => finish(...a) },
    preferences: { update: (...a: unknown[]) => updatePrefs(...a) },
    // ConnectModel (rendered by the page) references these; never called in these tests.
    providers: { verify: vi.fn(), connect: vi.fn() },
  },
}));

describe("TailorAndSeed", () => {
  beforeEach(() => {
    templates.mockReset();
    finish.mockReset();
    push.mockReset();
    templates.mockResolvedValue([
      { id: "t1", name: "Code Reviewer", description: "reviews code" },
      { id: "t2", name: "Research Agent", description: "does research" },
    ]);
    finish.mockResolvedValue({ ok: true, created_agents: 2, agents: [] });
  });

  it("seeds selected templates + custom instructions on finish", async () => {
    const { TailorAndSeed } = await import("@/components/onboarding/TailorAndSeed");
    const onDone = vi.fn();
    render(<TailorAndSeed onDone={onDone} onSkip={vi.fn()} />);

    // Templates load and default to selected.
    await waitFor(() => expect(screen.getByLabelText("Code Reviewer")).toBeInTheDocument());

    const ta = screen.getByPlaceholderText(/I work in Rust/i);
    fireEvent.change(ta, { target: { value: "I use TypeScript." } });

    fireEvent.click(screen.getByText("Finish setup"));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const [payload, token] = finish.mock.calls[0];
    expect(token).toBe("test-token");
    expect(payload.custom_instructions).toBe("I use TypeScript.");
    expect(payload.template_ids).toEqual(expect.arrayContaining(["t1", "t2"]));
  });

  it("Skip calls onSkip", async () => {
    const { TailorAndSeed } = await import("@/components/onboarding/TailorAndSeed");
    const onSkip = vi.fn();
    render(<TailorAndSeed onDone={vi.fn()} onSkip={onSkip} />);
    fireEvent.click(screen.getByText("Skip"));
    expect(onSkip).toHaveBeenCalled();
  });
});

describe("OnboardingPage", () => {
  beforeEach(() => {
    push.mockReset();
    updatePrefs.mockReset();
    updatePrefs.mockResolvedValue({});
  });

  it("starts on the connect step and 'Skip setup' marks onboarded + leaves", async () => {
    const OnboardingPage = (await import("@/app/onboarding/page")).default;
    render(<OnboardingPage />);

    // The connect step is shown first (its Verify button is unique to it).
    expect(screen.getByText("Verify")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Skip setup"));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/dashboard"));
    expect(updatePrefs).toHaveBeenCalledWith(
      expect.objectContaining({ onboarded_at: expect.any(String) }),
      "test-token",
    );
  });
});
