import { Monitor } from "lucide-react";
import { RouteStub } from "@/components/dashboard/RouteStub";

export default function ComputerUsePage() {
  return (
    <RouteStub
      title="Computer Use"
      description="Status and audit of the Steer (GUI) and Drive (Terminal) capability layer."
      icon={Monitor}
      cliCommand="forge cu status"
    />
  );
}
