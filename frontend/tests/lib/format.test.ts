import { describe, expect, it } from "vitest";

import { formatRelativeTime } from "@/lib/format";

describe("formatRelativeTime", () => {
  it("renders missing values as a dash, never as an empty string", () => {
    expect(formatRelativeTime(null)).toBe("—");
    expect(formatRelativeTime(undefined)).toBe("—");
    expect(formatRelativeTime("")).toBe("—");
    expect(formatRelativeTime("not-a-timestamp")).toBe("—");
  });

  it("renders moments ago as just now", () => {
    expect(formatRelativeTime(new Date().toISOString())).toBe("just now");
  });

  it("renders seconds, minutes, and hours relative to now", () => {
    const ago = (seconds: number) => new Date(Date.now() - seconds * 1000).toISOString();
    expect(formatRelativeTime(ago(30))).toBe("30s ago");
    expect(formatRelativeTime(ago(120))).toBe("2m ago");
    expect(formatRelativeTime(ago(60 * 60 * 3))).toBe("3h ago");
  });

  it("renders longer spans as days", () => {
    const ago = (days: number) => new Date(Date.now() - days * 86400 * 1000).toISOString();
    expect(formatRelativeTime(ago(3))).toBe("3d ago");
  });

  it("falls back to an absolute date beyond thirty days", () => {
    const fixed = "2026-01-15T09:30:00+00:00";
    const result = formatRelativeTime(fixed);
    // The exact locale wording varies; assert it is a calendar date, not a relative span.
    expect(result).not.toMatch(/ago$/);
    expect(result).toContain("2026");
  });

  it("accepts timestamps with or without an explicit offset", () => {
    expect(formatRelativeTime(new Date().toISOString().replace("Z", "+00:00"))).toBe("just now");
  });
});
