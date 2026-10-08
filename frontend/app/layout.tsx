import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DevPulse — Software Engineering Intelligence",
  description:
    "Analyze GitHub development activity: project health, delivery risk, and engineering bottlenecks — with explanations a tech lead can act on.",
  metadataBase: new URL("https://devpulse.example.com"),
  openGraph: {
    title: "DevPulse — Software Engineering Intelligence",
    description:
      "Project health, PR risk prediction, and delivery analytics for public GitHub repositories.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        {children}
      </body>
    </html>
  );
}
