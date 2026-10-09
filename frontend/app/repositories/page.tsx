"use client";

import { useCallback, useEffect, useState } from "react";

import { ConnectForm } from "@/components/repositories/connect-form";
import { JobStatusCard } from "@/components/repositories/job-status-card";
import { RepositoryCard } from "@/components/repositories/repository-card";
import { api, ApiError } from "@/lib/api";
import type { ConnectResponse, RepositorySummary } from "@/types";

/**
 * The repositories page: the Phase 2 slice.
 *
 * Connect is fire-and-forget from the UI's point of view — the endpoint answers 202 and the job
 * card polls until it lands. That is deliberate (AGENTS.md): nothing about ingestion may block a
 * request, so nothing about ingestion may block a render either.
 */
export default function RepositoriesPage() {
  const [repositories, setRepositories] = useState<RepositorySummary[]>([]);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const page = await api.listRepositories();
      setRepositories(page.items);
      setError(null);
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : "Unable to load repositories.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleConnected = useCallback(
    async (response: ConnectResponse) => {
      // The job is what the user actually wants to watch, so start polling it immediately.
      setActiveJobId(response.job_id);
      // The list re-fetch picks up the real row, with its id and sync timestamp.
      await load();
    },
    [load],
  );

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Repositories</h1>
        <p className="text-sm text-muted-foreground">
          Connect a public GitHub repository to ingest its pull requests, issues, commits, and
          releases.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-card p-6">
        <ConnectForm onConnected={handleConnected} />
      </div>

      <JobStatusCard jobId={activeJobId} />

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Connected</h2>

        {error !== null ? (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}

        {isLoading && repositories.length === 0 ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : repositories.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No repositories connected yet. Connect one above to see it here.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {repositories.map((repository) => (
              <RepositoryCard key={repository.id} repository={repository} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
