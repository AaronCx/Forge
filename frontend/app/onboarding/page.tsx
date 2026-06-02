"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { ConnectModel } from "@/components/onboarding/ConnectModel";
import { TailorAndSeed } from "@/components/onboarding/TailorAndSeed";

const STEPS = ["Connect a model", "Tailor & seed"] as const;

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);

  // Mark onboarded and leave — used by every Skip and by Finish.
  const completeAndExit = useCallback(async () => {
    try {
      const token = await getToken();
      if (token) {
        await api.preferences.update({ onboarded_at: new Date().toISOString() }, token);
      }
    } catch {
      // Don't trap the user if the write fails — still let them into the app.
    }
    router.push("/dashboard");
  }, [router]);

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col px-4 py-10">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Welcome to Forge</h1>
          <p className="text-sm text-muted-foreground">A minute of setup tailors Forge to you. Skip any time.</p>
        </div>
        <Button variant="ghost" size="sm" onClick={completeAndExit}>
          Skip setup
        </Button>
      </div>

      {/* Progress */}
      <ol className="mb-8 flex items-center gap-2 text-sm" aria-label="Progress">
        {STEPS.map((label, i) => (
          <li key={label} className="flex items-center gap-2">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${
                i <= step ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
              }`}
            >
              {i + 1}
            </span>
            <span className={i === step ? "font-medium" : "text-muted-foreground"}>{label}</span>
            {i < STEPS.length - 1 && <span className="mx-1 text-muted-foreground">→</span>}
          </li>
        ))}
      </ol>

      <div className="flex-1 rounded-xl border bg-card p-6 shadow-sm">
        {step === 0 ? (
          <ConnectModel onConnected={() => setStep(1)} onSkip={() => setStep(1)} />
        ) : (
          <TailorAndSeed onDone={() => router.push("/dashboard")} onSkip={completeAndExit} />
        )}
      </div>

      {step === 1 && (
        <button
          type="button"
          onClick={() => setStep(0)}
          className="mt-4 self-start text-sm text-muted-foreground hover:text-foreground"
        >
          ← Back
        </button>
      )}
    </div>
  );
}
