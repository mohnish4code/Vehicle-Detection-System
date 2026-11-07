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
  const ring = { ok: "ring-emerald-500/30", down: "ring-rose-500/30", unknown: "ring-slate-300/40" }[state];

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-50"
        aria-expanded={open}
        aria-label={`${label}: ${detail}`}
      >
        <span className={cx("relative flex size-2")}>
          {state === "ok" && <span className={cx("absolute inline-flex size-full animate-ping rounded-full opacity-40", dot)} />}
          <span className={cx("relative size-2 rounded-full ring-4", dot, ring, state === "unknown" && "animate-pulse")} />
        </span>
        {label}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-2 w-64 animate-fade-up rounded-xl bg-white p-3 text-sm text-slate-700 shadow-lg ring-1 ring-slate-200">
          <p className="font-semibold text-slate-900">{label}</p>
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
    const msg = error ?? "Can't reach the backend.";
    return { model: ["down", msg], sheets: ["down", msg] };
  }
  return {
    model: health.model.ok ? ["ok", "Detection model loaded."] : ["down", health.model.error ?? "Model not loaded."],
    sheets: health.sheets.ok ? ["ok", "Connected to Google Sheets."] : ["down", health.sheets.error ?? "Not connected."],
  };
}

const navLink = ({ isActive }: { isActive: boolean }) =>
  cx(
    "flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold transition",
    isActive ? "bg-slate-900 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
  );

export function Header() {
  const { model, sheets } = useStatuses();

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200/70 bg-white/75 backdrop-blur-lg">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4">
        <Link to="/" className="group flex items-center gap-2.5">
          <img src="/favicon.svg" alt="" className="size-8 transition group-hover:rotate-[-6deg]" />
          <span className="hidden flex-col leading-tight min-[380px]:flex">
            <span className="text-[15px] font-bold tracking-tight text-slate-900">Vehicle Tracker</span>
            <span className="text-[11px] font-medium text-slate-500">Number plate recognition</span>
          </span>
        </Link>
        <nav className="ml-4 hidden items-center gap-1 sm:flex">
          <NavLink to="/" end className={navLink}>
            <ScanIcon className="size-4" /> Scan
          </NavLink>
          <NavLink to="/logs" className={navLink}>
            <ListIcon className="size-4" /> Log
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
    cx(
      "flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-semibold transition",
      isActive ? "text-indigo-600" : "text-slate-500",
    );
  return (
    <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-slate-200 bg-white/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-lg sm:hidden">
      <NavLink to="/" end className={tab}>
        <ScanIcon className="size-6" /> Scan
      </NavLink>
      <NavLink to="/logs" className={tab}>
        <ListIcon className="size-6" /> Log
      </NavLink>
    </nav>
  );
}
