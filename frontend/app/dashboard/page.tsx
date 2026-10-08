import { Header } from "@/components/layout/header";
import { ApiStatusCard } from "@/components/dashboard/api-status-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Dashboard skeleton (Phase 1).
 *
 * Right now this only proves the frontend can reach the backend. Real screens
 * land phase by phase: metrics (Phase 3), health (Phase 4), PR risk (Phase 8).
 */
export default function DashboardPage() {
  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-8 flex flex-col gap-1">
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">
            Analytics screens arrive with Phases 3–8. This page currently verifies the API
            connection.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <ApiStatusCard />

          <Card className="sm:col-span-2">
            <CardHeader>
              <CardTitle>Roadmap</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-2 text-sm text-muted-foreground">
                <li>Phase 2 — GitHub ingestion (async jobs)</li>
                <li>Phase 3 — Engineering metrics + demo repository</li>
                <li>Phase 4 — Project health score</li>
                <li>Phase 5–8 — PR risk: rules, dataset, model, SHAP</li>
              </ol>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
