// Loads site-data JSON at build time and checks it against the contract
// (contract/site-data.schema.json). The site renders only from these documents.
import fs from "node:fs";
import path from "node:path";
import Ajv2020 from "ajv/dist/2020.js";

// Injected by astro.config.mjs as an absolute path (bundling moves this module, so not import.meta.url)
declare const __SITE_DATA_SCHEMA__: string;
const SCHEMA_PATH = __SITE_DATA_SCHEMA__;

export type OwnerRef = { slug: string; name: string };
export type League = {
  leagueName: string;
  seasons: { year: number; teamCount: number }[];
  champion: { owner: OwnerRef; teamName: string; year: number };
};

type Kind = "league" | "trophyShelf" | "ownerIndex" | "owner" | "season" | "draft" | "matchups";

let ajv: Ajv2020 | undefined;
let schemaId = "";

function validator(kind: Kind) {
  if (!ajv) {
    const schema = JSON.parse(fs.readFileSync(SCHEMA_PATH, "utf-8"));
    schemaId = schema.$id;
    ajv = new Ajv2020({ allErrors: true, strict: false });
    ajv.addSchema(schema);
  }
  const validate = ajv.getSchema(`${schemaId}#/$defs/${kind}`);
  if (!validate) throw new Error(`site-data schema has no entry point for ${kind}`);
  return validate;
}

function dataDir(): string {
  // Required on purpose: a forgotten variable must not build the site from the wrong data
  const dir = process.env.SITE_DATA_DIR;
  if (!dir) throw new Error("SITE_DATA_DIR is not set: point it at the exported site data (export/)");
  return path.resolve(dir);
}

function load<T>(relPath: string, kind: Kind): T {
  const file = path.join(dataDir(), relPath);
  const doc = JSON.parse(fs.readFileSync(file, "utf-8"));
  const validate = validator(kind);
  if (!validate(doc)) {
    const errors = (validate.errors ?? []).map((e) => `  - ${e.instancePath || "/"}: ${e.message}`).join("\n");
    throw new Error(`${relPath} breaks the site-data contract:\n${errors}`);
  }
  return doc as T;
}

let league: League | undefined;
export function getLeague(): League {
  league ??= load<League>("league.json", "league");
  return league;
}

export type WinLossTie = { wins: number; losses: number; ties: number };
export type PodiumSpot = { place: 1 | 2 | 3; owner: OwnerRef; teamName: string; record: WinLossTie };
export type Punishment = { title: string; description: string; image: string | null };
export type Season = {
  year: number;
  teamCount: number;
  dataTier: "full" | "partial";
  podium: [PodiumSpot, PodiumSpot, PodiumSpot];
  lastPlace: { owner: OwnerRef; teamName: string; record: WinLossTie; punishment: Punishment | null };
  scoringFormat: ScoringFormat;
  standings: StandingsRow[];
  bracket: Bracket;
  weeklyResults: WeeklyPeriod[];
  draft: Draft;
};
export type DraftPlayer = { name: string; position: string; nflTeam: string | null };
export type DraftPick = {
  overall: number;
  round: number;
  roundPick: number;
  owner: OwnerRef;
  player: DraftPlayer | null;
  points: number | null;
  positionalFinish: number | null;
  valueOverSlot: number | null;
};
export type GradedPick = { overall: number; round: number; roundPick: number; player: DraftPlayer; valueOverSlot: number };
export type DraftGrade = { rank: number; owner: OwnerRef; teamName: string; total: number; best: GradedPick; worst: GradedPick };
export type Draft = {
  type: "snake" | "offline";
  rounds: number;
  order: { slot: number; owner: OwnerRef; teamName: string }[];
  picks: DraftPick[];
  note: string | null;
  grades: DraftGrade[];
};

