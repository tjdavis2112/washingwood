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

type Kind = "league" | "trophyShelf" | "ownerIndex" | "owner" | "season" | "draft" | "matchups" | "rivalry" | "boxScores" | "recordBook" | "transactions" | "hallOfFame";

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
  pointsOverExpected: number | null;
};
export type GradedPick = { overall: number; round: number; roundPick: number; player: DraftPlayer; pointsOverExpected: number };
export type ReplacementLevel = { position: string; finish: number; points: number };
export type DraftGrade = { rank: number; owner: OwnerRef; teamName: string; total: number; best: GradedPick; worst: GradedPick };
export type Draft = {
  type: "snake" | "offline";
  rounds: number;
  order: { slot: number; owner: OwnerRef; teamName: string }[];
  picks: DraftPick[];
  note: string | null;
  replacement: ReplacementLevel[];
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
/** A signed points figure such as Value added: +12.50, −3.25 (a true minus sign) or 0.00. */
export const formatSigned = (n: number) => (n > 0 ? `+${formatPoints(n)}` : n < 0 ? `−${formatPoints(-n)}` : formatPoints(0));

const seasons = new Map<number, Season>();
export function getSeason(year: number): Season {
  if (!seasons.has(year)) seasons.set(year, load<Season>(`seasons/${year}.json`, "season"));
  return seasons.get(year)!;
}

/** "9-5", or "8-5-1" when there were ties. */
/** A 0-1 win % as a percentage to one decimal, e.g. 0.9259 -> "92.6%". */
export const formatPct = (n: number) => `${(n * 100).toFixed(1)}%`;
/** A Luck index with its sign: +1.6, 0.0, −2.1 (a true minus sign). */
export const formatLuck = (n: number) => (n > 0 ? `+${n.toFixed(1)}` : n < 0 ? `−${Math.abs(n).toFixed(1)}` : "0.0");
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
    pointsOverExpected: number | null;
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
  points: number;
  positionalFinish: number;
  valueOverSlot: number;
  pointsOverExpected: number;
};
export type BestDrafter = { owner: OwnerRef; seasons: number; averageRank: number };
export type DraftHistory = {
  seasons: DraftHistorySeason[];
  steals: AllTimePick[];
  hits: AllTimePick[];
  busts: AllTimePick[];
  bestDrafters: BestDrafter[];
};

let draftHistory: DraftHistory | undefined;
/** draft.json: every Season's first round (newest first), the all-time Steals, Hits and Busts, and
 * Best drafters, all in the pipeline's order. */
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
export type LeaderboardProjectionUpset = LeaderboardGame & { winnerProjected: number; loserProjected: number; projectedDeficit: number };
export type LeaderboardScore = LeaderboardBase & { team: LeaderboardSide; opponent: LeaderboardSide; result: "win" | "loss" | "tie" };
export type Leaderboards = {
  blowouts: LeaderboardGame[];
  closestGames: LeaderboardGame[];
  highestScores: LeaderboardScore[];
  lowestScores: LeaderboardScore[];
  playoffUpsets: LeaderboardUpset[];
  projectionUpsets: LeaderboardProjectionUpset[];
};
export type RivalryGrid = {
  owners: OwnerRef[];
  records: { owner: string; opponent: string; wins: number; losses: number; ties: number }[];
};
export type MatchupsDoc = { championships: Championship[]; leaderboards: Leaderboards; rivalryGrid: RivalryGrid };

let matchupsDoc: MatchupsDoc | undefined;
/** matchups.json: the Matchups section (championship cards, newest first). */
export function getMatchups(): MatchupsDoc {
  matchupsDoc ??= load<MatchupsDoc>("matchups.json", "matchups");
  return matchupsDoc;
}

export type RivalryGame = {
  year: number;
  matchupPeriod: number;
  weeks: number[];
  kind: "regular" | "playoff" | "thirdPlace" | "consolation";
  inRecord: boolean;
  teams: [{ teamName: string; score: number }, { teamName: string; score: number }];
  winner: 0 | 1 | null;
  isTie: boolean;
  margin: number;
};
export type RivalrySide = { owner: OwnerRef; regularSeason: WinLossTie; playoffs: WinLossTie; biggestWin: RivalryGame | null };
export type Rivalry = { sides: [RivalrySide, RivalrySide]; meetings: number; games: RivalryGame[] };

/** The Rivalry page path for two Owners: slugs in alphabetical order, so each pair has one URL. */
export const rivalryPath = (a: string, b: string) => `/matchups/${[a, b].sort().join("-vs-")}/`;

const rivalries = new Map<string, Rivalry>();
export function getRivalry(pair: string): Rivalry {
  if (!rivalries.has(pair)) rivalries.set(pair, load<Rivalry>(`rivalries/${pair}.json`, "rivalry"));
  return rivalries.get(pair)!;
}

export type BoxScoreEntry = { slot: string; name: string; position: string; nflTeam: string | null; points: number | null; projected: number | null };
export type BoxScoreWeek = { week: number; starters: BoxScoreEntry[]; bench: BoxScoreEntry[]; emptySlots: string[] };
export type BoxScoreSide = { owner: OwnerRef; teamName: string; score: number; projected: number; adjustment: number; weeks: BoxScoreWeek[] };
export type BoxScore = {
  matchupPeriod: number;
  weeks: number[];
  kind: "regular" | "playoff" | "thirdPlace" | "consolation";
  home: BoxScoreSide;
  away: BoxScoreSide;
  winner: "home" | "away" | null;
  isTie: boolean;
};

