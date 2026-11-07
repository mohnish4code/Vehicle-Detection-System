import type { Plate } from "../../lib/api";
import { normalizePlate, plateFormat } from "../../lib/plate";
import { AlertIcon, CheckIcon } from "../icons";
import { Badge, btn, ConfidenceBar, CopyButton, cx, NumberPlate, Spinner } from "../ui";

export type SaveState = "idle" | "saving" | "saved" | "duplicate";

interface Props {
  plate: Plate;
  index: number;
  text: string;
  onTextChange: (text: string) => void;
  saveState: SaveState;
  onSave: () => void;
  sheetsReady: boolean;
  color: string;
  highlighted?: boolean;
}

export function plateStatus(plate: Plate, text: string) {
  const fmt = plateFormat(text);
  const edited = normalizePlate(text) !== plate.text;
  if (!fmt) return { fmt, tone: "red" as const, label: text ? "Invalid format" : "No text" };
  if (plate.needs_review && !edited) return { fmt, tone: "amber" as const, label: "Needs review" };
  return { fmt, tone: "green" as const, label: edited ? "Valid · edited" : "Valid" };
}

export function PlateCard({ plate, index, text, onTextChange, saveState, onSave, sheetsReady, color, highlighted }: Props) {
  const status = plateStatus(plate, text);
  const locked = saveState === "saving" || saveState === "saved";
  const inputId = `plate-${index}`;

  let hint: string | null = null;
  if (!status.fmt) hint = "Doesn't match an Indian plate (e.g. MH12DE1433 or 22BH6517A). Fix it to save.";
  else if (status.tone === "amber") hint = "The text wasn't read clearly. Check it against the photo before saving.";

  return (
    <div
      className={cx(
        "rounded-2xl bg-white p-4 shadow-sm ring-1 transition sm:p-5",
        highlighted ? "ring-2 ring-indigo-300 shadow-md" : "ring-slate-200/80",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <span className="size-3 rounded-sm" style={{ background: color }} />
          Plate {index + 1}
          {status.fmt && (
            <span className="font-normal text-slate-400">· {status.fmt === "bh" ? "BH series" : "Standard"}</span>
          )}
        </div>
        <Badge tone={status.tone}>
          {status.tone === "green" ? <CheckIcon className="size-3.5" /> : <AlertIcon className="size-3.5" />}
          {status.label}
        </Badge>
      </div>

      {/* what will be saved, drawn as a plate; follows the text box live */}
      <div className="mt-4 flex items-center gap-2">
        <NumberPlate text={normalizePlate(text)} size="lg" className="min-w-0" />
        {status.fmt && <CopyButton value={normalizePlate(text)} label="Copy plate" />}
      </div>

      {plate.crop && (
        <div className="mt-3 rounded-xl bg-slate-50 p-2 ring-1 ring-slate-100">
          <p className="mb-1 px-1 text-[11px] font-medium uppercase tracking-wide text-slate-400">From the photo</p>
          <img src={plate.crop} alt={`Cropped plate ${index + 1}`} className="h-16 w-full rounded-lg object-contain" />
        </div>
      )}

      <label htmlFor={inputId} className="mt-4 block text-xs font-semibold text-slate-600">
        Plate number
      </label>
      <input
        id={inputId}
        value={text}
        onChange={(e) => onTextChange(e.target.value.toUpperCase())}
        disabled={locked}
        autoComplete="off"
        autoCapitalize="characters"
        spellCheck={false}
        maxLength={16}
        className={cx(
          "mt-1 w-full rounded-xl border bg-white px-3 py-2.5 font-[family-name:var(--font-plate)] text-lg font-bold tracking-widest text-slate-900 outline-none transition focus:ring-4 disabled:bg-slate-50 disabled:text-slate-500",
          status.fmt ? "border-slate-300 focus:border-indigo-400 focus:ring-indigo-100" : "border-rose-300 focus:ring-rose-100",
        )}
        placeholder="MH12DE1433"
      />
      {plate.raw_text && plate.raw_text !== plate.text && (
        <p className="mt-1.5 text-xs text-slate-500">
          OCR read <span className="font-[family-name:var(--font-plate)] font-semibold">{plate.raw_text}</span>, auto-corrected.
        </p>
      )}
      {hint && <p className={cx("mt-1.5 text-xs", status.fmt ? "text-amber-700" : "text-rose-600")}>{hint}</p>}

      <div className="mt-4 grid grid-cols-2 gap-4">
        <ConfidenceBar label="Detection" value={plate.det_conf} />
        <ConfidenceBar label="OCR" value={plate.ocr_conf} />
      </div>

      <button
        type="button"
        onClick={onSave}
        disabled={!status.fmt || locked || !sheetsReady}
        className={cx(
          btn.base,
          saveState === "saved" ? "bg-emerald-600 text-white disabled:opacity-100" : btn.primary,
          "mt-5 w-full py-3 sm:py-2.5",
        )}
      >
        {saveState === "saving" && <Spinner className="size-4" />}
        {saveState === "saved" && <CheckIcon className="size-4" />}
        {saveState === "saving" ? "Saving…" : saveState === "saved" ? "Saved to log" : "Save to log"}
      </button>
      {saveState === "duplicate" && (
        <p className="mt-2 text-center text-xs text-amber-700">Already logged recently. Not saved again.</p>
      )}
      {!sheetsReady && saveState !== "saved" && (
        <p className="mt-2 text-center text-xs text-slate-500">Saving is off because Google Sheets isn't connected.</p>
      )}
    </div>
  );
}
