import { Clock } from "lucide-react";

import type { RepositorySummary } from "@/types";
import { formatRelativeTime } from "@/lib/format";

/**
 * One repository in the list.
 *
 * Wording matters for the data-ethics invariants: this shows sync state, never contributor
 * performance. "Never synced" is a state to investigate, not a judgement.
 */
export function RepositoryCard({ repository }: RepositoryCardProps) {
  const synced = formatRelativeTime(repository.last_synced_at);

  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-border bg-card p-4">
      <div className="flex flex-col gap-1">
        <span className="font-mono text-sm font-medium">{repository.full_name}</span>
        {repository.default_branch ? (
          <span className="font-mono text-xs text-muted-foreground">
            {repository.default_branch}
          </span>
        ) : null}
      </div>

      <div className="flex flex-col items-end gap-1">
        {repository.is_demo ? (
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
            Demo
          </span>
        ) : null}
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Clock className="h-3.5 w-3.5" aria-hidden />
          {synced}
        </span>
      </div>
    </div>
  );
}

interface RepositoryCardProps {
  repository: RepositorySummary;
}
