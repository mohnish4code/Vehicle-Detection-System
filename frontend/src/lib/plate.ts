// Same rules as src/plates.py on the backend, used to give instant
// feedback while the user edits a plate. The backend still checks on save.

import type { PlateFormat } from "./api";

const STATES =
  "AN AP AR AS BR CG CH DD DL DN GA GJ HP HR JH JK KA KL LA LD MH ML MN MP MZ NL OD OR PB PY RJ SK TG TN TR TS UK UA UP WB".split(
    " ",
  );
const SERIES = "[A-HJ-NP-Z]";

const STANDARD = new RegExp(`^(${STATES.join("|")})(\\d{1,2})(${SERIES}{0,3})(\\d{1,4})$`);
const BH = new RegExp(`^\\d{2}BH(\\d{4})${SERIES}{1,2}$`);

export function normalizePlate(text: string): string {
  return text.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export function plateFormat(text: string): PlateFormat | null {
  const plate = normalizePlate(text);

  const std = STANDARD.exec(plate);
  if (std && Number(std[2]) > 0 && Number(std[4]) > 0) return "standard";

  const bh = BH.exec(plate);
  if (bh && Number(bh[1]) > 0) return "bh";

  return null;
}

/** "MH12DE1433" -> "MH 12 DE 1433", "22BH6517A" -> "22 BH 6517 A" */
export function prettyPlate(text: string): string {
  const plate = normalizePlate(text);
  if (plateFormat(plate) === "bh") return plate.replace(/^(\d{2})(BH)(\d{4})(\w+)$/, "$1 $2 $3 $4");
  const m = STANDARD.exec(plate);
  return m ? [m[1], m[2], m[3], m[4]].filter(Boolean).join(" ") : plate;
}
