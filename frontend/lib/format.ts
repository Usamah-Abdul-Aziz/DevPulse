/**
 * Presentation formatting for timestamps and durations.
 *
 * Timestamps always carry a timezone offset from the API (docs/api.md); rendering a naive string
 * here would silently drop the offset.
 */

const formatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

/**
 * A timestamp rendered relative to now ("3h ago"), falling back to an absolute date.
 *
 * Returns the em dash for missing values rather than an empty string, so a column of them stays
 * aligned and a blank never reads as "just now".
 */
export function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return "—";

  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return "—";

  const secondsAgo = Math.round((Date.now() - timestamp) / 1000);
  if (secondsAgo < 5) return "just now";
  if (secondsAgo < 60) return `${secondsAgo}s ago`;

  const minutesAgo = Math.round(secondsAgo / 60);
  if (minutesAgo < 60) return `${minutesAgo}m ago`;

  const hoursAgo = Math.round(minutesAgo / 60);
  if (hoursAgo < 48) return `${hoursAgo}h ago`;

  const daysAgo = Math.round(hoursAgo / 24);
  if (daysAgo < 30) return `${daysAgo}d ago`;

  return formatter.format(timestamp);
}
