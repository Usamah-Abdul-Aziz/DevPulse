import Link from "next/link";
import { Activity } from "lucide-react";

export function Header() {
  return (
    <header className="border-b border-border bg-card/50 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <Activity className="h-5 w-5 text-primary" aria-hidden />
          DevPulse
        </Link>

        <nav className="flex items-center gap-6 text-sm text-muted-foreground">
          <Link href="/dashboard" className="font-medium text-foreground hover:text-primary">
            Dashboard
          </Link>
          <Link href="/repositories" className="hover:text-foreground">
            Repositories
          </Link>
          <Link href="/settings" className="hover:text-foreground">
            Settings
          </Link>
        </nav>
      </div>
    </header>
  );
}
