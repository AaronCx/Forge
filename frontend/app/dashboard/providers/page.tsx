import { Cpu } from "lucide-react";
import { RouteStub } from "@/components/dashboard/RouteStub";

export default function ProvidersPage() {
  return (
    <RouteStub
      title="Providers"
      description="Multi-model provider registry, health checks, and side-by-side comparison."
      icon={Cpu}
      cliCommand="forge models list"
    />
  );
}
