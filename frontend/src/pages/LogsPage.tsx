import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import {
  AlertIcon,
  CalendarIcon,
  ClockIcon,
  CloudOffIcon,
  DownloadIcon,
  ListIcon,
  PlateIcon,
  RefreshIcon,
  SearchIcon,
} from "../components/icons";
import { Badge, btn, Card, CopyButton, cx, EmptyState, NumberPlate, Spinner, Stat } from "../components/ui";
import { api, ApiError, isAbort, OFFLINE_CODES, type LogEntry } from "../lib/api";
import { downloadCsv } from "../lib/csv";
import { formatIst, parseIst, percent, todayIso } from "../lib/format";
import { plateFormat } from "../lib/plate";

type Period = "all" | "today" | "7d" | "30d";

const PERIODS: Record<Period, string> = { all: "All time", today: "Today", "7d": "Last 7 days", "30d": "Last 30 days" };
const LIMIT = 1000;

function inPeriod(entry: LogEntry, period: Period): boolean {
  if (period === "all") return true;
  const time = parseIst(entry.timestamp);
  if (!time) return false;
  if (period === "today") {
    const day = (d: Date) => d.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
    return day(time) === day(new Date());
  }
  const days = period === "7d" ? 7 : 30;
  return Date.now() - time.getTime() <= days * 86_400_000;
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

const select =
  "rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 shadow-sm outline-none transition focus:border-indigo-400 focus:ring-4 focus:ring-indigo-100";

function FormatBadge({ format, plate }: { format: string | null; plate: string }) {
  // rows from the old app have no format column, so work it out from the text
  format = format ?? plateFormat(plate);
  if (format === "bh") return <Badge tone="blue">BH series</Badge>;
  if (format === "standard") return <Badge>Standard</Badge>;
  return <span className="text-slate-400">–</span>;
}

const SOURCES: Record<string, string> = { camera: "Camera", upload: "Upload", streamlit_capture: "Old app" };

function SourceLabel({ source }: { source: string }) {
  return <span className="text-slate-600">{SOURCES[source] ?? (source || "–")}</span>;
}

function PlateCell({ plate }: { plate: string }) {
  return (
    <span className="group/plate flex items-center gap-1">
      <NumberPlate text={plate} size="sm" />
      <CopyButton value={plate} label="Copy plate" className="opacity-0 transition group-hover/plate:opacity-100 focus:opacity-100" />
    </span>
  );
}

function relativeTime(timestamp: string | undefined): string {
  const t = timestamp ? parseIst(timestamp) : null;
  if (!t) return "–";
  const mins = Math.round((Date.now() - t.getTime()) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days < 30 ? `${days} day${days === 1 ? "" : "s"} ago` : formatIst(timestamp!).split(",")[0]!;
}

function Stats({ rows, total }: { rows: LogEntry[]; total: number }) {
  const today = rows.filter((r) => inPeriod(r, "today")).length;
  const week = rows.filter((r) => inPeriod(r, "7d")).length;
  const unique = new Set(rows.map((r) => r.plate)).size;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Stat icon={<ListIcon className="size-5" />} label="Plates logged" value={total} hint="all time" />
      <Stat icon={<CalendarIcon className="size-5" />} label="Today" value={today} hint={`${week} this week`} />
      <Stat icon={<PlateIcon className="size-5" />} label="Different vehicles" value={unique} hint="unique plates" />
      <Stat icon={<ClockIcon className="size-5" />} label="Last saved" value={relativeTime(rows[0]?.timestamp)} hint={rows[0] ? rows[0].plate : undefined} />
    </div>
  );
}

export function LogsPage() {
  const [query, setQuery] = useState("");
  const [format, setFormat] = useState("");
  const [source, setSource] = useState("");
  const [period, setPeriod] = useState<Period>("all");
  const [rows, setRows] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const q = useDebounced(query, 300);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    api
      .logs({ q, format, source, limit: LIMIT }, ctrl.signal)
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
        setError(null);
      })
      .catch((e) => {
        if (isAbort(e)) return;
        setError(e instanceof ApiError ? e : new ApiError("UNKNOWN", 0, "Couldn't load the log."));
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [q, format, source, reloadKey]);

  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);
  const visible = useMemo(() => rows.filter((r) => inPeriod(r, period)), [rows, period]);
  const filtered = Boolean(query || format || source || period !== "all");

  function exportCsv() {
    downloadCsv(visible, `plate-log-${todayIso()}.csv`);
    toast.success(`Downloaded ${visible.length} row${visible.length === 1 ? "" : "s"}`);
  }

  function clearFilters() {
    setQuery("");
    setFormat("");
    setSource("");
    setPeriod("all");
  }

  let body;
  if (error && OFFLINE_CODES.has(error.code)) {
    // the banner at the top of the page explains how to start the backend
    body = (
      <EmptyState
        tone="red"
        icon={<CloudOffIcon />}
        title="Waiting for the backend"
        message="The log loads as soon as the backend is running."
      />
    );
  } else if (error) {
    const notSetUp = error.code === "SHEETS_NOT_CONFIGURED";
    body = (
      <EmptyState
        tone={notSetUp ? "amber" : "red"}
        icon={error.code === "NETWORK" || error.code.startsWith("SHEETS") ? <CloudOffIcon /> : <AlertIcon />}
        title={notSetUp ? "Google Sheets isn't connected" : "Couldn't load the log"}
        message={notSetUp ? `${error.message} Plates can still be scanned, but nothing is logged until it's set up.` : error.message}
        action={
          <button type="button" className={cx(btn.base, btn.secondary)} onClick={refresh}>
            <RefreshIcon /> Try again
          </button>
        }
      />
    );
  } else if (loading && !rows.length) {
    body = (
      <div className="divide-y divide-slate-100" aria-busy="true">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="flex animate-pulse items-center gap-4 px-4 py-4">
            <div className="h-4 w-28 rounded bg-slate-200" />
            <div className="h-3 w-36 rounded bg-slate-100" />
            <div className="ml-auto h-3 w-14 rounded bg-slate-100" />
          </div>
        ))}
      </div>
    );
  } else if (!visible.length) {
    body = filtered ? (
      <EmptyState
        icon={<SearchIcon />}
        title="No matching plates"
        message="Try a different search or clear the filters."
        action={
          <button type="button" className={cx(btn.base, btn.secondary)} onClick={clearFilters}>
            Clear filters
          </button>
        }
      />
    ) : (
      <EmptyState
        icon={<ListIcon />}
        title="No plates logged yet"
        message="Scan a plate and press “Save to log”. It will show up here."
      />
    );
  } else {
    body = (
      <>
        <ul className="divide-y divide-slate-100 md:hidden">
          {visible.map((r, i) => (
            <li key={`${r.plate}-${r.timestamp}-${i}`} className="flex items-start justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <PlateCell plate={r.plate} />
                <p className="mt-1 text-xs text-slate-500">
                  {formatIst(r.timestamp)} · <SourceLabel source={r.source} />
                </p>
              </div>
              <div className="flex flex-col items-end gap-1">
                <FormatBadge format={r.format} plate={r.plate} />
                <span className="text-xs tabular-nums text-slate-500">OCR {percent(r.ocr_conf)}</span>
              </div>
            </li>
          ))}
        </ul>
        <table className="hidden w-full text-left text-sm md:table">
          <thead className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Plate</th>
              <th className="px-4 py-3">Time (IST)</th>
              <th className="px-4 py-3">Source</th>
              <th className="px-4 py-3 text-right">Detection</th>
              <th className="px-4 py-3 text-right">OCR</th>
              <th className="px-4 py-3">Format</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {visible.map((r, i) => (
              <tr key={`${r.plate}-${r.timestamp}-${i}`} className="transition hover:bg-indigo-50/40">
                <td className="px-4 py-2.5">
                  <PlateCell plate={r.plate} />
                </td>
                <td className="px-4 py-3 text-slate-700">{formatIst(r.timestamp)}</td>
                <td className="px-4 py-3">
                  <SourceLabel source={r.source} />
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-700">{percent(r.det_conf)}</td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-700">{percent(r.ocr_conf)}</td>
                <td className="px-4 py-3">
                  <FormatBadge format={r.format} plate={r.plate} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Plate log</h1>
          <p className="mt-1 text-sm text-slate-600">Every plate saved to Google Sheets, newest first.</p>
        </div>
        <div className="flex gap-2">
          <button type="button" className={cx(btn.base, btn.secondary)} onClick={refresh} disabled={loading}>
            {loading ? <Spinner className="size-4" /> : <RefreshIcon className="size-4" />}
            <span className="hidden sm:inline">Refresh</span>
          </button>
          <button
            type="button"
            className={cx(btn.base, btn.primary)}
            onClick={exportCsv}
            disabled={!visible.length || !!error}
          >
            <DownloadIcon className="size-4" /> CSV
          </button>
        </div>
      </div>

      {!error && rows.length > 0 && !filtered && <Stats rows={rows} total={total} />}

      <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto_auto]">
        <label className="relative">
          <span className="sr-only">Search plates</span>
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search plate, e.g. MH12"
            autoCapitalize="characters"
            className={cx(select, "w-full pl-9 uppercase placeholder:normal-case")}
          />
        </label>
        <div className="grid grid-cols-3 gap-2 sm:contents">
          <select aria-label="Format" value={format} onChange={(e) => setFormat(e.target.value)} className={select}>
            <option value="">All formats</option>
            <option value="standard">Standard</option>
            <option value="bh">BH series</option>
          </select>
          <select aria-label="Source" value={source} onChange={(e) => setSource(e.target.value)} className={select}>
            <option value="">All sources</option>
            <option value="camera">Camera</option>
            <option value="upload">Upload</option>
          </select>
          <select
            aria-label="Period"
            value={period}
            onChange={(e) => setPeriod(e.target.value as Period)}
            className={select}
          >
            {Object.entries(PERIODS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <Card className="overflow-hidden">{body}</Card>

      {!error && visible.length > 0 && (
        <p className="text-xs text-slate-500">
          Showing {visible.length} of {total} logged plate{total === 1 ? "" : "s"}
          {total > LIMIT && ` (latest ${LIMIT} loaded)`}.
        </p>
      )}
    </div>
  );
}
