/**
 * Demo seed fixtures for the 6 newly-built routes (Computer Use, Providers,
 * MCP, Targets, Recordings, API Keys). Data is realistic enough that the demo
 * surface looks like the live product.
 */

export interface CapabilityRow {
  platform: "macos" | "linux" | "windows";
  steer: "ok" | "missing" | "n/a";
  drive: "ok" | "missing" | "n/a";
  ocr: "ok" | "missing" | "n/a";
  notes: string;
}

export const DEMO_CU_CAPABILITY: CapabilityRow[] = [
  { platform: "macos", steer: "ok", drive: "ok", ocr: "ok", notes: "tesseract 5.4.1 · tmux 3.4" },
  { platform: "linux", steer: "ok", drive: "ok", ocr: "ok", notes: "xdotool 3.20211022 · scrot 1.7" },
  { platform: "windows", steer: "ok", drive: "ok", ocr: "n/a", notes: "pyautogui 0.9.54 · PowerShell 7.5" },
];

export const DEMO_CU_SESSIONS = [
  { id: "drive-1", target: "local-mac-mini", kind: "drive", focus: "tmux:demo-mac-mini", started_at: "2026-04-25T18:24:11Z" },
  { id: "steer-1", target: "linux-ec2", kind: "steer", focus: "Firefox · 1920×1080", started_at: "2026-04-25T18:21:09Z" },
];

export const DEMO_CU_AUDIT = [
  { ts: "2026-04-25T18:25:02Z", action: "steer_click", target: "local-mac-mini", blueprint: "Computer Use demo", result: "ok" },
  { ts: "2026-04-25T18:24:48Z", action: "steer_type", target: "local-mac-mini", blueprint: "Computer Use demo", result: "ok" },
  { ts: "2026-04-25T18:24:11Z", action: "steer_see", target: "local-mac-mini", blueprint: "Computer Use demo", result: "ok" },
  { ts: "2026-04-25T18:21:09Z", action: "drive_run", target: "linux-ec2", blueprint: "scraper-agent CI", result: "ok" },
  { ts: "2026-04-25T18:18:42Z", action: "cu_planner", target: "local-mac-mini", blueprint: "Computer Use demo", result: "ok" },
  { ts: "2026-04-25T18:11:09Z", action: "steer_focus", target: "win-workstation", blueprint: "Test runner", result: "ok" },
  { ts: "2026-04-25T17:52:41Z", action: "drive_send", target: "linux-ec2", blueprint: "scraper-agent CI", result: "blocked", note: "command blocked by safety policy" },
];

export const DEMO_CU_SAFETY = {
  app_blocklist: ["Keychain Access", "1Password", "System Preferences"],
  command_blocklist: ["rm -rf /", "sudo rm", "shutdown"],
  rate_limit_per_minute: 30,
  approval_gates: ["destructive_write", "network_egress"],
};

export const DEMO_CU_SCREENSHOTS = [
  { id: "shot-1", ts: "2026-04-25T18:25:02Z", target: "local-mac-mini", thumb_caption: "demo blueprint · post-click" },
  { id: "shot-2", ts: "2026-04-25T18:24:11Z", target: "local-mac-mini", thumb_caption: "demo blueprint · capture" },
  { id: "shot-3", ts: "2026-04-25T18:21:09Z", target: "linux-ec2", thumb_caption: "scraper-agent CI · run pytest" },
  { id: "shot-4", ts: "2026-04-25T18:11:09Z", target: "win-workstation", thumb_caption: "Test runner · focus IDE" },
];

export const DEMO_PROVIDERS = [
  { provider: "openai", status: "healthy" as const, latency_ms: 118, default_model: "gpt-4o-mini", api_key_masked: "sk-•••• A4xB" },
  { provider: "anthropic", status: "healthy" as const, latency_ms: 142, default_model: "claude-haiku-4-5", api_key_masked: "sk-ant-•••• Q9zM" },
  { provider: "google", status: "healthy" as const, latency_ms: 96, default_model: "gemini-1.5-flash", api_key_masked: "AIza•••• T7nP" },
  { provider: "ollama", status: "degraded" as const, latency_ms: 0, default_model: "llama3:8b", api_key_masked: "(local · http://localhost:11434)" },
];

export const DEMO_MODEL_CATALOG = [
  { provider: "openai", name: "gpt-4o", context: 128000, input_cost: 0.005, output_cost: 0.015, supports_streaming: true },
  { provider: "openai", name: "gpt-4o-mini", context: 128000, input_cost: 0.00015, output_cost: 0.0006, supports_streaming: true },
  { provider: "anthropic", name: "claude-opus-4-7", context: 200000, input_cost: 0.015, output_cost: 0.075, supports_streaming: true },
  { provider: "anthropic", name: "claude-sonnet-4-6", context: 200000, input_cost: 0.003, output_cost: 0.015, supports_streaming: true },
  { provider: "anthropic", name: "claude-haiku-4-5", context: 200000, input_cost: 0.00025, output_cost: 0.00125, supports_streaming: true },
  { provider: "google", name: "gemini-1.5-pro", context: 1000000, input_cost: 0.00125, output_cost: 0.005, supports_streaming: true },
  { provider: "google", name: "gemini-1.5-flash", context: 1000000, input_cost: 0.0000375, output_cost: 0.00015, supports_streaming: true },
  { provider: "ollama", name: "llama3:8b", context: 8192, input_cost: 0, output_cost: 0, supports_streaming: true },
];

