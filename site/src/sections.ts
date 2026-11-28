// Every top-level section, in nav order. `built` sections have real pages;
// the rest render the shared "Coming soon" page.
export type Section = { label: string; href: string; built: boolean; blurb: string };

export const SECTIONS: Section[] = [
  { label: "Home", href: "/", built: true, blurb: "" },
  { label: "Seasons", href: "/seasons/", built: true, blurb: "" },
  { label: "Owners", href: "/owners/", built: true, blurb: "Every Owner's trophy case, career record and rivalries." },
  { label: "Matchups", href: "/matchups/", built: true, blurb: "Every championship, the biggest blowouts and upsets, and every rivalry." },
  { label: "Record Book", href: "/record-book/", built: true, blurb: "Single-week, season and all-time records, streaks, luck and Last place history." },
  { label: "Hall of Fame", href: "/hall-of-fame/", built: true, blurb: "The league's legendary player seasons." },
  { label: "Draft", href: "/draft/", built: true, blurb: "Every Season's first round, and links to each draft board." },
  { label: "Transactions", href: "/transactions/", built: true, blurb: "Trades and waiver pickups, and who won them." },
  { label: "League Rules", href: "/league-rules/", built: false, blurb: "Scoring, rosters and how the rules changed." },
];

