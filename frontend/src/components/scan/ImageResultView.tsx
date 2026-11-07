import type { ImageResult } from "../../lib/api";
import { duration } from "../../lib/format";
import { AlertIcon, ImageIcon } from "../icons";
import { Card, cx, EmptyState } from "../ui";
import { AnnotatedImage } from "./AnnotatedImage";
import { PlateCard, type SaveState } from "./PlateCard";
import { plateColor } from "./status";

interface Props {
  url: string;
  result: ImageResult;
  texts: string[];
  saveStates: SaveState[];
  onTextChange: (plateIndex: number, text: string) => void;
  onSave: (plateIndex: number) => void;
  sheetsReady: boolean;
}

const REJECTED = new Set(["bad_image", "unsupported_type", "too_large", "error"]);

export function ImageResultView({ url, result, texts, saveStates, onTextChange, onSave, sheetsReady }: Props) {
  const { plates } = result;

  if (REJECTED.has(result.status) || !result.width || !result.height) {
    return (
      <Card>
        <EmptyState
          tone="red"
          icon={<AlertIcon />}
          title={result.status === "error" ? "Couldn't process this image" : "This file can't be scanned"}
          message={result.message ?? "Try a different photo."}
        />
      </Card>
    );
  }

  const colors = plates.map((_, i) => plateColor(i));
  const warn = result.status !== "ok" && plates.length > 0;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="space-y-3">
        <AnnotatedImage
          src={url}
          width={result.width}
          height={result.height}
          plates={plates}
          labels={texts}
          colors={colors}
          alt={result.filename}
        />
        <p className="flex justify-between gap-2 text-xs text-slate-500">
          <span className="truncate">{result.filename}</span>
          <span className="shrink-0 tabular-nums">
            {result.width}×{result.height} · {duration(result.processing_ms)}
          </span>
        </p>
      </div>

      <div className="space-y-3">
        {warn && result.message && (
          <div className={cx("flex gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200")}>
            <AlertIcon className="size-5 shrink-0" />
            <p>{result.message}</p>
          </div>
        )}
        {plates.length === 0 ? (
          <Card>
            <EmptyState
              icon={<ImageIcon />}
              title="No number plate found"
              message="Get closer so the plate fills more of the photo, keep it straight on, and avoid glare."
            />
          </Card>
        ) : (
          plates.map((plate, i) => (
            <PlateCard
              key={i}
              plate={plate}
              index={i}
              text={texts[i] ?? ""}
              onTextChange={(t) => onTextChange(i, t)}
              saveState={saveStates[i] ?? "idle"}
              onSave={() => onSave(i)}
              sheetsReady={sheetsReady}
              color={colors[i]!}
            />
          ))
        )}
      </div>
    </div>
  );
}
