import { useEffect, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import type { Source } from "../../lib/api";
import { MAX_FILE_MB, MAX_FILES } from "../../lib/limits";
import { CameraIcon, UploadIcon } from "../icons";
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
    <Card className="p-2">
      <div
        {...getRootProps()}
        className={cx(
          "flex flex-col items-center rounded-xl border-2 border-dashed text-center transition",
          compact ? "px-4 py-5" : "px-6 py-10 sm:py-14",
          isDragActive ? "border-sky-400 bg-sky-50" : "border-slate-200",
        )}
      >
        <input {...getInputProps({ accept: "image/*" })} />
        {!compact && (
          <div className="mb-4 grid size-12 place-items-center rounded-full bg-slate-100 text-slate-600">
            <UploadIcon className="size-6" />
          </div>
        )}
        <p className="text-sm font-medium text-slate-900">
          {isDragActive ? "Drop images to scan" : compact ? "Scan more images" : "Scan a number plate"}
        </p>
        {!compact && (
          <p className="mt-1 text-sm text-slate-500">
            Take a photo or upload up to {MAX_FILES} images (JPEG, PNG, WebP or iPhone HEIC, max {MAX_FILE_MB} MB each).
          </p>
        )}

        <div className="mt-5 flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
          <button
            type="button"
            className={cx(btn.base, btn.primary, "py-3 sm:py-2.5")}
            onClick={() => cameraRef.current?.click()}
            disabled={disabled}
          >
            <CameraIcon /> Take photo
          </button>
          <button type="button" className={cx(btn.base, btn.secondary, "py-3 sm:py-2.5")} onClick={open} disabled={disabled}>
            <UploadIcon /> Upload images
          </button>
        </div>
        <p className="mt-3 hidden text-xs text-slate-400 sm:block">or drag and drop images here</p>

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

export function ScanningCard({ count, onCancel }: { count: number; onCancel: () => void }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <Card className="flex flex-col items-center px-6 py-12 text-center" >
      <Spinner className="size-8 text-slate-700" />
      <p className="mt-4 font-medium text-slate-900" role="status">
        Scanning {count === 1 ? "image" : `${count} images`}… <span className="tabular-nums text-slate-500">{seconds}s</span>
      </p>
      <p className="mt-1 max-w-sm text-sm text-slate-500">
        Finding plates and reading the text. On a CPU this can take up to a minute per image.
      </p>
      <button type="button" className={cx(btn.base, btn.ghost, "mt-5")} onClick={onCancel}>
        Cancel
      </button>
    </Card>
  );
}
