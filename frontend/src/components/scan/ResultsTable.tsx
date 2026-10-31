import type { ImageResult } from "../../lib/api";
import { duration } from "../../lib/format";
import { prettyPlate } from "../../lib/plate";
import { Badge, Card, cx } from "../ui";
import { resultStatus } from "./status";

export interface Row {
  id: string;
  url: string;
  result: ImageResult;
  texts: string[];
}

interface Props {
  rows: Row[];
  selected: string | null;
  onSelect: (id: string) => void;
}

function Plates({ texts }: { texts: string[] }) {
  const shown = texts.filter(Boolean);
  if (!shown.length) return <span className="text-slate-400">—</span>;
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-1">
      {shown.map((t, i) => (
        <span key={i} className="font-mono font-semibold tracking-wide text-slate-900">
          {prettyPlate(t)}
        </span>
      ))}
    </span>
  );
}

export function ResultsTable({ rows, selected, onSelect }: Props) {
  return (
    <Card className="overflow-hidden">
      {/* Phones: one tappable card per image */}
      <ul className="divide-y divide-slate-100 sm:hidden">
        {rows.map((row) => {
          const status = resultStatus(row.result);
          return (
            <li key={row.id}>
              <button
                type="button"
                onClick={() => onSelect(row.id)}
                className={cx("flex w-full items-center gap-3 p-3 text-left", selected === row.id && "bg-slate-50")}
              >
                <img src={row.url} alt="" className="size-14 shrink-0 rounded-lg bg-slate-100 object-cover" />
                <div className="min-w-0 flex-1">
                  <Plates texts={row.texts} />
                  <p className="mt-0.5 truncate text-xs text-slate-500">{row.result.filename}</p>
                </div>
                <Badge tone={status.tone}>{status.label}</Badge>
              </button>
            </li>
          );
        })}
      </ul>

      {/* Larger screens: a proper table */}
      <table className="hidden w-full text-left text-sm sm:table">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">Image</th>
            <th className="px-4 py-3">Plates</th>
            <th className="px-4 py-3">Detection</th>
            <th className="px-4 py-3">OCR</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3 text-right">Time</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => {
            const status = resultStatus(row.result);
            const best = row.result.plates[0];
            return (
              <tr
                key={row.id}
                onClick={() => onSelect(row.id)}
                className={cx("cursor-pointer transition hover:bg-slate-50", selected === row.id && "bg-sky-50/60")}
              >
                <td className="px-4 py-3">
                  <button type="button" className="flex items-center gap-3 text-left" onClick={() => onSelect(row.id)}>
                    <img src={row.url} alt="" className="h-10 w-14 rounded-md bg-slate-100 object-cover" />
                    <span className="max-w-40 truncate text-slate-700">{row.result.filename}</span>
                  </button>
                </td>
                <td className="px-4 py-3">
                  <Plates texts={row.texts} />
                </td>
                <td className="px-4 py-3 tabular-nums text-slate-700">
                  {best ? `${Math.round(best.det_conf * 100)}%` : "—"}
                </td>
                <td className="px-4 py-3 tabular-nums text-slate-700">
                  {best ? `${Math.round(best.ocr_conf * 100)}%` : "—"}
                </td>
                <td className="px-4 py-3">
                  <Badge tone={status.tone}>{status.label}</Badge>
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-500">{duration(row.result.processing_ms)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
