import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { AlertIcon, CameraIcon, CheckIcon, PlusIcon, SparkIcon } from "../components/icons";
import { ImageResultView } from "../components/scan/ImageResultView";
import type { SaveState } from "../components/scan/PlateCard";
import { ResultsTable } from "../components/scan/ResultsTable";
import { SamplePicker, ScanningCard, UploadPanel } from "../components/scan/UploadPanel";
import { btn, Card, cx, EmptyState } from "../components/ui";
import { useHealth } from "../health";
import { api, ApiError, isAbort, OFFLINE_CODES, type ImageResult, type Source } from "../lib/api";
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
  { icon: <CameraIcon className="size-5" />, title: "Get close", text: "The plate should fill a good part of the photo." },
  { icon: <SparkIcon className="size-5" />, title: "Keep it sharp", text: "Hold still and avoid glare on shiny plates." },
  { icon: <CheckIcon className="size-5" />, title: "Check before saving", text: "Unclear reads are flagged so you can fix them." },
];

// From backend/benchmark/reports (heldout_e2e.json, benchmark.json)
const FACTS = ["85% of unseen test plates read exactly", "~1.8 s per photo on a laptop CPU", "Standard & BH series plates"];

function Summary({ items }: { items: ScanItem[] }) {
  const plates = items.flatMap((i) => i.result?.plates ?? []);
  const review = plates.filter((p) => p.needs_review || !p.valid).length;
  const saved = items.reduce((n, i) => n + i.saves.filter((s) => s === "saved").length, 0);
  const chips = [
    { label: `${items.length} image${items.length === 1 ? "" : "s"}`, tone: "bg-slate-100 text-slate-700" },
    { label: `${plates.length} plate${plates.length === 1 ? "" : "s"} found`, tone: "bg-indigo-50 text-indigo-700" },
    review > 0 && { label: `${review} to check`, tone: "bg-amber-50 text-amber-800" },
    saved > 0 && { label: `${saved} saved`, tone: "bg-emerald-50 text-emerald-700" },
  ].filter(Boolean) as { label: string; tone: string }[];
  return (
    <div className="flex flex-wrap gap-1.5">
      {chips.map((c) => (
        <span key={c.label} className={cx("rounded-full px-2.5 py-1 text-xs font-semibold", c.tone)}>
          {c.label}
        </span>
      ))}
    </div>
  );
}

export function ScanPage() {
  const { health, error: healthError, offline, refresh: refreshHealth } = useHealth();
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
      if (e instanceof ApiError && OFFLINE_CODES.has(e.code)) refreshHealth();
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
    <div className="space-y-6">
      {phase === "idle" ? (
        <div className="animate-fade-up">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs font-semibold text-indigo-700 shadow-sm ring-1 ring-indigo-100">
            <SparkIcon className="size-3.5" /> YOLOv8 + PaddleOCR
          </span>
          <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
            Read Indian number plates{" "}
            <span className="bg-gradient-to-r from-indigo-600 to-sky-500 bg-clip-text text-transparent">in seconds</span>
          </h1>
          <p className="mt-2 max-w-2xl text-base text-slate-600">
            Upload or snap a photo of a vehicle. The plate is found, read, checked against Indian plate formats, and
            logged to Google Sheets once you confirm it.
          </p>
          <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 text-sm text-slate-600">
            {FACTS.map((f) => (
              <li key={f} className="flex items-center gap-1.5">
                <CheckIcon className="size-4 text-emerald-600" /> {f}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              {phase === "scanning" ? "Scanning" : phase === "failed" ? "Scan failed" : "Results"}
            </h1>
            {phase === "done" && (
              <p className="mt-1 text-sm text-slate-500">
                Scanned in {duration(totalMs)}. Check each plate, edit if needed, then save it to the log.
              </p>
            )}
          </div>
          {phase === "done" && (
            <button type="button" className={cx(btn.base, btn.dark)} onClick={() => setPhase("idle")}>
              <PlusIcon className="size-4" /> New scan
            </button>
          )}
        </div>
      )}

      {(modelDown || (healthError && !offline)) && (
        <div className="flex gap-3 rounded-2xl bg-rose-50 p-4 text-sm text-rose-900 ring-1 ring-rose-200" role="alert">
          <AlertIcon className="size-5 shrink-0 text-rose-600" />
          <div>
            <p className="font-semibold">Scanning is unavailable right now</p>
            <p className="mt-0.5">{modelDown ? health?.model.error : healthError}</p>
          </div>
        </div>
      )}

      {phase === "idle" && (
        <>
          <UploadPanel onFiles={handleFiles} disabled={!!modelDown || offline} />
          <SamplePicker onFiles={handleFiles} disabled={!!modelDown || offline} />
          <ul className="grid gap-3 sm:grid-cols-3">
            {TIPS.map((tip) => (
              <li key={tip.title} className="flex gap-3 rounded-2xl bg-white/70 p-4 ring-1 ring-slate-200/80">
                <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600">{tip.icon}</span>
                <div>
                  <p className="text-sm font-semibold text-slate-900">{tip.title}</p>
                  <p className="text-sm text-slate-500">{tip.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {phase === "scanning" && <ScanningCard urls={items.map((i) => i.url)} onCancel={() => abortRef.current?.abort()} />}

      {phase === "failed" && (
        <Card>
          <EmptyState
            tone="red"
            icon={<AlertIcon />}
            title="Couldn't scan the images"
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
          <Summary items={items} />

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
