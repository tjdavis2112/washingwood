// Draft position tints (muted, non-metallic tokens in global.css). The position is always written out
// next to the tint, so color is never the only signal.
import type { DraftPlayer } from "./site-data";

export const POSITION_TINTS: Record<string, string> = {
  QB: "var(--color-pos-qb)",
  RB: "var(--color-pos-rb)",
  WR: "var(--color-pos-wr)",
  TE: "var(--color-pos-te)",
  K: "var(--color-pos-k)",
  "D/ST": "var(--color-pos-dst)",
};

/** Inline style for a Pick tinted by its Player's position; empty for a Pick with no Player recorded. */
export const pickStyle = (player: DraftPlayer | null) => {
  if (!player) return "";
  const tint = POSITION_TINTS[player.position] ?? "var(--color-pos-other)";
  return `border-color:${tint};background:color-mix(in srgb, ${tint} 35%, transparent)`;
};
