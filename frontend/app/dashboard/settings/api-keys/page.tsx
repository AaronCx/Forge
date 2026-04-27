import { Key } from "lucide-react";
import { RouteStub } from "@/components/dashboard/RouteStub";

export default function ApiKeysPage() {
  return (
    <RouteStub
      title="API Keys"
      description="Manage API keys for accessing Forge from external systems."
      icon={Key}
      cliCommand="forge keys list"
    />
  );
}
