import { useHealth } from "../health";
import { CloudOffIcon, RefreshIcon, TerminalIcon } from "./icons";
import { btn, CopyButton, cx, Spinner } from "./ui";

const START_BACKEND = [
  { label: "Windows", command: "venv\\Scripts\\uvicorn main:app --reload" },
  { label: "macOS / Linux", command: "venv/bin/uvicorn main:app --reload" },
];

/**
 * Shown on every page while the API can't be reached at all, with what to do about it.
 * The health check retries every few seconds, so this disappears by itself once the backend is up.
 */
export function OfflineBanner() {
  const { offline, errorCode, error, refresh, loading } = useHealth();
  if (!offline) return null;

  const wrongServer = errorCode === "NOT_THE_API";

  return (
    <section
      role="alert"
      className="mb-6 animate-fade-up overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-rose-200"
    >
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start">
        <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-rose-50 text-rose-600">
          <CloudOffIcon className="size-6" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-slate-900">
            {wrongServer ? "This page isn't talking to the backend" : "The backend isn't running"}
          </h2>
          <p className="mt-1 text-sm text-slate-600">{error}</p>

          {!wrongServer && (
            <div className="mt-4 space-y-2">
              {START_BACKEND.map(({ label, command }) => (
                <div key={label}>
                  <p className="mb-1 text-xs font-medium text-slate-500">{label}, from the project folder:</p>
                  <div className="flex items-center gap-2 rounded-xl bg-slate-900 py-1.5 pl-3 pr-1.5 text-slate-100">
                    <TerminalIcon className="size-4 shrink-0 text-slate-400" />
                    <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap text-xs">{command}</code>
                    <CopyButton value={command} label="Copy command" className="text-slate-400 hover:bg-slate-800 hover:text-white" />
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button type="button" className={cx(btn.base, btn.secondary, "py-2")} onClick={refresh}>
              {loading ? <Spinner className="size-4" /> : <RefreshIcon className="size-4" />} Retry now
            </button>
            <span className="flex items-center gap-2 text-xs text-slate-500">
              <span className="size-1.5 animate-soft-pulse rounded-full bg-slate-400" /> Reconnecting automatically…
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