export const DEMO_MCP_SERVERS = [
  {
    id: "mcp-fs",
    name: "filesystem",
    transport: "stdio" as const,
    status: "connected" as const,
    tool_count: 6,
    last_seen: "2026-04-25T18:24:00Z",
    tools: [
      { name: "read_file", description: "Read a UTF-8 text file", schema: '{ "path": "string" }' },
      { name: "write_file", description: "Write a UTF-8 text file", schema: '{ "path": "string", "contents": "string" }' },
      { name: "list_dir", description: "List directory entries", schema: '{ "path": "string" }' },
      { name: "stat", description: "Stat a path", schema: '{ "path": "string" }' },
      { name: "delete_file", description: "Delete a file", schema: '{ "path": "string" }' },
      { name: "move", description: "Move or rename a file", schema: '{ "src": "string", "dst": "string" }' },
    ],
  },
  {
    id: "mcp-github",
    name: "github",
    transport: "sse" as const,
    status: "connected" as const,
    tool_count: 4,
    last_seen: "2026-04-25T18:22:11Z",
    tools: [
      { name: "list_issues", description: "List repository issues", schema: '{ "repo": "string", "state": "open|closed" }' },
      { name: "create_issue", description: "Open a new issue", schema: '{ "repo": "string", "title": "string", "body": "string" }' },
      { name: "search_code", description: "Search across repos", schema: '{ "query": "string" }' },
      { name: "get_pr", description: "Fetch a pull request", schema: '{ "repo": "string", "number": "number" }' },
    ],
  },
  {
    id: "mcp-web",
    name: "web-fetch",
    transport: "stdio" as const,
    status: "degraded" as const,
    tool_count: 2,
    last_seen: "2026-04-25T17:50:14Z",
    tools: [
      { name: "fetch", description: "Fetch a URL", schema: '{ "url": "string" }' },
      { name: "search", description: "Web search", schema: '{ "query": "string" }' },
    ],
  },
];

export const DEMO_MCP_LOGS = [
  { ts: "2026-04-25T18:24:00Z", server: "filesystem", level: "info", message: "handshake ok · 6 tools registered" },
  { ts: "2026-04-25T18:22:11Z", server: "github", level: "info", message: "handshake ok · 4 tools registered" },
  { ts: "2026-04-25T17:50:14Z", server: "web-fetch", level: "warn", message: "handshake ok · upstream rate-limited (HTTP 429)" },
];

export const DEMO_TARGETS = [
  {
    id: "tgt-mac",
    name: "local-mac-mini",
    platform: "macos" as const,
    capabilities: ["steer", "drive", "ocr"],
    status: "healthy" as const,
    last_seen: "2026-04-25T18:24:00Z",
  },
  {
    id: "tgt-linux",
    name: "linux-ec2",
    platform: "linux" as const,
    capabilities: ["xdotool", "tmux"],
    status: "healthy" as const,
    last_seen: "2026-04-25T18:21:00Z",
  },
  {
    id: "tgt-win",
    name: "win-workstation",
    platform: "windows" as const,
    capabilities: ["pyautogui", "powershell"],
    status: "idle" as const,
    last_seen: "2026-04-25T16:01:00Z",
  },
];

export const DEMO_RECORDINGS = [
  {
    id: "rec-1",
    blueprint: "Computer Use demo",
    target: "local-mac-mini",
    duration_ms: 18400,
    started_at: "2026-04-25T18:24:11Z",
    trace_id: "trace-cu-demo-1",
    thumbnail_caption: "click → type → verify",
  },
  {
    id: "rec-2",
    blueprint: "scraper-agent CI",
    target: "linux-ec2",
    duration_ms: 41200,
    started_at: "2026-04-25T18:21:09Z",
    trace_id: "trace-scraper-1",
    thumbnail_caption: "pytest run on ec2",
  },
  {
    id: "rec-3",
    blueprint: "Test runner",
    target: "win-workstation",
    duration_ms: 9100,
    started_at: "2026-04-25T18:11:09Z",
    trace_id: "trace-winrunner-1",
    thumbnail_caption: "focus IDE → run tests",
  },
  {
    id: "rec-4",
    blueprint: "Computer Use demo",
    target: "local-mac-mini",
    duration_ms: 12800,
    started_at: "2026-04-24T22:14:42Z",
    trace_id: "trace-cu-demo-2",
    thumbnail_caption: "see → plan → click",
  },
];

export const DEMO_API_KEYS_DETAILED = [
  {
    id: "key-prod",
    name: "production",
    masked: "fge_•••• 9F2A",
    created_at: "2026-03-12T11:04:00Z",
    last_used_at: "2026-04-25T18:23:11Z",
  },
  {
    id: "key-ci",
    name: "ci-pipeline",
    masked: "fge_•••• Q7XD",
    created_at: "2026-04-01T08:00:00Z",
    last_used_at: "2026-04-25T07:12:00Z",
  },
];
