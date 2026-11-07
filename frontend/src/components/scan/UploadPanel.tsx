import { useEffect, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import toast from "react-hot-toast";
import type { Source } from "../../lib/api";
import { MAX_FILE_MB, MAX_FILES } from "../../lib/limits";
import { CameraIcon, SparkIcon, UploadIcon } from "../icons";
import { btn, Card, cx, Spinner } from "../ui";

interface Props {
  onFiles: (files: File[], source: Source) => void;
  disabled?: boolean;
  compact?: boolean;
}

export function UploadPanel({ onFiles, disabled, compact }: Props) {
  const cameraRef = useRef<HTMLInputElement>(null);
  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    // Type and size checks happen in checkFiles so the user gets a reason
    onDrop: (accepted, rejected) => onFiles([...accepted, ...rejected.map((r) => r.file)], "upload"),
    multiple: true,
    disabled,
    noClick: true,
    noKeyboard: true,
  });

  return (
    <Card className={cx("p-2 transition", isDragActive && "ring-2 ring-indigo-400")}>
      <div
        {...getRootProps()}
        className={cx(
          "relative flex flex-col items-center overflow-hidden rounded-xl border-2 border-dashed text-center transition",
          compact ? "px-4 py-6" : "px-5 py-8 sm:px-6 sm:py-16",
          isDragActive ? "border-indigo-400 bg-indigo-50/70" : "border-slate-200 bg-gradient-to-b from-slate-50/80 to-white",
        )}
      >
        <input {...getInputProps({ accept: "image/*" })} />
        {!compact && (
          <div
            className={cx(
              "mb-5 grid size-16 place-items-center rounded-2xl bg-gradient-to-br from-indigo-500 to-sky-500 text-white shadow-lg shadow-indigo-500/30 transition",
              isDragActive && "scale-110",
            )}
          >
            <UploadIcon className="size-7" />
          </div>
        )}
        <p className={cx("font-semibold text-slate-900", compact ? "text-sm" : "text-lg")}>
          {isDragActive ? "Drop to scan" : compact ? "Scan more images" : "Drop photos of vehicles here"}
        </p>
        {!compact && (
          <p className="mt-1.5 max-w-md text-sm text-slate-500">
            Or take a photo with your phone. Up to {MAX_FILES} images at once — JPEG, PNG, WebP or iPhone HEIC, up to{" "}
            {MAX_FILE_MB} MB each.
          </p>
        )}

        <div className={cx("flex w-full flex-col gap-2 sm:w-auto sm:flex-row", compact ? "mt-4" : "mt-6")}>
          <button
            type="button"
            className={cx(btn.base, btn.primary, "py-3 sm:py-2.5")}
            onClick={open}
            disabled={disabled}
          >
            <UploadIcon className="size-4" /> Choose images
          </button>
          <button
            type="button"
            className={cx(btn.base, btn.secondary, "py-3 sm:py-2.5")}
            onClick={() => cameraRef.current?.click()}
            disabled={disabled}
          >
            <CameraIcon className="size-4" /> Take photo
          </button>
        </div>

        {/* Opens the rear camera on phones, a file picker on desktop */}
        <input
          ref={cameraRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (files.length) onFiles(files, "camera");
          }}
        />
      </div>
    </Card>
  );
}

const SAMPLES = [
  { src: "/samples/sample-1.png", name: "BH series", file: "sample-bh.png" },
  { src: "/samples/sample-2.png", name: "Rajasthan", file: "sample-rj.png" },
  { src: "/samples/sample-3.png", name: "Maharashtra", file: "sample-mh.png" },
];

