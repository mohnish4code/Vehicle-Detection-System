import type { ImageResult } from "../../lib/api";

type Tone = "green" | "amber" | "red" | "slate";

export function resultStatus(result: ImageResult): { label: string; tone: Tone } {
  switch (result.status) {
    case "ok":
      return result.plates.some((p) => p.needs_review)
        ? { label: "Needs review", tone: "amber" }
        : { label: "Plate found", tone: "green" };
    case "no_plate":
      return { label: "No plate", tone: "slate" };
    case "unreadable":
      return { label: "Unreadable", tone: "amber" };
    case "invalid_format":
      return { label: "Check text", tone: "amber" };
    case "error":
      return { label: "Failed", tone: "red" };
    default:
      return { label: "Rejected", tone: "red" };
  }
}

// Box colours, one per plate in an image
export const PLATE_COLORS = ["#4ade80", "#facc15", "#38bdf8", "#f472b6", "#fb923c"];

export function plateColor(i: number): string {
  return PLATE_COLORS[i % PLATE_COLORS.length]!;
}
