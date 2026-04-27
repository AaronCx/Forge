import { Card, CardContent } from "@/components/ui/card";
import type { LucideIcon } from "lucide-react";

interface RouteStubProps {
  title: string;
  description: string;
  icon: LucideIcon;
  cliCommand?: string;
}

export function RouteStub({ title, description, icon: Icon, cliCommand }: RouteStubProps) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
        <p className="mt-2 text-muted-foreground">{description}</p>
      </div>

      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
          <Icon className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
          <div className="space-y-1">
            <p className="text-sm font-medium">Building this surface</p>
            <p className="max-w-md text-sm text-muted-foreground">
              The web UI for this feature is on the roadmap. The CLI already has full coverage
              {cliCommand ? (
                <>
                  {" "}via{" "}
                  <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{cliCommand}</code>
                </>
              ) : null}
              .
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
