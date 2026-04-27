import Link from "next/link";
import { RunHistory } from "@/components/dashboard/RunHistory";
import { Button } from "@/components/ui/button";

export function RecentRunsSection() {
  return (
    <section id="recent" className="scroll-mt-20 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Recent runs</h2>
        <Link href="/dashboard/runs">
          <Button variant="ghost" size="sm">
            View all
          </Button>
        </Link>
      </div>
      <RunHistory limit={5} />
    </section>
  );
}
