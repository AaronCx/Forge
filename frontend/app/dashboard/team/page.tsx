"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { isDemoMode } from "@/lib/demo-data";

interface Organization {
  id: string;
  name: string;
  slug: string;
  description: string;
  owner_id: string;
  created_at: string;
}

interface Member {
  id: string;
  org_id: string;
  user_id: string;
  role: string;
  joined_at: string;
}

const roleBadgeColors: Record<string, string> = {
  owner: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  admin: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  member: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  viewer: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
};

async function getToken(): Promise<string> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token || "";
}

export default function TeamPage() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedOrg, setSelectedOrg] = useState<Organization | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgDesc, setNewOrgDesc] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isDemoMode()) {
      setLoading(false);
      return;
    }
    loadOrgs();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadOrgs() {
    setLoading(true);
    try {
      const t = await getToken();
      const data = await api.organizations.list(t);
      setOrgs(data);
    } catch {
      setOrgs([]);
    } finally {
      setLoading(false);
    }
  }

  async function selectOrg(org: Organization) {
    setSelectedOrg(org);
    try {
      const t = await getToken();
      if (t) {
        const m = await api.organizations.members(org.id, t);
        setMembers(m);
      }
    } catch {
      setMembers([]);
    }
  }

  async function handleCreateOrg() {
    if (!newOrgName.trim()) return;
    try {
      const t = await getToken();
      await api.organizations.create({ name: newOrgName, description: newOrgDesc }, t);
      setNewOrgName("");
      setNewOrgDesc("");
      setShowCreate(false);
      await loadOrgs();
    } catch {
      // error handling
    }
  }

  async function handleDeleteOrg(orgId: string) {
    try {
      const t = await getToken();
      await api.organizations.delete(orgId, t);
      setSelectedOrg(null);
      setMembers([]);
      await loadOrgs();
    } catch {
      // error handling
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Teams</h1>
        <Button onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? "Cancel" : "New Organization"}
        </Button>
      </div>

      {showCreate && (
        <Card>
          <CardContent className="p-4 space-y-3">
            <Input
              placeholder="Organization name"
              value={newOrgName}
              onChange={(e) => setNewOrgName(e.target.value)}
            />
            <Input
              placeholder="Description (optional)"
              value={newOrgDesc}
              onChange={(e) => setNewOrgDesc(e.target.value)}
            />
            <Button onClick={handleCreateOrg} disabled={!newOrgName.trim()}>
              Create Organization
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Org list */}
        <div className="space-y-4">
          {loading ? (
            <p className="text-muted-foreground">Loading...</p>
          ) : orgs.length === 0 ? (
            <p className="text-muted-foreground">
              No organizations yet. Create one to get started.
            </p>
          ) : (
            orgs.map((org) => (
              <Card
                key={org.id}
                className={`cursor-pointer transition-colors hover:bg-accent/50 ${
                  selectedOrg?.id === org.id ? "border-primary" : ""
                }`}
                onClick={() => selectOrg(org)}
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-semibold">{org.name}</h3>
                      <p className="text-xs text-muted-foreground">@{org.slug}</p>
                      {org.description && (
                        <p className="text-sm text-muted-foreground mt-1">
                          {org.description}
                        </p>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>

        {/* Org detail + members */}
        {selectedOrg && (
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>{selectedOrg.name}</CardTitle>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => handleDeleteOrg(selectedOrg.id)}
                  >
                    Delete
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p>
                  <span className="text-muted-foreground">Slug:</span> @{selectedOrg.slug}
                </p>
                <p>
                  <span className="text-muted-foreground">Description:</span>{" "}
                  {selectedOrg.description || "None"}
                </p>
                <p>
                  <span className="text-muted-foreground">Created:</span>{" "}
                  {new Date(selectedOrg.created_at).toLocaleDateString()}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">
                  Members ({members.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                {members.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No members.</p>
                ) : (
                  <div className="space-y-2">
                    {members.map((member) => (
                      <div
                        key={member.id}
                        className="flex items-center justify-between rounded border p-2"
                      >
                        <span className="text-sm font-mono">
                          {member.user_id.slice(0, 8)}...
                        </span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            roleBadgeColors[member.role] || roleBadgeColors.viewer
                          }`}
                        >
                          {member.role}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
