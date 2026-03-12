"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Badge } from "@/components/ui/badge";
import { API_URL } from "@/lib/constants";

interface Message {
  id: string;
  sender_index: number;
  receiver_index: number | null;
  message_type: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

const typeColors: Record<string, string> = {
  info: "bg-blue-500",
  request: "bg-purple-500",
  response: "bg-green-500",
  error: "bg-red-500",
  handoff: "bg-orange-500",
};

interface MessageFeedProps {
  groupId: string;
  taskNames?: string[];
}

export default function MessageFeed({ groupId, taskNames = [] }: MessageFeedProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [filterType, setFilterType] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchMessages() {
      const { data: sessionData } = await supabase.auth.getSession();
      if (!sessionData.session) return;

      const params = new URLSearchParams({ limit: "100" });
      if (filterType) params.set("message_type", filterType);

      const res = await fetch(`${API_URL}/api/messages/${groupId}?${params}`, {
        headers: { Authorization: `Bearer ${sessionData.session.access_token}` },
      });
      if (res.ok) {
        setMessages(await res.json());
      }
      setLoading(false);
    }

    fetchMessages();
    const interval = setInterval(fetchMessages, 3000);
    return () => clearInterval(interval);
  }, [groupId, filterType]);

  function getAgentLabel(index: number): string {
    return taskNames[index] || `Agent ${index + 1}`;
  }

  if (loading) {
    return <div className="text-sm text-muted-foreground">Loading messages...</div>;
  }

  return (
    <div className="space-y-3">
      {/* Filter */}
      <div className="flex gap-2">
        <button
          onClick={() => setFilterType("")}
          className={`rounded-md border px-2 py-1 text-xs ${
            !filterType ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"
          }`}
        >
          All
        </button>
        {Object.keys(typeColors).map((t) => (
          <button
            key={t}
            onClick={() => setFilterType(t)}
            className={`rounded-md border px-2 py-1 text-xs ${
              filterType === t ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Messages */}
      {messages.length === 0 ? (
        <p className="text-sm text-muted-foreground">No messages yet.</p>
      ) : (
        <div className="max-h-96 space-y-2 overflow-y-auto">
          {messages.map((msg) => (
            <div key={msg.id} className="flex items-start gap-2 rounded-lg border border-border p-2">
              <Badge className={`shrink-0 text-[10px] text-white ${typeColors[msg.message_type] || "bg-gray-500"}`}>
                {msg.message_type}
              </Badge>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{getAgentLabel(msg.sender_index)}</span>
                  {msg.receiver_index !== null && (
                    <>
                      <span>→</span>
                      <span className="font-medium text-foreground">{getAgentLabel(msg.receiver_index)}</span>
                    </>
                  )}
                  <span className="ml-auto">
                    {new Date(msg.created_at).toLocaleTimeString()}
                  </span>
                </div>
                <p className="mt-1 text-sm break-words">{msg.content}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
