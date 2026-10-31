import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { AlertIcon, CameraIcon, UploadIcon } from "../components/icons";
import { ImageResultView } from "../components/scan/ImageResultView";
import type { SaveState } from "../components/scan/PlateCard";
import { ResultsTable } from "../components/scan/ResultsTable";
import { ScanningCard, UploadPanel } from "../components/scan/UploadPanel";
import { btn, Card, cx, EmptyState } from "../components/ui";
import { useHealth } from "../health";
import { api, ApiError, isAbort, type ImageResult, type Source } from "../lib/api";
import { duration } from "../lib/format";
import { checkFiles } from "../lib/limits";
import { normalizePlate, prettyPlate } from "../lib/plate";

interface ScanItem {
  id: string;
  file: File;
  url: string;
  result?: ImageResult;
  texts: string[];
  saves: SaveState[];
}

type Phase = "idle" | "scanning" | "done" | "failed";

let nextId = 0;

const TIPS = [
  { icon: <CameraIcon />, title: "Get close", text: "The plate should fill a good part of the photo." },
  { icon: <UploadIcon />, title: "Keep it sharp", text: "Hold still and avoid glare on shiny plates." },
  { icon: <AlertIcon />, title: "Check before saving", text: "Edit the text if anything looks off." },
];

export function ScanPage() {
  const { health, error: healthError } = useHealth();
  const [items, setItems] = useState<ScanItem[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [failure, setFailure] = useState("");
  const [source, setSource] = useState<Source>("upload");
  const [selected, setSelected] = useState<string | null>(null);
  const [totalMs, setTotalMs] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const urlsRef = useRef<string[]>([]);

  // Free the image previews when leaving the page
  useEffect(
    () => () => {
      abortRef.current?.abort();
      urlsRef.current.forEach(URL.revokeObjectURL);
    },
    [],
  );

  const sheetsReady = health?.sheets.ok ?? false;
  const modelDown = health && !health.model.ok;

  async function scan(files: File[], src: Source) {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    urlsRef.current.forEach(URL.revokeObjectURL);
    const fresh = files.map((file) => ({
      id: String(nextId++),
      file,
      url: URL.createObjectURL(file),
      texts: [],
      saves: [],
    }));
    urlsRef.current = fresh.map((i) => i.url);

    setItems(fresh);
    setSource(src);
    setPhase("scanning");

    try {
      const res = await api.detect(files, ctrl.signal);
      setItems(
        fresh.map((item, i) => {
          const result = res.results[i];
          const plates = result?.plates ?? [];
          return { ...item, result, texts: plates.map((p) => p.text), saves: plates.map(() => "idle" as const) };
        }),
      );
      setSelected(fresh[0]?.id ?? null);
      setTotalMs(res.total_ms);
      setPhase("done");

      const found = res.results.reduce((n, r) => n + r.plates.filter((p) => p.text).length, 0);
      if (found) toast.success(`Found ${found} plate${found === 1 ? "" : "s"}`);
    } catch (e) {
      if (isAbort(e)) {
        if (abortRef.current === ctrl) {
          setPhase("idle");
          toast("Scan cancelled");
        }
        return;
      }
      const message = e instanceof ApiError ? e.message : "Something went wrong. Please try again.";
      setFailure(message);
      setPhase("failed");
      toast.error(message);
    }
  }

  function handleFiles(files: File[], src: Source) {
    const { accepted, rejected } = checkFiles(files);
    if (rejected.length === 1) {
      toast.error(`${rejected[0]!.name}: ${rejected[0]!.reason}`);
    } else if (rejected.length > 1) {
      toast.error(`${rejected.length} files skipped (${rejected[0]!.reason}, …)`);
    }
    if (accepted.length) scan(accepted, src);
  }

  function updateItem(id: string, update: (item: ScanItem) => ScanItem) {
    setItems((prev) => prev.map((it) => (it.id === id ? update(it) : it)));
  }

  function setSave(id: string, index: number, state: SaveState) {
    updateItem(id, (it) => ({ ...it, saves: it.saves.map((s, i) => (i === index ? state : s)) }));
  }

  async function save(item: ScanItem, index: number) {
    const plate = item.result?.plates[index];
    if (!plate) return;
    const text = normalizePlate(item.texts[index] ?? "");

    setSave(item.id, index, "saving");
    try {
      await api.saveLog({ plate: text, source, det_conf: plate.det_conf, ocr_conf: plate.ocr_conf });
      setSave(item.id, index, "saved");
      toast.success(`${prettyPlate(text)} saved to log`);
    } catch (e) {
      if (e instanceof ApiError && e.code === "DUPLICATE_PLATE") {
        setSave(item.id, index, "duplicate");
        toast(e.message, { icon: <AlertIcon className="size-5 text-amber-500" /> });
      } else {
        setSave(item.id, index, "idle");
        toast.error(e instanceof ApiError ? e.message : "Couldn't save. Please try again.");
      }
    }
  }

  const current = items.find((i) => i.id === selected) ?? items[0];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">Scan plates</h1>
        <p className="mt-1 text-sm text-slate-600">Detect number plates in photos and log them to Google Sheets.</p>
      </div>

      {(modelDown || healthError) && (
        <div className="flex gap-3 rounded-xl bg-rose-50 p-4 text-sm text-rose-900 ring-1 ring-rose-200" role="alert">
          <AlertIcon className="size-5 shrink-0 text-rose-600" />
          <div>
            <p className="font-medium">Scanning is unavailable right now</p>
            <p className="mt-0.5">{modelDown ? health?.model.error : healthError}</p>
          </div>
        </div>
      )}

      {phase === "idle" && (
        <>
          <UploadPanel onFiles={handleFiles} disabled={!!modelDown} />
          <ul className="grid gap-3 sm:grid-cols-3">
            {TIPS.map((tip) => (
              <li key={tip.title} className="flex gap-3 rounded-xl bg-white p-4 ring-1 ring-slate-200">
                <span className="text-slate-400">{tip.icon}</span>
                <div>
                  <p className="text-sm font-medium text-slate-900">{tip.title}</p>
                  <p className="text-sm text-slate-500">{tip.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {phase === "scanning" && <ScanningCard count={items.length} onCancel={() => abortRef.current?.abort()} />}

      {phase === "failed" && (
        <Card>
          <EmptyState
            tone="red"
            icon={<AlertIcon />}
            title="Scan failed"
            message={failure}
            action={
              <div className="flex flex-col gap-2 sm:flex-row">
                <button
                  type="button"
                  className={cx(btn.base, btn.primary)}
                  onClick={() => scan(items.map((i) => i.file), source)}
                >
                  Try again
                </button>
                <button type="button" className={cx(btn.base, btn.secondary)} onClick={() => setPhase("idle")}>
                  Choose other images
                </button>
              </div>
            }
          />
        </Card>
      )}

      {phase === "done" && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-slate-600">
              {items.length} image{items.length === 1 ? "" : "s"} scanned in {duration(totalMs)}
            </p>
            <button type="button" className={cx(btn.base, btn.secondary)} onClick={() => setPhase("idle")}>
              New scan
            </button>
          </div>

          {items.length > 1 && (
            <ResultsTable
              rows={items.filter((i) => i.result).map((i) => ({ id: i.id, url: i.url, result: i.result!, texts: i.texts }))}
              selected={current?.id ?? null}
              onSelect={setSelected}
            />
          )}

          {current?.result && (
            <ImageResultView
              key={current.id}
              url={current.url}
              result={current.result}
              texts={current.texts}
              saveStates={current.saves}
              sheetsReady={sheetsReady}
              onTextChange={(i, text) =>
                updateItem(current.id, (it) => ({
                  ...it,
                  texts: it.texts.map((t, j) => (j === i ? text : t)),
                  // an edited plate can be saved again
                  saves: it.saves.map((s, j) => (j === i && s === "duplicate" ? "idle" : s)),
                }))
              }
              onSave={(i) => save(current, i)}
            />
          )}

          <UploadPanel onFiles={handleFiles} compact />
        </>
      )}
    </div>
  );
}
