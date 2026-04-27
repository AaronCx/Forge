import { Video } from "lucide-react";
import { RouteStub } from "@/components/dashboard/RouteStub";

export default function RecordingsPage() {
  return (
    <RouteStub
      title="Recordings"
      description="Screen recordings from Computer Use sessions — gallery, scrubbing player, trace links."
      icon={Video}
      cliCommand="forge recordings list"
    />
  );
}