/** One-click demo images, so the app can be tried without a photo at hand */
export function SamplePicker({ onFiles, disabled }: { onFiles: Props["onFiles"]; disabled?: boolean }) {
  const [loading, setLoading] = useState<string | null>(null);

  async function pick(sample: (typeof SAMPLES)[number] | "all") {
    const chosen = sample === "all" ? SAMPLES : [sample];
    setLoading(sample === "all" ? "all" : sample.src);
    try {
      const files = await Promise.all(
        chosen.map(async (s) => {
          const res = await fetch(s.src);
          if (!res.ok) throw new Error(s.src);
          return new File([await res.blob()], s.file, { type: "image/png" });
        }),
      );
      onFiles(files, "upload");
    } catch {
      toast.error("Couldn't load the sample image.");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="animate-fade-up">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <SparkIcon className="size-4 text-indigo-500" /> No photo handy? Try a sample
        </p>
        <button
          type="button"
          onClick={() => pick("all")}
          disabled={disabled || !!loading}
          className="text-sm font-semibold text-indigo-600 hover:text-indigo-500 disabled:opacity-50"
        >
          {loading === "all" ? "Loading…" : "Scan all three →"}
        </button>
      </div>
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        {SAMPLES.map((s) => (
          <button
            key={s.src}
            type="button"
            onClick={() => pick(s)}
            disabled={disabled || !!loading}
            className="group relative overflow-hidden rounded-xl bg-slate-900 text-left shadow-sm ring-1 ring-slate-200 transition hover:-translate-y-0.5 hover:shadow-md hover:ring-indigo-300 disabled:opacity-60 disabled:hover:translate-y-0"
          >
            <img
              src={s.src}
              alt={`Sample photo: ${s.name} plate`}
              className="aspect-[4/3] w-full object-cover opacity-90 transition group-hover:scale-105 group-hover:opacity-100 sm:aspect-[5/2]"
            />
            <span className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-slate-950/85 to-transparent px-2 pb-1.5 pt-5 text-[11px] font-semibold text-white sm:px-2.5 sm:text-xs">
              {s.name}
              {loading === s.src ? <Spinner className="size-3.5" /> : <span className="opacity-0 transition group-hover:opacity-100">Scan →</span>}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function ScanningCard({ urls, onCancel }: { urls: string[]; onCancel: () => void }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const [first, ...rest] = urls;
  const count = urls.length;

  return (
    <Card className="animate-fade-up overflow-hidden">
      <div className="grid gap-6 p-5 sm:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] sm:items-center sm:p-6">
        <div className="relative overflow-hidden rounded-xl bg-slate-900">
          {first && <img src={first} alt="" className="block max-h-80 w-full object-contain opacity-80" />}
          {/* sweeping beam, purely decorative */}
          <div className="pointer-events-none absolute inset-x-0 h-16 -translate-y-1/2 animate-scan-beam bg-gradient-to-b from-transparent via-indigo-400/35 to-transparent">
            <div className="absolute inset-x-0 top-1/2 h-0.5 bg-indigo-300 shadow-[0_0_12px_2px_rgb(129_140_248)]" />
          </div>
          <div className="pointer-events-none absolute inset-3 rounded-lg border border-white/20" />
        </div>

        <div className="text-center sm:text-left">
          <p className="flex items-center justify-center gap-2 text-lg font-semibold text-slate-900 sm:justify-start" role="status">
            <Spinner className="size-5 text-indigo-600" />
            Scanning {count === 1 ? "image" : `${count} images`}…
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Finding plates with YOLOv8 and reading them with PaddleOCR. Usually a few seconds per image on a CPU.
          </p>
          <p className="mt-4 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
            {seconds}
            <span className="ml-1 text-base font-medium text-slate-400">s</span>
          </p>
          {rest.length > 0 && (
            <div className="mt-4 flex justify-center gap-2 sm:justify-start">
              {rest.slice(0, 5).map((u) => (
                <img key={u} src={u} alt="" className="h-10 w-16 rounded-md object-cover opacity-70 ring-1 ring-slate-200" />
              ))}
              {rest.length > 5 && (
                <span className="grid h-10 w-16 place-items-center rounded-md bg-slate-100 text-xs font-semibold text-slate-500">
                  +{rest.length - 5}
                </span>
              )}
            </div>
          )}
          <button type="button" className={cx(btn.base, btn.ghost, "mt-5")} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </Card>
  );
}