/** A Pick as round.pick: "3.07". */
export const formatPick = (p: { round: number; roundPick: number }) => `${p.round}.${String(p.roundPick).padStart(2, "0")}`;
export type WeeklySide = { owner: OwnerRef; teamName: string; score: number | null };
export type WeeklyMatchup = {
  home: WeeklySide;
  away: WeeklySide | null;
  winner: "home" | "away" | null;
  isTie: boolean;
  isBye: boolean;
};
export type WeeklyPeriod = { matchupPeriod: number; weeks: number[]; matchups: WeeklyMatchup[] };
export type BracketSide = { seed: number; owner: OwnerRef; teamName: string; score: number | null };
export type BracketMatchup = {
  home: BracketSide;
  away: BracketSide | null;
  winner: "home" | "away" | null;
  isTie: boolean;
  isBye: boolean;
};
export type BracketRound = { name: string; matchupPeriod: number; weeks: number[]; matchups: BracketMatchup[] };
export type Bracket = {
  rounds: BracketRound[];
  thirdPlaceGame: { matchupPeriod: number; weeks: number[]; matchup: BracketMatchup };
};

/** "Week 15", or "Weeks 14–15" for a two-week round. */
export const formatWeeks = (w: number[]) => (w.length > 1 ? `Weeks ${w[0]}–${w[w.length - 1]}` : `Week ${w[0]}`);
export type ScoringFormat = {
  label: string;
  receptionPoints: number;
  tePremium: number;
  keyValues: { label: string; points: number }[];
  rosterSlots: { slot: string; count: number }[];
};
export type StandingsRow = {
  rank: number;
  owner: OwnerRef;
  teamName: string;
  record: WinLossTie;
  pointsFor: number;
  pointsAgainst: number;
  playoffSeed: number;
};

/** Season points with thousands separators and two decimals: "1,499.50". */
export const formatPoints = (n: number) =>
  n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const seasons = new Map<number, Season>();
export function getSeason(year: number): Season {
  if (!seasons.has(year)) seasons.set(year, load<Season>(`seasons/${year}.json`, "season"));
  return seasons.get(year)!;
}

/** "9-5", or "8-5-1" when there were ties. */
export const formatRecord = (r: WinLossTie) => (r.ties ? `${r.wins}-${r.losses}-${r.ties}` : `${r.wins}-${r.losses}`);

export type ShelfEntry = {
  owner: OwnerRef;
  currentTeamName: string;
  titles: number[];
  runnerUps: number[];
  firstSeason: number;
  lastSeason: number;
  isFormer: boolean;
};

let shelf: ShelfEntry[] | undefined;
/** Every Owner, ordered by titles, then runner-ups, then name (the pipeline's order). */
export function getTrophyShelf(): ShelfEntry[] {
  shelf ??= load<{ owners: ShelfEntry[] }>("trophy-shelf.json", "trophyShelf").owners;
  return shelf;
}

export type OwnerIndexEntry = {
  owner: OwnerRef;
  currentTeamName: string;
  firstSeason: number;
  lastSeason: number;
  isFormer: boolean;
  titles: number[];
  runnerUps: number[];
  regularSeason: WinLossTie;
};

let ownerIndex: OwnerIndexEntry[] | undefined;
/** Every Owner for the Owners index, in trophy-shelf order (the pipeline's order). */
export function getOwnerIndex(): OwnerIndexEntry[] {
  ownerIndex ??= load<{ owners: OwnerIndexEntry[] }>("owners.json", "ownerIndex").owners;
  return ownerIndex;
}

/** "2018–2025", or "2020" for a single Season. */
export const formatSpan = (first: number, last: number) => (first === last ? String(first) : `${first}–${last}`);

