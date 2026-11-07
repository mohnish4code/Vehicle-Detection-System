import type { LogEntry } from "./api";

const COLUMNS: [keyof LogEntry, string][] = [
  ["plate", "Plate"],
  ["timestamp", "Timestamp (IST)"],
  ["source", "Source"],
  ["det_conf", "Detection Conf"],
  ["ocr_conf", "OCR Conf"],
  ["format", "Format"],
];

function cell(value: unknown): string {
  let s = value === null || value === undefined ? "" : String(value);
  // Stop spreadsheet apps from running cell contents as formulas
  if (/^[=+\-@]/.test(s)) s = `'${s}`;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(rows: LogEntry[]): string {
  const lines = [COLUMNS.map(([, label]) => label).join(",")];
  for (const row of rows) lines.push(COLUMNS.map(([key]) => cell(row[key])).join(","));
  return lines.join("\r\n") + "\r\n";
}

export function downloadCsv(rows: LogEntry[], filename: string) {
  const blob = new Blob(["﻿" + toCsv(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
