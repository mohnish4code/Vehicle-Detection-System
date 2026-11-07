import type { ImageResult } from "../../lib/api";
import { duration } from "../../lib/format";
import { Badge, Card, cx, NumberPlate } from "../ui";
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
  if (!shown.length) return <span className="text-sm text-slate-400">No plate</span>;
  return (
    <span className="flex flex-wrap gap-1.5">
      {shown.map((t, i) => (
        <NumberPlate key={i} text={t} size="sm" />
      ))}
    </span>
  );
}

export function ResultsTable({ rows, selected, onSelect }: Props) {
  return (
    <Card className="animate-fade-up overflow-hidden">
      {/* Phones: one tappable card per image */}
      <ul className="divide-y divide-slate-100 sm:hidden">
        {rows.map((row) => {
          const status = resultStatus(row.result);
          return (
            <li key={row.id}>
              <button
                type="button"
                onClick={() => onSelect(row.id)}
                className={cx(
                  "flex w-full items-center gap-3 p-3 text-left transition",
                  selected === row.id ? "bg-indigo-50/70" : "active:bg-slate-50",
                )}
              >
                <img src={row.url} alt="" className="size-14 shrink-0 rounded-lg bg-slate-100 object-cover" />
                <div className="min-w-0 flex-1">
                  <Plates texts={row.texts} />
                  <p className="mt-1 truncate text-xs text-slate-500">{row.result.filename}</p>
                </div>
                <Badge tone={status.tone}>{status.label}</Badge>
              </button>
            </li>
          );
        })}
      </ul>

      {/* Larger screens: a proper table */}
      <table className="hidden w-full text-left text-sm sm:table">
        <thead className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">Image</th>
            <th className="px-4 py-3">Plates</th>
            <th className="px-4 py-3 text-right">Detection</th>
            <th className="px-4 py-3 text-right">OCR</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3 text-right">Time</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => {
            const status = resultStatus(row.result);
            const best = row.result.plates[0];
            const isSelected = selected === row.id;
            return (
              <tr
                key={row.id}
                onClick={() => onSelect(row.id)}
                className={cx(
                  "cursor-pointer transition",
                  isSelected ? "bg-indigo-50/70 shadow-[inset_3px_0_0_rgb(79_70_229)]" : "hover:bg-slate-50",
                )}
              >
                <td className="px-4 py-3">
                  <button type="button" className="flex items-center gap-3 text-left" onClick={() => onSelect(row.id)}>
                    <img src={row.url} alt="" className="h-10 w-16 rounded-md bg-slate-100 object-cover ring-1 ring-slate-200" />
                    <span className="max-w-40 truncate text-slate-700">{row.result.filename}</span>
                  </button>
                </td>
                <td className="px-4 py-3">
                  <Plates texts={row.texts} />
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                  {best ? `${Math.round(best.det_conf * 100)}%` : "—"}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-700">
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
