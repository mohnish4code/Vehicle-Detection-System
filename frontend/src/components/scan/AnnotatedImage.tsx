import type { Plate } from "../../lib/api";

interface Props {
  src: string;
  width: number;
  height: number;
  plates: Plate[];
  labels: string[];
  colors: string[];
  alt: string;
  /** Plate being hovered in the list; the others are dimmed */
  active?: number | null;
  onHover?: (index: number | null) => void;
}

/**
 * The uploaded image with plate boxes drawn on top. The SVG uses the image's
 * pixel size as its viewBox, so the boxes from the API line up at any screen size.
 */
export function AnnotatedImage({ src, width, height, plates, labels, colors, alt, active = null, onHover }: Props) {
  const stroke = Math.max(2, width / 250);
  const font = Math.max(14, width / 32);
  const pad = font * 0.35;

  return (
    <div className="relative overflow-hidden rounded-2xl bg-slate-900 shadow-sm ring-1 ring-slate-200">
      <img src={src} alt={alt} className="block h-auto w-full" />
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
        aria-hidden="true"
      >
        {plates.map((p, i) => {
          const { x1, y1, x2, y2 } = p.box;
          const label = labels[i] || "?";
          const labelW = label.length * font * 0.62 + pad * 2;
          const labelH = font + pad * 1.4;
          // Label above the box, or inside it if the box touches the top edge
          const labelY = y1 - labelH >= 0 ? y1 - labelH : y1;
          const color = colors[i] ?? "#22c55e";
          const dimmed = active !== null && active !== i;
          return (
            <g
              key={i}
              opacity={dimmed ? 0.35 : 1}
              style={{ transition: "opacity 150ms", cursor: onHover ? "pointer" : undefined }}
              onMouseEnter={() => onHover?.(i)}
              onMouseLeave={() => onHover?.(null)}
            >
              {/* soft fill so the hovered plate stands out */}
              <rect
                x={x1}
                y={y1}
                width={x2 - x1}
                height={y2 - y1}
                fill={color}
                fillOpacity={active === i ? 0.18 : 0.04}
                stroke={color}
                strokeWidth={active === i ? stroke * 1.8 : stroke}
                rx={stroke}
              />
              <rect x={x1} y={labelY} width={labelW} height={labelH} fill={color} rx={stroke} />
              <text
                x={x1 + pad}
                y={labelY + labelH / 2}
                dominantBaseline="central"
                fontSize={font}
                fontFamily="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace"
                fontWeight={700}
                fill="#0f172a"
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