export type OwnerSeasonRow = {
  year: number;
  teamName: string;
  record: WinLossTie;
  pointsFor: number;
  pointsAgainst: number;
  playoffSeed: number;
  finalRank: number;
  podiumPlace: 1 | 2 | 3 | null;
  isLastPlace: boolean;
};
export type HeadToHeadRow = { opponent: OwnerRef; regularSeason: WinLossTie; playoffs: WinLossTie; meetings: number };
export type OwnerDoc = {
  owner: OwnerRef;
  currentTeamName: string;
  firstSeason: number;
  lastSeason: number;
  isFormer: boolean;
  trophies: { titles: number[]; runnerUps: number[]; thirds: number[] };
  career: {
    regularSeason: WinLossTie;
    playoffs: WinLossTie;
    avgPointsFor: number;
    avgPointsAgainst: number;
    playoffAppearances: number[];
    lastPlaces: number[];
  };
  seasons: OwnerSeasonRow[];
  headToHead: HeadToHeadRow[];
  draft: OwnerDraftSeason[];
};
export type OwnerDraftSeason = {
  year: number;
  teamName: string;
  slot: number;
  grade: { rank: number; of: number; total: number };
  picks: {
    overall: number;
    round: number;
    roundPick: number;
    player: DraftPlayer | null;
    points: number | null;
    positionalFinish: number | null;
    valueOverSlot: number | null;
  }[];
};

const ownerDocs = new Map<string, OwnerDoc>();
export function getOwner(slug: string): OwnerDoc {
  if (!ownerDocs.has(slug)) ownerDocs.set(slug, load<OwnerDoc>(`owners/${slug}.json`, "owner"));
  return ownerDocs.get(slug)!;
}

export type FirstRoundPick = { overall: number; owner: OwnerRef; teamName: string; player: DraftPlayer | null };
export type DraftHistorySeason = { year: number; teamCount: number; type: "snake" | "offline"; firstRound: FirstRoundPick[] };

export type AllTimePick = {
  year: number;
  owner: OwnerRef;
  teamName: string;
  overall: number;
  round: number;
  roundPick: number;
  player: DraftPlayer;
  positionalFinish: number;
  valueOverSlot: number;
};
export type BestDrafter = { owner: OwnerRef; seasons: number; averageRank: number };
export type DraftHistory = {
  seasons: DraftHistorySeason[];
  bestPicks: AllTimePick[];
  worstPicks: AllTimePick[];
  bestDrafters: BestDrafter[];
};

let draftHistory: DraftHistory | undefined;
/** draft.json: every Season's first round (newest first), the all-time best and worst Picks, and Best
 * drafters, all in the pipeline's order. */
export function getDraftHistory(): DraftHistory {
  draftHistory ??= load<DraftHistory>("draft.json", "draft");
  return draftHistory;
}

/** "1st", "2nd", "3rd", "11th". */
export const ordinal = (n: number) => {
  const tail = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${tail}`;
};

export type Championship = {
  year: number;
  matchupPeriod: number;
  weeks: number[];
  champion: BracketSide;
  runnerUp: BracketSide;
  margin: number;
};
export type LeaderboardSide = { owner: OwnerRef; teamName: string; score: number; seed: number | null };
type LeaderboardBase = { year: number; matchupPeriod: number; weeks: number[]; kind: "regular" | "playoff"; scoringFormat: string };
export type LeaderboardGame = LeaderboardBase & { winner: LeaderboardSide; loser: LeaderboardSide; isTie: boolean; margin: number };
export type LeaderboardUpset = LeaderboardGame & { seedGap: number };
export type LeaderboardScore = LeaderboardBase & { team: LeaderboardSide; opponent: LeaderboardSide; result: "win" | "loss" | "tie" };
export type Leaderboards = {
  blowouts: LeaderboardGame[];
  closestGames: LeaderboardGame[];
  highestScores: LeaderboardScore[];
  lowestScores: LeaderboardScore[];
  playoffUpsets: LeaderboardUpset[];
};
export type MatchupsDoc = { championships: Championship[]; leaderboards: Leaderboards };

let matchupsDoc: MatchupsDoc | undefined;
/** matchups.json: the Matchups section (championship cards, newest first). */
export function getMatchups(): MatchupsDoc {
  matchupsDoc ??= load<MatchupsDoc>("matchups.json", "matchups");
  return matchupsDoc;
}
