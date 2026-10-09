"use client";

import { AlertCircle, CheckCircle2, Loader2, PauseCircle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useJobPolling } from "@/hooks/use-job-polling";
import type { IngestionCounts, JobStatus } from "@/types";

/**
 * Live job status. Polls `GET /jobs/{id}` until the job succeeds or fails.
 *
 * A `paused` job is *not* an error: GitHub's rate budget ran out, the job recorded where it
 * stopped, and it will resume when the window reopens — so the card says so instead of showing
 * a failure.
 */
export function JobStatusCard({ jobId, intervalMs = 2000 }: JobStatusCardProps) {
  const { job, error, isLoading } = useJobPolling(jobId, intervalMs);

  if (jobId === null) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ingestion job #{jobId}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && job === null && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Waiting for the job to start…
          </p>
        )}

        {job !== null && (
          <div className="flex flex-col gap-3">
            <p className={`flex items-center gap-2 text-sm font-medium ${statusTone(job.status)}`}>
              {statusIcon(job.status)}
              <span>{statusLabel(job.status)}</span>
            </p>

            {job.status === "paused" && (
              <p className="text-sm text-muted-foreground">
                GitHub&apos;s rate limit paused the job. It resumes from where it stopped — the
                {job.cursor?.phase ? ` ${job.cursor.phase} ` : ""}
                phase is saved — no re-ingesting from scratch.
              </p>
            )}

            {job.status === "failed" && job.error !== null && (
              <p className="flex items-start gap-2 text-sm text-destructive">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <span>{job.error}</span>
              </p>
            )}

            {job.counts && Object.keys(job.counts).length > 0 && (
              <dl className="grid grid-cols-2 gap-1 text-sm text-muted-foreground sm:grid-cols-4">
                {COUNT_LABELS.map(([key, label]) => {
                  const value = job.counts?.[key];
                  if (value === undefined) return null;
                  return (
                    <div key={key} className="flex flex-col">
                      <dt>{label}</dt>
                      <dd className="font-mono text-foreground">{value}</dd>
                    </div>
                  );
                })}
              </dl>
            )}

            {error !== null && (
              <p className="text-sm text-muted-foreground">Polling error: {error}</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface JobStatusCardProps {
  jobId: number | null;
  /** Poll interval. Exposed so tests can poll immediately instead of waiting two seconds. */
  intervalMs?: number;
}

const COUNT_LABELS: ReadonlyArray<readonly [keyof IngestionCounts, string]> = [
  ["prs", "PRs"],
  ["issues", "Issues"],
  ["commits", "Commits"],
  ["releases", "Releases"],
  ["files", "Files"],
  ["reviews", "Reviews"],
  ["contributors", "Contributors"],
  ["api_calls", "API calls"],
];

function statusLabel(status: JobStatus): string {
  switch (status) {
    case "pending":
      return "Queued";
    case "running":
      return "Ingesting";
    case "paused":
      return "Paused — rate limited";
    case "succeeded":
      return "Completed";
    case "failed":
      return "Failed";
  }
}

function statusIcon(status: JobStatus) {
  const className = "h-4 w-4 shrink-0";
  switch (status) {
    case "pending":
    case "running":
      return <Loader2 className={`${className} animate-spin`} aria-hidden />;
    case "paused":
      return <PauseCircle className={className} aria-hidden />;
    case "succeeded":
      return <CheckCircle2 className={className} aria-hidden />;
    case "failed":
      return <AlertCircle className={className} aria-hidden />;
  }
}

function statusTone(status: JobStatus): string {
  switch (status) {
    case "pending":
    case "running":
    case "paused":
      return "text-muted-foreground";
    case "succeeded":
      return "text-success";
    case "failed":
      return "text-destructive";
  }
}
