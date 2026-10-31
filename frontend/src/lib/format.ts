export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : `${Math.round(value * 100)}%`;
}

export function duration(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** Backend timestamps are "YYYY-MM-DD HH:MM:SS" in IST */
export function parseIst(timestamp: string): Date | null {
  const d = new Date(`${timestamp.replace(" ", "T")}+05:30`);
  return Number.isNaN(d.getTime()) ? null : d;
}

const dateFmt = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Asia/Kolkata",
});

export function formatIst(timestamp: string): string {
  const d = parseIst(timestamp);
  return d ? dateFmt.format(d) : timestamp || "–";
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
