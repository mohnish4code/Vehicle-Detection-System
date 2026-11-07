import { useState, type ReactNode } from "react";
import toast from "react-hot-toast";
import { plateFormat, prettyPlate } from "../lib/plate";
import { CheckIcon, CopyIcon } from "./icons";

export const btn = {
  base: "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-50 active:scale-[0.98]",
  primary:
    "bg-indigo-600 text-white shadow-sm shadow-indigo-600/30 hover:bg-indigo-500 active:bg-indigo-700 disabled:shadow-none",
  dark: "bg-slate-900 text-white shadow-sm hover:bg-slate-800 active:bg-slate-950",
  secondary: "bg-white text-slate-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 active:bg-slate-100",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
};

export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

type Tone = "green" | "amber" | "red" | "slate" | "blue" | "indigo";

const tones: Record<Tone, string> = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  amber: "bg-amber-50 text-amber-800 ring-amber-600/25",
  red: "bg-rose-50 text-rose-700 ring-rose-600/20",
  slate: "bg-slate-100 text-slate-700 ring-slate-500/20",
  blue: "bg-sky-50 text-sky-700 ring-sky-600/20",
  indigo: "bg-indigo-50 text-indigo-700 ring-indigo-600/20",
};

export function Badge({ tone = "slate", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}

export function Spinner({ className = "size-5" }: { className?: string }) {
  return (
    <svg className={cx("animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cx("rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/80", className)}>{children}</div>
  );
}

export function EmptyState({
  icon,
  title,
  message,
  action,
  tone = "slate",
}: {
  icon: ReactNode;
  title: string;
  message?: ReactNode;
  action?: ReactNode;
  tone?: "slate" | "red" | "amber";
}) {
  const iconTone = {
    slate: "bg-slate-100 text-slate-500",
    red: "bg-rose-50 text-rose-600",
    amber: "bg-amber-50 text-amber-600",
  };
  return (
    <div className="flex animate-fade-up flex-col items-center px-6 py-12 text-center">
      <div className={cx("mb-4 grid size-12 place-items-center rounded-2xl", iconTone[tone])}>{icon}</div>
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
      {message && <div className="mt-1 max-w-md text-sm text-slate-600">{message}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ConfidenceBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-500">
        <span>{label}</span>
        <span className="font-semibold tabular-nums text-slate-900">{pct}%</span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div className={cx("h-full rounded-full transition-[width] duration-700", color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/**
 * Plate text drawn like an Indian HSRP number plate: white plate, black border,
 * blue "IND" strip. Text that isn't a valid plate is shown as typed, greyed out.
 */
export function NumberPlate({ text, size = "md", className }: { text: string; size?: "sm" | "md" | "lg"; className?: string }) {
  const valid = plateFormat(text) !== null;
  const shown = text ? (valid ? prettyPlate(text) : text.toUpperCase()) : "— — —";
  const sizes = {
    sm: { plate: "h-7 rounded-md border", strip: "w-3.5 text-[5px]", text: "px-2 text-sm" },
    md: { plate: "h-10 rounded-lg border-2", strip: "w-5 text-[7px]", text: "px-3 text-lg" },
    lg: { plate: "h-14 rounded-xl border-[3px]", strip: "w-7 text-[9px]", text: "px-4 text-2xl sm:text-[1.7rem]" },
  }[size];
  return (
    <span
      className={cx(
        "inline-flex max-w-full items-stretch overflow-hidden bg-white shadow-sm",
        sizes.plate,
        valid ? "border-slate-900" : "border-slate-300",
        className,
      )}
    >
      <span
        className={cx(
          "flex shrink-0 items-end justify-center pb-0.5 font-bold text-white",
          sizes.strip,
          valid ? "bg-blue-700" : "bg-slate-300",
        )}
        aria-hidden="true"
      >
        IND
      </span>
      <span
        className={cx(
          "flex items-center truncate whitespace-nowrap font-[family-name:var(--font-plate)] font-bold tracking-wider",
          sizes.text,
          valid ? "text-slate-900" : "text-slate-400",
        )}
      >
        {shown}
      </span>
    </span>
  );
}

export function CopyButton({ value, label = "Copy", className }: { value: string; label?: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy to the clipboard");
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      title={copied ? "Copied" : `${label} ${value}`}
      aria-label={`${label} ${value}`}
      className={cx(
        "grid size-8 shrink-0 place-items-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700",
        className,
      )}
    >
      {copied ? <CheckIcon className="size-4 text-emerald-600" /> : <CopyIcon className="size-4" />}
    </button>
  );
}

/** Small stat tile: a label, a big number and an optional hint */
export function Stat({ label, value, hint, icon }: { label: string; value: ReactNode; hint?: string; icon?: ReactNode }) {
  return (
    <Card className="flex items-start gap-3 p-4">
      {icon && <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-indigo-50 text-indigo-600">{icon}</span>}
      <div className="min-w-0">
        <p className="text-xs font-medium text-slate-500">{label}</p>
        <p className="mt-0.5 truncate text-xl font-bold tracking-tight text-slate-900 tabular-nums">{value}</p>
        {hint && <p className="truncate text-xs text-slate-500">{hint}</p>}
      </div>
    </Card>
  );
}
