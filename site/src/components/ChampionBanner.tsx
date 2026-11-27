// Home's Champion banner. The Champion's name links to their Owner page and a second link opens
// that Season's page (a link can't hold another link, so the card itself isn't one). A React
// island only for the hover lift (Motion); all text is rendered at build time.
import { MotionConfig, motion } from "motion/react";
import type { ReactNode } from "react";

// children: the trophy art, passed in as Astro slot content
type Props = { ownerName: string; ownerSlug: string; teamName: string; year: number; children?: ReactNode };

export default function ChampionBanner({ ownerName, ownerSlug, teamName, year, children }: Props) {
  return (
    <MotionConfig reducedMotion="user">
      <section aria-labelledby="champion-heading">
        <motion.div
          whileHover={{ y: -4 }}
          transition={{ type: "spring", stiffness: 300, damping: 24 }}
          className="relative block overflow-hidden rounded-3xl border border-line bg-gradient-to-br from-panel via-ink to-brand-deep/40 p-6 shadow-2xl transition-colors hover:border-brand/60 md:p-12"
        >
          <div aria-hidden="true" className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full bg-brand/20 blur-3xl" />
          <div className="relative flex flex-col items-center gap-6 text-center md:flex-row md:items-center md:gap-10 md:text-left">
            <div className="size-24 shrink-0 drop-shadow-[0_0_24px_color-mix(in_srgb,var(--color-gold)_35%,transparent)] md:size-36">
              {children}
            </div>
            <div className="min-w-0">
              <h2 id="champion-heading" className="text-xs font-semibold uppercase tracking-[0.3em] text-brand">
                {year} Champion
              </h2>
              <p className="mt-3 text-4xl font-black leading-tight break-words md:text-6xl">
                <a href={`/owners/${ownerSlug}/`} data-owner-link className="transition-colors hover:text-brand">
                  {ownerName}
                </a>
              </p>
              <p className="mt-2 text-lg text-muted md:text-xl">{teamName}</p>
              <a
                href={`/seasons/${year}/`}
                className="mt-5 inline-block text-sm font-semibold text-brand transition-colors hover:text-paper"
              >
                See the {year} Season →
              </a>
            </div>
          </div>
        </motion.div>
      </section>
    </MotionConfig>
  );
}
