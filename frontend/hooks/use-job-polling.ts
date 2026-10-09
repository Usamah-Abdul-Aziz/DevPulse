"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { JobResponse } from "@/types";
import { JOB_TERMINAL_STATUSES } from "@/types";

/**
 * Polls a job until it reaches a terminal state.
 *
 * A rate-limited job pauses rather than fails, so the UI keeps polling a `paused` job — it will
 * resume on its own. The interval is cleared on terminal status and on unmount via the stored
 * timer, so a component that unmounts mid-poll never setState's after teardown.
 */
export function useJobPolling(jobId: number | null, intervalMs = 2000): JobPollingState {
  const [job, setJob] = useState<JobResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(jobId !== null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (jobId === null) {
      setJob(null);
      setError(null);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    const poll = async () => {
      try {
        const data = await api.getJob(jobId);
        if (cancelled) return;
        setJob(data);
        setIsLoading(false);
        if (JOB_TERMINAL_STATUSES.includes(data.status)) {
          stop();
          return;
        }
        timerRef.current = setTimeout(poll, intervalMs);
      } catch (problem) {
        if (cancelled) return;
        setIsLoading(false);
        setError(problem instanceof ApiError ? problem.message : "Unable to load the job.");
        // A transient failure should not silently stop the poll.
        timerRef.current = setTimeout(poll, intervalMs);
      }
    };

    poll();

    return () => {
      cancelled = true;
      stop();
    };
  }, [jobId, intervalMs, stop]);

  return { job, error, isLoading };
}

export interface JobPollingState {
  job: JobResponse | null;
  error: string | null;
  isLoading: boolean;
}
