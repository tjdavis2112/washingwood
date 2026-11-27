// Draft colors. Position tints are muted, non-metallic tokens in global.css; the Value over slot scale
// diverges from a bust red (a different hue from the brand red) through neutral to a steal green.
// The position and the signed value are always written out too, so color is never the only signal.
import type { DraftPlayer } from "./site-data";

export const POSITION_TINTS: Record<string, string> = {
  QB: "var(--color-pos-qb)",
  RB: "var(--color-pos-rb)",
  WR: "var(--color-pos-wr)",
  TE: "var(--color-pos-te)",
  K: "var(--color-pos-k)",
  "D/ST": "var(--color-pos-dst)",
};

const tintOf = (player: DraftPlayer) => POSITION_TINTS[player.position] ?? "var(--color-pos-other)";

/** Inline style for a Pick tinted by its Player's position; empty for a Pick with no Player recorded. */
export const pickStyle = (player: DraftPlayer | null) => {
  if (!player) return "";
  const tint = tintOf(player);
  return `border-color:${tint};background:color-mix(in srgb, ${tint} 35%, transparent)`;
};

/**
 * The value scale's clamp for one Season: the 90th percentile (nearest rank) of |Value over slot| over
 * its recorded Picks, so one extreme late-round steal doesn't wash out every other color. At least 1.
 */
export function valueClamp(values: (number | null)[]): number {
  const abs = values.filter((v): v is number => v !== null).map(Math.abs).sort((a, b) => a - b);
  if (!abs.length) return 1;
  return Math.max(1, abs[Math.ceil(0.9 * abs.length) - 1]);
}

/**
 * CSS custom properties for a board Pick that can be colored by position or by value (global.css
 * `.draft-pick` reads them, and the board's "Color by" toggle picks which pair applies).
 */
export function pickColorVars(player: DraftPlayer | null, valueOverSlot: number | null, clamp: number): string {
  if (!player) return "";
  const pos = tintOf(player);
  const vars = [`--pick-pos-edge:${pos}`, `--pick-pos-bg:color-mix(in srgb, ${pos} 35%, transparent)`];
  if (valueOverSlot !== null) {
    const t = Math.min(1, Math.abs(valueOverSlot) / clamp);
    const end = valueOverSlot > 0 ? "var(--color-value-steal)" : "var(--color-value-bust)";
    const bg = valueOverSlot === 0 ? "var(--color-panel)" : `color-mix(in srgb, ${end} ${Math.round(12 + t * 53)}%, var(--color-panel))`;
    const edge = valueOverSlot === 0 ? "var(--color-line)" : `color-mix(in srgb, ${end} ${Math.round(40 + t * 60)}%, var(--color-panel))`;
    vars.push(`--pick-val-edge:${edge}`, `--pick-val-bg:${bg}`);
  }
  return vars.join(";");
}

/** "+12", "−4" (true minus sign) or "0". */
export const formatValue = (v: number) => (v > 0 ? `+${v}` : v < 0 ? `−${Math.abs(v)}` : "0");
