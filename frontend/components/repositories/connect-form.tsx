"use client";

import { useState } from "react";
import { Loader2, Plug } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import type { ConnectResponse } from "@/types";

/**
 * The connect form.
 *
 * Accepts `owner/name`, a GitHub URL, or a trailing slash — the backend normalises all of them.
 * It does not retry on its own: a duplicate connect returns the existing job id (202), so a
 * second submit *is* the retry.
 */
export function ConnectForm({ onConnected }: ConnectFormProps) {
  const [repository, setRepository] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const value = repository.trim();
    if (!value) {
      setError("Enter a repository as owner/name.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const response = await api.connectRepository(value);
      onConnected(response);
      setRepository("");
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : "Unable to connect the repository.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <label htmlFor="repository" className="text-sm font-medium">
        Connect a public repository
      </label>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Plug
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <input
            id="repository"
            name="repository"
            type="text"
            placeholder="fastapi/fastapi"
            autoComplete="off"
            spellCheck={false}
            value={repository}
            onChange={(event) => setRepository(event.target.value)}
            className="w-full rounded-md border border-border bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled={isSubmitting}
          />
        </div>
        <button
          type="submit"
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          disabled={isSubmitting}
        >
          {isSubmitting ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Plug className="h-4 w-4" aria-hidden />
          )}
          Connect
        </button>
      </div>

      {error !== null && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      <p className="text-xs text-muted-foreground">
        Only repositories listed in <code className="font-mono">ALLOWED_REPOS</code> can be
        connected. Ingestion runs in the background and resumes automatically if it hits a GitHub
        rate limit.
      </p>
    </form>
  );
}

interface ConnectFormProps {
  /** Called with the accepted-connect reply so the caller can start watching the job. */
  onConnected: (response: ConnectResponse) => void;
}
