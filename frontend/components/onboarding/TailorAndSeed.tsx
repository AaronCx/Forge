"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { api, type Agent } from "@/lib/api";
import { getToken } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface TailorAndSeedProps {
  onDone: () => void;
  onSkip: () => void;
}

const USE_CASES: { id: string; label: string; match: RegExp }[] = [
  { id: "coding", label: "Coding", match: /code|review|implement/i },
  { id: "research", label: "Research", match: /research|search|report/i },
  { id: "data", label: "Data", match: /data|extract|json/i },
  { id: "computer_use", label: "Computer use", match: /screen|browser|click|gui/i },
  { id: "exploring", label: "Just exploring", match: /.*/ },
];

/**
 * Onboarding "tailor + seed" step — pick a use case (pre-selects templates),
 * toggle starter agents, add global custom instructions, and optionally
 * describe an agent in plain language. Everything is optional; Skip escapes.
 */
export function TailorAndSeed({ onDone, onSkip }: TailorAndSeedProps) {
  const [templates, setTemplates] = useState<Agent[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [useCase, setUseCase] = useState("");
  const [customInstructions, setCustomInstructions] = useState("");
  const [customAgent, setCustomAgent] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const token = await getToken();
      if (!token) return;
      try {
        const tpls = await api.agents.templates(token);
        if (cancelled) return;
        setTemplates(tpls);
        setSelected(new Set(tpls.map((t) => t.id))); // default all on
      } catch {
        // non-fatal — the step still works without templates
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const pickUseCase = (uc: { id: string; match: RegExp }) => {
    setUseCase(uc.id);
    // Pre-select templates that match this use case (others stay available).
    if (uc.id !== "exploring") {
      const matched = templates.filter((t) => uc.match.test(`${t.name} ${t.description}`));
      if (matched.length > 0) setSelected(new Set(matched.map((t) => t.id)));
    } else {
      setSelected(new Set(templates.map((t) => t.id)));
    }
  };

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const finish = async () => {
    setSaving(true);
    setError("");
    try {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated.");
      await api.onboarding.finish(
        {
          use_case: useCase || undefined,
          custom_instructions: customInstructions.trim() || undefined,
          template_ids: Array.from(selected),
          custom_agents: customAgent.trim() ? [{ description: customAgent.trim() }] : [],
        },
        token,
      );
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to finish setup.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-semibold">Tailor Forge to you</h2>
          <p className="text-sm text-muted-foreground">Seed a few agents and tell Forge about your work. All optional.</p>
        </div>
        <Button variant="ghost" size="sm" onClick={onSkip}>
          Skip
        </Button>
      </div>

      {/* Use case */}
      <div className="space-y-2">
        <p className="text-sm font-medium">What are you working on?</p>
        <div className="flex flex-wrap gap-2">
          {USE_CASES.map((uc) => (
            <button
              key={uc.id}
              type="button"
              onClick={() => pickUseCase(uc)}
              className={`rounded-full border px-3 py-1 text-sm ${
                useCase === uc.id ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent"
              }`}
            >
              {uc.label}
            </button>
          ))}
        </div>
      </div>

      {/* Starter agents */}
      {templates.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">Starter agents</p>
          <ul className="space-y-2">
            {templates.map((t) => (
              <li key={t.id} className="flex items-start gap-2 rounded-md border p-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={selected.has(t.id)}
                  onChange={() => toggle(t.id)}
                  aria-label={t.name}
                />
                <div>
                  <p className="text-sm font-medium">{t.name}</p>
                  <p className="text-xs text-muted-foreground">{t.description}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Custom instructions */}
      <div className="space-y-1">
        <p className="text-sm font-medium">Tell Forge about you</p>
        <p className="text-xs text-muted-foreground">
          Your stack, domain, conventions, preferences — we weave this into every agent.
        </p>
        <Textarea
          value={customInstructions}
          onChange={(e) => setCustomInstructions(e.target.value)}
          rows={3}
          placeholder="e.g. I work in Rust and TypeScript, prefer terse output, and care about test coverage."
        />
      </div>

      {/* Write your own */}
      <div className="space-y-1">
        <p className="text-sm font-medium">Write your own (optional)</p>
        <Textarea
          value={customAgent}
          onChange={(e) => setCustomAgent(e.target.value)}
          rows={2}
          placeholder="Describe an agent in plain language — e.g. “watch my CI runs and summarize failures.”"
        />
      </div>

      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      <div className="flex justify-end">
        <Button onClick={finish} disabled={saving}>
          {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
          Finish setup
        </Button>
      </div>
    </div>
  );
}
