"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { getToken } from "@/lib/auth-client";
import { api, type Workspace } from "@/lib/api";
import { isDemoMode } from "@/lib/demo-data";
import { FileTree } from "@/components/workspace/FileTree";
import { EditorTabs } from "@/components/workspace/EditorTabs";
import { WorkspaceSocket, type FileChangeEvent } from "@/lib/workspace-ws";
import { AgentPanel } from "@/components/workspace/AgentPanel";
import { Button } from "@/components/ui/button";
import { ArrowLeft, RefreshCw, TerminalSquare, PanelRightClose, PanelRightOpen } from "lucide-react";
import "@xterm/xterm/css/xterm.css";

// Dynamic imports for browser-only components
const CodeEditor = dynamic(
  () => import("@/components/workspace/CodeEditor").then((m) => m.CodeEditor),
  { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-muted-foreground">Loading editor...</div> }
);
const TerminalPanel = dynamic(
  () => import("@/components/workspace/Terminal").then((m) => m.TerminalPanel),
  { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-muted-foreground">Loading terminal...</div> }
);

interface FileEntry {
  name: string;
  path: string;
  type: "file" | "directory";
  size: number | null;
  children: FileEntry[] | null;
}

interface OpenFile {
  path: string;
  content: string;
  originalContent: string;
}

export default function WorkspaceIDEPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [openFiles, setOpenFiles] = useState<Map<string, OpenFile>>(new Map());
  const [activeFile, setActiveFile] = useState<string>("");
  const [highlightedPaths, setHighlightedPaths] = useState<Set<string>>(new Set());
  const [notification, setNotification] = useState<{ path: string; message: string } | null>(null);
  const [showTerminal, setShowTerminal] = useState(false);
  const [showActivityPanel, setShowActivityPanel] = useState(true);
  const [recentChanges, setRecentChanges] = useState<FileChangeEvent[]>([]);
  const [currentToken, setCurrentToken] = useState("");
  const wsRef = useRef<WorkspaceSocket | null>(null);

  // Load workspace and files
  useEffect(() => {
    if (isDemoMode()) {
      setWorkspace({
        id: workspaceId,
        user_id: "demo",
        name: "Demo Workspace",
        description: "Demo workspace",
        path: "/demo",
        status: "active",
        settings: {},
        created_at: "2026-03-20T00:00:00Z",
        updated_at: "2026-03-23T00:00:00Z",
      });
      setFiles([
        { name: "README.md", path: "README.md", type: "file", size: 256, children: null },
        { name: "main.py", path: "main.py", type: "file", size: 1024, children: null },
        {
          name: "src",
          path: "src",
          type: "directory",
          size: null,
          children: [
            { name: "app.py", path: "src/app.py", type: "file", size: 512, children: null },
            { name: "config.json", path: "src/config.json", type: "file", size: 128, children: null },
          ],
        },
      ]);
      return;
    }

    async function load() {
      const token = await getToken();
      if (!token) return;
      try {
        const [ws, fileTree] = await Promise.all([
          api.workspaces.get(workspaceId, token),
          api.workspaces.files(workspaceId, token),
        ]);
        setWorkspace(ws);
        setFiles(fileTree as FileEntry[]);
      } catch {
        router.push("/dashboard/workspace");
      }
    }
    load();
  }, [workspaceId, router]);

  // WebSocket connection
  useEffect(() => {
    if (isDemoMode()) return;

    const socket = new WorkspaceSocket();
    wsRef.current = socket;

    async function connect() {
      const token = await getToken();
      if (token) {
        setCurrentToken(token);
        socket.connect(workspaceId, token);
      }
    }
    connect();

    const unsub = socket.onFileChange((event: FileChangeEvent) => {
      refreshFiles();

      // Track for agent panel
      setRecentChanges((prev) => [event, ...prev].slice(0, 10));

      // Highlight changed file briefly
      setHighlightedPaths((prev) => { const next = new Set(prev); next.add(event.path); return next; });
      setTimeout(() => {
        setHighlightedPaths((prev) => {
          const next = new Set(prev);
          next.delete(event.path);
          return next;
        });
      }, 2000);

      // Update open file content
      if (event.type !== "file_deleted" && event.content !== undefined) {
        setOpenFiles((prev) => {
          const existing = prev.get(event.path);
          if (!existing) return prev;
          const isModified = existing.content !== existing.originalContent;
          if (isModified) {
            setNotification({ path: event.path, message: `"${event.path}" was modified externally.` });
            return prev;
          }
          const next = new Map(prev);
          next.set(event.path, { path: event.path, content: event.content!, originalContent: event.content! });
          return next;
        });
      }

      if (event.type === "file_deleted") {
        setOpenFiles((prev) => {
          const next = new Map(prev);
          next.delete(event.path);
          return next;
        });
      }
    });

    return () => {
      unsub();
      socket.disconnect();
      wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const refreshFiles = useCallback(async () => {
    if (isDemoMode()) return;
    const token = await getToken();
    if (!token) return;
    try {
      const fileTree = await api.workspaces.files(workspaceId, token);
      setFiles(fileTree as FileEntry[]);
    } catch { /* ignore */ }
  }, [workspaceId]);

  async function openFile(path: string) {
    if (openFiles.has(path)) {
      setActiveFile(path);
      return;
    }

    if (isDemoMode()) {
      const content = `# Demo file: ${path}\n\nThis is a demo workspace file.\nEdit it and see real-time sync in action.`;
      setOpenFiles((prev) => {
        const next = new Map(prev);
        next.set(path, { path, content, originalContent: content });
        return next;
      });
      setActiveFile(path);
      return;
    }

    const token = await getToken();
    if (!token) return;
    try {
      const result = await api.workspaces.readFile(workspaceId, path, token);
      setOpenFiles((prev) => {
        const next = new Map(prev);
        next.set(path, { path, content: result.content, originalContent: result.content });
        return next;
      });
      setActiveFile(path);
    } catch { /* file not found */ }
  }

  function closeFile(path: string) {
    setOpenFiles((prev) => {
      const next = new Map(prev);
      next.delete(path);
      return next;
    });
    if (activeFile === path) {
      const remaining = Array.from(openFiles.keys()).filter((p) => p !== path);
      setActiveFile(remaining[remaining.length - 1] ?? "");
    }
  }

  function handleEditorChange(content: string) {
    if (!activeFile) return;
    setOpenFiles((prev) => {
      const next = new Map(prev);
      const existing = next.get(activeFile);
      if (existing) next.set(activeFile, { ...existing, content });
      return next;
    });
  }

  async function handleSave() {
    if (!activeFile) return;
    const file = openFiles.get(activeFile);
    if (!file) return;

    if (isDemoMode()) {
      setOpenFiles((prev) => {
        const next = new Map(prev);
        next.set(activeFile, { ...file, originalContent: file.content });
        return next;
      });
      return;
    }

    const token = await getToken();
    if (!token) return;
    try {
      await api.workspaces.writeFile(workspaceId, activeFile, file.content, token);
      wsRef.current?.sendFileSave(activeFile, file.content);
      setOpenFiles((prev) => {
        const next = new Map(prev);
        next.set(activeFile, { ...file, originalContent: file.content });
        return next;
      });
    } catch { /* save failed */ }
  }

  const activeOpenFile = activeFile ? openFiles.get(activeFile) : null;
  const tabs = Array.from(openFiles.entries()).map(([path, file]) => ({
    path,
    modified: file.content !== file.originalContent,
  }));

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b border-border bg-card px-3 py-1.5">
        <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard/workspace")}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back
        </Button>
        <span className="text-sm font-medium">{workspace?.name ?? "Loading..."}</span>
        <span className="text-xs text-muted-foreground truncate">{workspace?.path}</span>
        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => setShowTerminal(!showTerminal)} title="Toggle terminal">
            <TerminalSquare className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setShowActivityPanel(!showActivityPanel)} title="Toggle activity panel">
            {showActivityPanel ? <PanelRightClose className="h-3.5 w-3.5" /> : <PanelRightOpen className="h-3.5 w-3.5" />}
          </Button>
          <Button variant="ghost" size="sm" onClick={refreshFiles} title="Refresh files">
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Notification banner */}
      {notification && (
        <div className="flex items-center gap-2 bg-yellow-900/50 border-b border-yellow-700 px-3 py-1.5 text-sm text-yellow-200">
          <span>{notification.message}</span>
          <Button size="sm" variant="outline" className="h-6 text-xs" onClick={() => { setNotification(null); openFile(notification.path); }}>
            Reload
          </Button>
          <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => setNotification(null)}>
            Keep
          </Button>
        </div>
      )}

      {/* Main IDE area */}
      <div className="flex flex-1 overflow-hidden">
        {/* File tree sidebar */}
        <div className="w-[250px] shrink-0 border-r border-border overflow-y-auto bg-card">
          <div className="px-3 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Files
          </div>
          <FileTree
            files={files}
            selectedPath={activeFile}
            onSelect={openFile}
            highlightedPaths={highlightedPaths}
          />
        </div>

        {/* Center: Editor + Terminal */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <EditorTabs tabs={tabs} activeTab={activeFile} onSelect={setActiveFile} onClose={closeFile} />

          <div className="flex-1 overflow-hidden">
            {activeOpenFile ? (
              <CodeEditor
                content={activeOpenFile.content}
                filename={activeFile}
                onChange={handleEditorChange}
                onSave={handleSave}
              />
            ) : (
              <div className="flex h-full items-center justify-center text-muted-foreground">
                <div className="text-center">
                  <p className="text-lg">Select a file to edit</p>
                  <p className="mt-1 text-sm">Click a file in the tree to open it</p>
                  <p className="mt-4 text-xs">Cmd+S to save | Real-time sync with agents and Neovim</p>
                </div>
              </div>
            )}
          </div>

          {/* Terminal panel */}
          {showTerminal && currentToken && (
            <div className="h-[200px] shrink-0 border-t border-border">
              <TerminalPanel workspaceId={workspaceId} token={currentToken} />
            </div>
          )}
        </div>

        {/* Right sidebar: Agent activity */}
        {showActivityPanel && (
          <div className="w-[260px] shrink-0 border-l border-border overflow-y-auto bg-card">
            <AgentPanel workspaceId={workspaceId} recentChanges={recentChanges} />
          </div>
        )}
      </div>
    </div>
  );
}
