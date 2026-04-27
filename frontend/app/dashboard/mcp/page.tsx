import { Plug } from "lucide-react";
import { RouteStub } from "@/components/dashboard/RouteStub";

export default function McpPage() {
  return (
    <RouteStub
      title="MCP"
      description="Model Context Protocol connection management — connected servers, tool inventory, and add-connection flow."
      icon={Plug}
      cliCommand="forge mcp list"
    />
  );
}
