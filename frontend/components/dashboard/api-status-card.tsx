"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import type { HealthResponse } from "@/types";

type State =
  | { status: "loading" }
  | { status: "ok"; data: HealthResponse }
  | { status: "error"; message: string };

/**
 * The walking-skeleton check: can the deployed frontend actually reach the
 * deployed backend? Renders on the dashboard so the connection is verifiable
 * in production, not just locally.
 */
export function ApiStatusCard() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((data) => !cancelled && setState({ status: "ok", data }))
      .catch((error: unknown) => {
        if (cancelled) return;
        const message =
          error instanceof ApiError ? error.message : "Unable to reach the API";
        setState({ status: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>API connection</CardTitle>
      </CardHeader>
      <CardContent>
        {state.status === "loading" && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Checking backend…
          </p>
        )}

        {state.status === "ok" && (
          <div className="flex flex-col gap-2">
            <p className="flex items-center gap-2 text-sm font-medium text-success">
              <CheckCircle2 className="h-4 w-4" aria-hidden />
              Connected
            </p>
            <dl className="grid grid-cols-2 gap-1 text-sm text-muted-foreground">
              <dt>Service</dt>
              <dd className="font-mono text-foreground">{state.data.service}</dd>
              <dt>Version</dt>
              <dd className="font-mono text-foreground">{state.data.version}</dd>
              <dt>Environment</dt>
              <dd className="font-mono text-foreground">{state.data.environment}</dd>
            </dl>
          </div>
        )}

        {state.status === "error" && (
          <p className="flex items-center gap-2 text-sm font-medium text-destructive">
            <XCircle className="h-4 w-4 shrink-0" aria-hidden />
            <span>{state.message}</span>
          </p>
        )}
      </CardContent>
    </Card>
  );
}
