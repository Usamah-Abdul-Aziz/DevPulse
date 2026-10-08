import { describe, expect, it } from "vitest";
import { formatHours, formatPercent, healthBand } from "@/lib/utils";

describe("formatHours", () => {
  it("renders sub-hour durations in minutes", () => {
    expect(formatHours(0.5)).toBe("30m");
    expect(formatHours(0.02)).toBe("1m");
  });

  it("renders hours under two days with one decimal", () => {
    expect(formatHours(36)).toBe("36.0h");
  });

  it("renders durations of two days or more as days", () => {
    expect(formatHours(72)).toBe("3.0d");
  });

  it("renders missing data as a dash, never as NaN", () => {
    expect(formatHours(null)).toBe("—");
    expect(formatHours(undefined)).toBe("—");
    expect(formatHours(Number.NaN)).toBe("—");
  });
});

describe("formatPercent", () => {
  it("multiplies by 100 and rounds to the requested precision", () => {
    expect(formatPercent(0.1234)).toBe("12.3%");
    expect(formatPercent(0.1234, 2)).toBe("12.34%");
  });

  it("renders missing data as a dash", () => {
    expect(formatPercent(null)).toBe("—");
  });
});

describe("healthBand", () => {
  it("maps scores to the bands defined in docs/metrics.md", () => {
    expect(healthBand(95)).toBe("healthy");
    expect(healthBand(80)).toBe("healthy");
    expect(healthBand(79.9)).toBe("watch");
    expect(healthBand(60)).toBe("watch");
    expect(healthBand(59.9)).toBe("at-risk");
    expect(healthBand(0)).toBe("at-risk");
  });
});