/** A Box score page: /matchups/<year>/<first week>/<a>-vs-<b>/, slugs in alphabetical order. */
export const boxScorePath = (year: number, week: number, a: string, b: string) =>
  `/matchups/${year}/${week}/${[a, b].sort().join("-vs-")}/`;

/** Seasons with lineups have Box scores (a Season without lineups has no box-scores file). */
export function hasBoxScores(year: number): boolean {
  return fs.existsSync(path.join(dataDir(), "box-scores", `${year}.json`));
}

const boxScores = new Map<number, BoxScore[]>();
export function getBoxScores(year: number): BoxScore[] {
  if (!boxScores.has(year)) boxScores.set(year, load<{ year: number; matchups: BoxScore[] }>(`box-scores/${year}.json`, "boxScores").matchups);
  return boxScores.get(year)!;
}

export type LastPlaceRow = { year: number; owner: OwnerRef; teamName: string; record: WinLossTie; pointsFor: number; scoringFormat: string };
export type LastPlaceTally = { owner: OwnerRef; count: number; years: number[] };
export type SeasonRecordRow = {
  year: number; owner: OwnerRef; teamName: string; record: WinLossTie; games: number; winPct: number;
  pointsFor: number; pointsPerGame: number; pointsAgainst: number; pointsAgainstPerGame: number; benchPoints: number | null;
  expectedWins: number | null; luck: number | null;
  scoringFormat: string;
};
export type SeasonRecordKey = "bestWinPct" | "worstWinPct" | "mostPointsFor" | "fewestPointsFor" | "mostPointsAgainst" | "mostBenchPoints"
  | "luckiest" | "unluckiest";
export type WeekRecordRow = {
  year: number; matchupPeriod: number; week: number; kind: "regular" | "playoff"; team: LeaderboardSide;
  opponent: LeaderboardSide; result: "win" | "loss" | "tie"; benchPoints: number | null; scoringFormat: string;
};
export type WeekRecordKey = "mostPointsInLoss" | "fewestPointsInWin" | "mostBenchPoints";
export type StreakRow = {
  owner: OwnerRef; length: number; start: { year: number; week: number }; end: { year: number; week: number };
  active: boolean;
};
export type AllTimeRow = {
  owner: OwnerRef; seasons: number; record: WinLossTie; games: number; winPct: number;
  pointsFor: number; pointsPerGame: number; benchPoints: number | null; luck: number | null; longestWinStreak: number;
  longestLossStreak: number; lastPlaces: number;
};
export type RecordBookDoc = {
  week: Record<WeekRecordKey, WeekRecordRow[]>;
  season: Record<SeasonRecordKey, SeasonRecordRow[]>;
  allTime: AllTimeRow[];
  streaks: { wins: StreakRow[]; losses: StreakRow[] };
  lastPlace: { seasons: LastPlaceRow[]; tally: LastPlaceTally[] };
};

let recordBookDoc: RecordBookDoc | undefined;
/** record-book.json: the Record Book section (Season records, All-time table, Last place history and tally). */
export function getRecordBook(): RecordBookDoc {
  recordBookDoc ??= load<RecordBookDoc>("record-book.json", "recordBook");
  return recordBookDoc;
}

export type TradedPlayer = { name: string; position: string; nflTeam: string | null; points: number; value: number; weeksStarted: number };
export type TradeSide = {
  owner: OwnerRef; teamName: string; outcome: "won" | "lost" | "tied"; total: number; rawTotal: number; players: TradedPlayer[];
};
export type Trade = {
  year: number; week: number; scoringFormat: string; margin: number; fleeced: boolean; sides: [TradeSide, TradeSide];
};
export type Pickup = {
  name: string; position: string; nflTeam: string | null; owner: OwnerRef; teamName: string; year: number; week: number;
  via: "waiver" | "free_agent"; points: number; value: number; weeksStarted: number; scoringFormat: string;
};
export type TradeRecord = { owner: OwnerRef; trades: number; won: number; lost: number; tied: number; netPoints: number };
export type TransactionsDoc = {
  trades: Trade[]; pickups: Pickup[]; seasonPickups: { year: number; pickups: Pickup[] }[];
  tradeRecords: TradeRecord[]; ownerPickups: { owner: OwnerRef; pickups: Pickup[] }[];
  activity: { owner: OwnerRef; trades: number; pickups: number }[];
};

let transactionsDoc: TransactionsDoc | undefined;
/** transactions.json: every executed trade, newest first. Season and Owner pages filter it (one source). */
export function getTransactions(): TransactionsDoc {
  transactionsDoc ??= load<TransactionsDoc>("transactions.json", "transactions");
  return transactionsDoc;
}

/** dominant: Points above replacement; overachiever: Points over expected (whole points); waiver_legend: the best
 * Pickup's Value added. Each lane names its own Owner, which can differ from the Inductee's credited one. */
export type InductionLane = { lane: "dominant" | "overachiever" | "waiver_legend"; value: number; owner: OwnerRef };
export type Inductee = {
  year: number; scoringFormat: string; name: string; position: string; nflTeam: string | null; owner: OwnerRef;
  teamName: string; lanes: InductionLane[];
  /** null when the Archive has no Season points for him (only a Waiver legend can be) */
  points: number | null; positionalFinish: number | null;
};
export type HallOfFameDoc = { inductees: Inductee[] };

let hallOfFameDoc: HallOfFameDoc | undefined;
/** hall-of-fame.json: every Inductee, newest Season first. Season and Owner pages filter it (one source). */
export function getHallOfFame(): HallOfFameDoc {
  hallOfFameDoc ??= load<HallOfFameDoc>("hall-of-fame.json", "hallOfFame");
  return hallOfFameDoc;
}
