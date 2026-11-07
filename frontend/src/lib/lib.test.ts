import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";
import { toCsv } from "./csv";
import { formatIst, parseIst } from "./format";
import { checkFiles } from "./limits";
import { normalizePlate, plateFormat, prettyPlate } from "./plate";

describe("plateFormat", () => {
  it.each([
    ["MH12DE1433", "standard"],
    ["DL3CAB1234", "standard"],
    ["KL07BZ4455", "standard"],
    ["mh 12 de 1433", "standard"],
    ["22BH6517A", "bh"],
  ])("%s is %s", (plate, fmt) => {
    expect(plateFormat(plate)).toBe(fmt);
  });

  it.each(["", "IND", "XX12AB1234", "MH00AB1234", "MH12AB0000", "MH12IO1234", "22BH651A", "HELLO123"])(
    "rejects %s",
    (junk) => {
      expect(plateFormat(junk)).toBeNull();
    },
  );

  it("formats plates for display", () => {
    expect(prettyPlate("MH12DE1433")).toBe("MH 12 DE 1433");
    expect(prettyPlate("DL3CAB1234")).toBe("DL 3 CAB 1234");
    expect(prettyPlate("22BH6517A")).toBe("22 BH 6517 A");
    expect(prettyPlate("junk!")).toBe("JUNK");
    expect(normalizePlate("mh-12 de.1433")).toBe("MH12DE1433");
  });
});

describe("toCsv", () => {
  it("writes a header and escapes values", () => {
    const csv = toCsv([
      { plate: "MH12DE1433", timestamp: "2026-10-31 15:05:00", source: "upload", det_conf: 0.91, ocr_conf: null, format: "standard" },
      { plate: "22BH6517A", timestamp: "2026-10-31 16:00:00", source: 'a "b", c', det_conf: null, ocr_conf: 0.5, format: "bh" },
      { plate: "X", timestamp: "", source: "=HYPERLINK(1)", det_conf: null, ocr_conf: null, format: null },
    ]);
    const lines = csv.trim().split("\r\n");
    expect(lines[0]).toBe("Plate,Timestamp (IST),Source,Detection Conf,OCR Conf,Format");
    expect(lines[1]).toBe("MH12DE1433,2026-10-31 15:05:00,upload,0.91,,standard");
    expect(lines[2]).toBe('22BH6517A,2026-10-31 16:00:00,"a ""b"", c",,0.5,bh');
    expect(lines[3]).toBe("X,,'=HYPERLINK(1),,,");
  });
});

describe("IST timestamps", () => {
  it("parses backend timestamps as IST", () => {
    expect(parseIst("2026-10-31 15:30:00")?.toISOString()).toBe("2026-10-31T10:00:00.000Z");
    expect(parseIst("not a date")).toBeNull();
    expect(formatIst("garbage")).toBe("garbage");
  });
});

describe("checkFiles", () => {
  const file = (name: string, type: string, size = 1000) => new File([new Uint8Array(size)], name, { type });

  it("accepts images and explains rejections", () => {
    const { accepted, rejected } = checkFiles([
      file("a.jpg", "image/jpeg"),
      file("b.heic", "image/heic"),
      file("c.pdf", "application/pdf"),
      file("d.png", "image/png", 11 * 1024 * 1024),
      file("e.png", "image/png", 0),
    ]);
    expect(accepted.map((f) => f.name)).toEqual(["a.jpg", "b.heic"]);
    expect(rejected.map((r) => r.reason)).toEqual([
      "not a JPEG, PNG, WebP, BMP or HEIC image",
      "larger than 10 MB",
      "file is empty",
    ]);
  });

  it("caps the number of files", () => {
    const files = Array.from({ length: 12 }, (_, i) => file(`${i}.jpg`, "image/jpeg"));
    const { accepted, rejected } = checkFiles(files);
    expect(accepted).toHaveLength(10);
    expect(rejected).toHaveLength(2);
  });
});

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("turns error JSON into ApiError with the server message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({ error: { code: "DUPLICATE_PLATE", message: "MH12DE1433 was already logged" } }, { status: 409 }),
      ),
    );
    const err = await api.saveLog({ plate: "MH12DE1433", source: "upload" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("DUPLICATE_PLATE");
    expect(err.status).toBe(409);
    expect(err.message).toBe("MH12DE1433 was already logged");
  });

  it("gives a friendly message when the server is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const err = await api.health().catch((e) => e);
    expect(err.code).toBe("NETWORK");
    expect(err.message).toMatch(/Can't reach the backend/);
  });

  it("treats an empty proxy error as the backend being down", async () => {
    // what the Vite dev proxy answers when nothing listens on port 8000
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
    const err = await api.health().catch((e) => e);
    expect(err.code).toBe("BACKEND_DOWN");
    expect(err.message).toMatch(/Can't reach the backend/);
  });

  it("notices when a web page answers instead of the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<!doctype html><html></html>", { headers: { "content-type": "text/html" } })),
    );
    const err = await api.health().catch((e) => e);
    expect(err.code).toBe("NOT_THE_API");
    expect(err.message).not.toMatch(/<html/i);
  });

  it("keeps the server's own message for real API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ error: { code: "INTERNAL_ERROR", message: "Server hiccup." } }, { status: 500 })),
    );
    const err = await api.health().catch((e) => e);
    expect(err.code).toBe("INTERNAL_ERROR");
    expect(err.message).toBe("Server hiccup.");
  });

  it("sends filters as query params", async () => {
    const fetchMock = vi.fn(async (_url: string) => Response.json({ items: [], total: 0 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.logs({ q: "MH", format: "", source: "camera", limit: 50 });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/logs?q=MH&source=camera&limit=50");
  });
});
