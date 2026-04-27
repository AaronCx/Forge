import { Target } from "lucide-react";
import { RouteStub } from "@/components/dashboard/RouteStub";

export default function TargetsPage() {
  return (
    <RouteStub
      title="Targets"
      description="Multi-machine dispatch — execution targets that blueprint nodes can route to."
      icon={Target}
      cliCommand="forge targets list"
    />
  );
}
