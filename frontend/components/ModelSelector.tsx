"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { api, ModelInfo } from "@/lib/api";

interface ModelSelectorProps {
  value: string | null;
  onChange: (model: string | null) => void;
  label?: string;
  showDefault?: boolean;
}

export function ModelSelector({ value, onChange, label = "Model", showDefault = true }: ModelSelectorProps) {
  const [models, setModels] = useState<ModelInfo[]>([]);

  useEffect(() => {
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;
      try {
        const modelList = await api.providers.models(data.session.access_token);
        setModels(modelList);
      } catch {
        // Provider API may not be available
      }
    }
    load();
  }, []);

  // Group by provider
  const grouped = models.reduce<Record<string, ModelInfo[]>>((acc, m) => {
    (acc[m.provider] ||= []).push(m);
    return acc;
  }, {});

  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-muted-foreground">
        {label}
      </label>
      <select
        value={value || ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
      >
        {showDefault && <option value="">Default (account setting)</option>}
        {Object.entries(grouped).map(([provider, providerModels]) => (
          <optgroup key={provider} label={provider.charAt(0).toUpperCase() + provider.slice(1)}>
            {providerModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
}
