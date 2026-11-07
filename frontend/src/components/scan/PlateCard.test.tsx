import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Plate } from "../../lib/api";
import { PlateCard, type SaveState } from "./PlateCard";

const plate = (overrides: Partial<Plate> = {}): Plate => ({
  box: { x1: 0, y1: 0, x2: 10, y2: 10 },
  text: "RJ1GCV0002",
  raw_text: "RJIGCV0002",
  det_conf: 0.87,
  ocr_conf: 0.33,
  valid: true,
  needs_review: true,
  format: "standard",
  crop: "",
  ...overrides,
});

function Harness({ p, sheetsReady = true, saveState = "idle", onSave = () => {} }: {
  p: Plate;
  sheetsReady?: boolean;
  saveState?: SaveState;
  onSave?: () => void;
}) {
  const [text, setText] = useState(p.text);
  return (
    <PlateCard
      plate={p}
      index={0}
      text={text}
      onTextChange={setText}
      saveState={saveState}
      onSave={onSave}
      sheetsReady={sheetsReady}
      color="#4ade80"
    />
  );
}

describe("PlateCard", () => {
  it("flags a low-confidence read for review", () => {
    render(<Harness p={plate()} />);
    expect(screen.getByText("Needs review")).toBeInTheDocument();
    expect(screen.getByText(/auto-corrected/)).toBeInTheDocument();
    expect(screen.getByText("87%")).toBeInTheDocument();
    expect(screen.getByText("33%")).toBeInTheDocument();
  });

  it("lets the user fix the text before saving", async () => {
    const onSave = vi.fn();
    render(<Harness p={plate()} onSave={onSave} />);
    const input = screen.getByLabelText("Plate number");

    await userEvent.clear(input);
    await userEvent.type(input, "rj14xx");
    expect(screen.getByText("Invalid format")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save to log" })).toBeDisabled();

    await userEvent.clear(input);
    await userEvent.type(input, "rj14cv0002");
    expect(input).toHaveValue("RJ14CV0002");
    expect(screen.getByText("Valid · edited")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Save to log" }));
    expect(onSave).toHaveBeenCalledOnce();
  });

  it("can't save when Google Sheets is down", () => {
    render(<Harness p={plate({ needs_review: false, text: "MH12DE1433" })} sheetsReady={false} />);
    expect(screen.getByText("Valid")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save to log" })).toBeDisabled();
    expect(screen.getByText(/Google Sheets isn't connected/)).toBeInTheDocument();
  });

  it("locks the plate once saved", () => {
    render(<Harness p={plate({ needs_review: false, text: "MH12DE1433" })} saveState="saved" />);
    expect(screen.getByRole("button", { name: /Saved to log/ })).toBeDisabled();
    expect(screen.getByLabelText("Plate number")).toBeDisabled();
  });
});
