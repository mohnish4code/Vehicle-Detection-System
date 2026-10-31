import { useEffect, useRef, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { useHealth } from "../health";
import { ListIcon, ScanIcon } from "./icons";
import { cx } from "./ui";

type State = "ok" | "down" | "unknown";

function StatusPill({ label, state, detail }: { label: string; state: State; detail: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [open]);

  const dot = { ok: "bg-emerald-500", down: "bg-rose-500", unknown: "bg-slate-300" }[state];

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
        aria-expanded={open}
        aria-label={`${label}: ${detail}`}
      >
        <span className={cx("size-2 rounded-full", dot, state === "unknown" && "animate-pulse")} />
        {label}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-2 w-64 rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-700 shadow-lg">
          <p className="font-medium text-slate-900">{label}</p>
          <p className="mt-1">{detail}</p>
        </div>
      )}
    </div>
  );
}

function useStatuses(): Record<"model" | "sheets", [State, string]> {
  const { health, error, loading } = useHealth();
  if (loading && !health) {
    return { model: ["unknown", "Checking…"], sheets: ["unknown", "Checking…"] };
  }
  if (!health) {
    const msg = error ?? "Can't reach the server.";
    return { model: ["down", msg], sheets: ["down", msg] };
  }
  return {
    model: health.model.ok ? ["ok", "Detection model loaded."] : ["down", health.model.error ?? "Model not loaded."],
    sheets: health.sheets.ok ? ["ok", "Connected to Google Sheets."] : ["down", health.sheets.error ?? "Not connected."],
  };
}

const navLink = ({ isActive }: { isActive: boolean }) =>
  cx(
    "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition",
    isActive ? "bg-slate-100 text-slate-900" : "text-slate-600 hover:text-slate-900",
  );

export function Header() {
  const { model, sheets } = useStatuses();

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4">
        <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight text-slate-900">
          <img src="/favicon.svg" alt="" className="size-7" />
          <span className="hidden min-[380px]:inline">Vehicle Tracker</span>
        </Link>
        <nav className="hidden items-center gap-1 sm:flex">
          <NavLink to="/" end className={navLink}>
            <ScanIcon /> Scan
          </NavLink>
          <NavLink to="/logs" className={navLink}>
            <ListIcon /> Logs
          </NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <StatusPill label="Model" state={model[0]} detail={model[1]} />
          <StatusPill label="Sheets" state={sheets[0]} detail={sheets[1]} />
        </div>
      </div>
    </header>
  );
}

/** Bottom tab bar on phones, where the top nav is hidden */
export function MobileNav() {
  const tab = ({ isActive }: { isActive: boolean }) =>
    cx("flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium", isActive ? "text-slate-900" : "text-slate-500");
  return (
    <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] sm:hidden">
      <NavLink to="/" end className={tab}>
        <ScanIcon className="size-6" /> Scan
      </NavLink>
      <NavLink to="/logs" className={tab}>
        <ListIcon className="size-6" /> Logs
      </NavLink>
    </nav>
  );
}
