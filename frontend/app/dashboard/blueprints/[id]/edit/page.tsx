"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Edge,
  type Node,
  type OnConnect,
  type ReactFlowInstance,
  BackgroundVariant,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { supabase } from "@/lib/supabase";
import { api, Blueprint, BlueprintNode as ApiBlueprintNode, NodeTypeInfo } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { NodePalette } from "@/components/blueprints/NodePalette";
import { BlueprintNodeComponent_Memo } from "@/components/blueprints/BlueprintNode";
import { ConfigPanel } from "@/components/blueprints/ConfigPanel";

const nodeTypes = { blueprint: BlueprintNodeComponent_Memo };

interface NodeStatus {
  status: "pending" | "running" | "done" | "error";
  tokens?: number;
  duration?: number;
}

export default function BlueprintEditorPage() {
  const params = useParams();
  const router = useRouter();
  const blueprintId = params.id as string;
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [nodeTypeList, setNodeTypeList] = useState<NodeTypeInfo[]>([]);

  const [blueprintName, setBlueprintName] = useState("");
  const [blueprintDescription, setBlueprintDescription] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [runInput, setRunInput] = useState("");
  const [nodeStatuses, setNodeStatuses] = useState<Record<string, NodeStatus>>({});
  const [executionLog, setExecutionLog] = useState<string[]>([]);
  const [showTrace, setShowTrace] = useState(false);

  const tokenRef = useRef<string>("");

  // Load blueprint and node types
  useEffect(() => {
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) {
        router.push("/login");
        return;
      }
      tokenRef.current = data.session.access_token;

      try {
        const [bp, types] = await Promise.all([
          api.blueprints.get(blueprintId, data.session.access_token),
          api.blueprints.nodeTypes(),
        ]);
        setNodeTypeList(types);
        setBlueprintName(bp.name);
        setBlueprintDescription(bp.description);
        hydrate(bp, types);
      } catch {
        router.push("/dashboard/blueprints");
      }
    }
    load();
  }, [blueprintId, router]);

  // Convert API blueprint nodes to React Flow nodes + edges
  function hydrate(bp: Blueprint, types: NodeTypeInfo[]) {
    const typeMap = new Map(types.map((t) => [t.key, t]));

    const rfNodes: Node[] = bp.nodes.map((n) => ({
      id: n.id,
      type: "blueprint",
      position: n.position || { x: 0, y: 0 },
      data: {
        label: n.label,
        nodeType: n.type,
        nodeClass: typeMap.get(n.type)?.node_class || "deterministic",
        config: n.config,
      },
    }));

    const rfEdges: Edge[] = [];
    for (const n of bp.nodes) {
      for (const dep of n.dependencies) {
        rfEdges.push({
          id: `${dep}->${n.id}`,
          source: dep,
          target: n.id,
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: "hsl(var(--muted-foreground))", strokeWidth: 2 },
        });
      }
    }

    setNodes(rfNodes);
    setEdges(rfEdges);
  }

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            animated: true,
            markerEnd: { type: MarkerType.ArrowClosed },
            style: { stroke: "hsl(var(--muted-foreground))", strokeWidth: 2 },
          },
          eds,
        ),
      );
    },
    [setEdges],
  );

  // Drop handler for palette drag
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const raw = event.dataTransfer.getData("application/blueprint-node");
      if (!raw || !rfInstance || !reactFlowWrapper.current) return;

      const nodeType: NodeTypeInfo = JSON.parse(raw);
      const bounds = reactFlowWrapper.current.getBoundingClientRect();
      const position = rfInstance.screenToFlowPosition({
        x: event.clientX - bounds.left,
        y: event.clientY - bounds.top,
      });

      const id = `${nodeType.key}_${Date.now()}`;
      const newNode: Node = {
        id,
        type: "blueprint",
        position,
        data: {
          label: nodeType.display_name,
          nodeType: nodeType.key,
          nodeClass: nodeType.node_class,
          config: {},
        },
      };

      setNodes((nds) => [...nds, newNode]);
    },
    [rfInstance, setNodes],
  );

  // Selection
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  // Config changes
  function handleNodeConfigChange(nodeId: string, config: Record<string, unknown>) {
    setNodes((nds) =>
      nds.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, config } } : n,
      ),
    );
  }

  function handleNodeLabelChange(nodeId: string, label: string) {
    setNodes((nds) =>
      nds.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, label } } : n,
      ),
    );
  }

  // Serialize React Flow state back to API format
  function serialize(): ApiBlueprintNode[] {
    const edgeMap = new Map<string, string[]>();
    for (const e of edges) {
      const deps = edgeMap.get(e.target) || [];
      deps.push(e.source);
      edgeMap.set(e.target, deps);
    }

    return nodes.map((n) => ({
      id: n.id,
      type: (n.data as Record<string, unknown>).nodeType as string,
      label: (n.data as Record<string, unknown>).label as string,
      config: (n.data as Record<string, unknown>).config as Record<string, unknown>,
      dependencies: edgeMap.get(n.id) || [],
      position: n.position,
    }));
  }

  // Save
  async function handleSave() {
    setSaving(true);
    try {
      await api.blueprints.update(
        blueprintId,
        {
          name: blueprintName,
          description: blueprintDescription,
          nodes: serialize(),
        },
        tokenRef.current,
      );
    } catch {
      // Could add toast here
    } finally {
      setSaving(false);
    }
  }

  // Run blueprint
  async function handleRun() {
    setRunning(true);
    setShowTrace(true);
    setExecutionLog([]);
    setNodeStatuses({});

    // Reset node statuses to pending
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: { ...n.data, status: "pending", tokens: undefined, duration: undefined },
      })),
    );

    // Save first
    await handleSave();

    const url = api.blueprints.run(blueprintId, { input_text: runInput }, tokenRef.current);
    const controller = new AbortController();

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${tokenRef.current}`,
        },
        body: JSON.stringify({ input_text: runInput }),
        signal: controller.signal,
      });

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) return;

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") continue;

          try {
            const event = JSON.parse(payload);
            handleSSEEvent(event);
          } catch {
            // ignore malformed events
          }
        }
      }
    } catch {
      setExecutionLog((prev) => [...prev, "Connection lost"]);
    } finally {
      setRunning(false);
    }
  }

  function handleSSEEvent(event: { type: string; data: Record<string, unknown> }) {
    const { type, data } = event;

    if (type === "node_start" || type === "layer_start") {
      const nodeIds = (data.node_ids as string[]) || [data.node_id as string];
      for (const nid of nodeIds.filter(Boolean)) {
        updateNodeStatus(nid, { status: "running" });
      }
      setExecutionLog((prev) => [...prev, `Running: ${nodeIds.join(", ")}`]);
    }

    if (type === "node_done") {
      const nid = data.node_id as string;
      updateNodeStatus(nid, {
        status: "done",
        tokens: data.tokens as number | undefined,
        duration: data.duration_ms as number | undefined,
      });
      setExecutionLog((prev) => [
        ...prev,
        `Done: ${nid}${data.duration_ms ? ` (${((data.duration_ms as number) / 1000).toFixed(1)}s)` : ""}`,
      ]);
    }

    if (type === "node_error") {
      const nid = data.node_id as string;
      updateNodeStatus(nid, { status: "error" });
      setExecutionLog((prev) => [...prev, `Error: ${nid} — ${data.error || "unknown"}`]);
    }

    if (type === "result") {
      setExecutionLog((prev) => [...prev, "Blueprint execution completed"]);
    }

    if (type === "error") {
      setExecutionLog((prev) => [...prev, `Error: ${data.data || "unknown"}`]);
    }
  }

  function updateNodeStatus(nodeId: string, status: NodeStatus) {
    setNodeStatuses((prev) => ({ ...prev, [nodeId]: status }));
    setNodes((nds) =>
      nds.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...status } } : n,
      ),
    );
  }

  // Delete selected node
  function handleDeleteNode() {
    if (!selectedNodeId) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedNodeId));
    setEdges((eds) =>
      eds.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId),
    );
    setSelectedNodeId(null);
  }

  const selectedNode = selectedNodeId
    ? nodes.find((n) => n.id === selectedNodeId)
    : null;

  const selectedNodeData = selectedNode
    ? {
        id: selectedNode.id,
        type: (selectedNode.data as Record<string, unknown>).nodeType as string,
        label: (selectedNode.data as Record<string, unknown>).label as string,
        nodeClass: (selectedNode.data as Record<string, unknown>).nodeClass as string,
        config: (selectedNode.data as Record<string, unknown>).config as Record<string, unknown>,
      }
    : null;

  return (
    <div className="fixed inset-0 flex flex-col bg-background">
      {/* Top bar */}
      <div className="flex h-12 items-center justify-between border-b border-border bg-card px-4">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/dashboard/blueprints")}
          >
            &larr; Back
          </Button>
          <span className="text-sm font-semibold">{blueprintName || "Untitled"}</span>
        </div>
        <div className="flex items-center gap-2">
          {selectedNodeId && (
            <Button variant="destructive" size="sm" onClick={handleDeleteNode}>
              Delete Node
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </Button>
          <div className="flex items-center gap-1">
            <input
              type="text"
              placeholder="Input text..."
              value={runInput}
              onChange={(e) => setRunInput(e.target.value)}
              className="h-8 w-48 rounded-md border border-border bg-background px-2 text-sm"
            />
            <Button size="sm" onClick={handleRun} disabled={running}>
              {running ? "Running..." : "Run"}
            </Button>
          </div>
        </div>
      </div>

      {/* Main editor area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Node Palette */}
        <NodePalette nodeTypes={nodeTypeList} />

        {/* Canvas */}
        <div ref={reactFlowWrapper} className="flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={setRfInstance}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            fitView
            className="bg-background"
            deleteKeyCode="Backspace"
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
            <Controls />
            <MiniMap
              nodeColor={(n) => {
                const d = n.data as Record<string, unknown>;
                if (d.status === "running") return "#3b82f6";
                if (d.status === "done") return "#22c55e";
                if (d.status === "error") return "#ef4444";
                return d.nodeClass === "agent" ? "#a855f7" : "#6b7280";
              }}
              className="!bg-card"
            />
          </ReactFlow>
        </div>

        {/* Config Panel */}
        <ConfigPanel
          selectedNode={selectedNodeData}
          blueprintName={blueprintName}
          blueprintDescription={blueprintDescription}
          onBlueprintNameChange={setBlueprintName}
          onBlueprintDescriptionChange={setBlueprintDescription}
          onNodeConfigChange={handleNodeConfigChange}
          onNodeLabelChange={handleNodeLabelChange}
        />
      </div>

      {/* Execution trace panel */}
      {showTrace && (
        <div className="h-48 shrink-0 overflow-y-auto border-t border-border bg-card p-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-semibold text-muted-foreground">Execution Trace</h4>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-xs"
              onClick={() => setShowTrace(false)}
            >
              Close
            </Button>
          </div>
          <div className="mt-2 space-y-1 font-mono text-xs">
            {executionLog.length === 0 ? (
              <p className="text-muted-foreground">No events yet</p>
            ) : (
              executionLog.map((log, i) => (
                <div key={i} className="text-muted-foreground">
                  <span className="mr-2 text-[10px] text-muted-foreground/50">
                    {String(i + 1).padStart(3, " ")}
                  </span>
                  {log}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
