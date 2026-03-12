"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { supabase } from "@/lib/supabase";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function NewBlueprintPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleCreate() {
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    setSaving(true);
    setError("");

    try {
      const { data } = await supabase.auth.getSession();
      if (!data.session) {
        router.push("/login");
        return;
      }

      const bp = await api.blueprints.create(
        {
          name: name.trim(),
          description: description.trim(),
          nodes: [],
        },
        data.session.access_token,
      );
      router.push(`/dashboard/blueprints/${bp.id}/edit`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create blueprint");
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg">
      <h1 className="text-3xl font-bold">New Blueprint</h1>
      <p className="mt-1 text-muted-foreground">
        Create a new visual workflow
      </p>

      <div className="mt-8 space-y-4">
        <div>
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="My Workflow"
            className="mt-1"
          />
        </div>
        <div>
          <Label htmlFor="desc">Description</Label>
          <Textarea
            id="desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What does this workflow do?"
            className="mt-1"
            rows={3}
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex gap-3">
          <Button onClick={handleCreate} disabled={saving}>
            {saving ? "Creating..." : "Create & Open Editor"}
          </Button>
          <Button variant="outline" onClick={() => router.back()}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}
