import Link from "next/link";
import { Activity, ArrowRight, Github, ShieldCheck } from "lucide-react";

export default function LandingPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col items-center justify-center gap-12 px-6 py-16">
      <div className="flex flex-col items-center gap-6 text-center">
        <div className="flex items-center gap-3 rounded-full border border-border bg-card px-4 py-1.5 text-sm text-muted-foreground">
          <Activity className="h-4 w-4 text-primary" aria-hidden />
          <span>Engineering analytics for public GitHub repos</span>
        </div>

        <h1 className="max-w-3xl text-balance text-4xl font-bold tracking-tight sm:text-5xl">
          What is happening in your project — and what should you investigate?
        </h1>

        <p className="max-w-2xl text-pretty text-lg text-muted-foreground">
          DevPulse turns raw GitHub activity into project health scores, delivery-risk signals, and
          explainable PR risk predictions — built for the Monday-morning triage.
        </p>

        <div className="flex flex-col gap-3 sm:flex-row">
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3 font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Try Live Demo
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
          <Link
            href="https://github.com/your-org/devpulse"
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-card px-6 py-3 font-medium transition-colors hover:bg-accent"
          >
            <Github className="h-4 w-4" aria-hidden />
            View on GitHub
          </Link>
        </div>

        <p className="text-sm text-muted-foreground">
          No login and no ingestion wait — the demo opens a pre-analyzed repository instantly.
        </p>
      </div>

      <div className="grid w-full gap-4 sm:grid-cols-3">
        {[
          {
            icon: Activity,
            title: "Delivery metrics",
            body: "Cycle time decomposed into pickup, review, and merge delay — p50 and p85, per week.",
          },
          {
            icon: ShieldCheck,
            title: "Health score",
            body: "A transparent, rule-based 0–100 score with every component and threshold visible.",
          },
          {
            icon: ArrowRight,
            title: "PR risk, explained",
            body: "At PR-open time, with SHAP factors ranked and signed — never a black-box score.",
          },
        ].map(({ icon: Icon, title, body }) => (
          <div
            key={title}
            className="flex flex-col gap-2 rounded-lg border border-border bg-card p-5 text-left"
          >
            <Icon className="h-5 w-5 text-primary" aria-hidden />
            <h2 className="font-semibold">{title}</h2>
            <p className="text-sm text-muted-foreground">{body}</p>
          </div>
        ))}
      </div>
    </main>
  );
}
