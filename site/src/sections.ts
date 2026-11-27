// Every top-level section, in nav order. `built` sections have real pages;
// the rest render the shared "Coming soon" page.
export type Section = { label: string; href: string; built: boolean; blurb: string };

export const SECTIONS: Section[] = [
  { label: "Home", href: "/", built: true, blurb: "" },
  { label: "Seasons", href: "/seasons/", built: true, blurb: "" },
  { label: "Owners", href: "/owners/", built: false, blurb: "Every Owner's trophy case, career record and rivalries." },
  { label: "Matchups", href: "/matchups/", built: false, blurb: "Every Matchup, bracket history, blowouts and upsets." },
  { label: "Record Book", href: "/record-book/", built: false, blurb: "Single-week, season and all-time records." },
  { label: "Hall of Fame", href: "/hall-of-fame/", built: false, blurb: "The league's legendary player seasons." },
  { label: "Draft", href: "/draft/", built: false, blurb: "Every draft board, graded by value over slot." },
  { label: "Transactions", href: "/transactions/", built: false, blurb: "Trades and waiver pickups, and who won them." },
  { label: "League Rules", href: "/league-rules/", built: false, blurb: "Scoring, rosters and how the rules changed." },
];

