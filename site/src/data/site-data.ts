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

type Kind = "league" | "trophyShelf" | "season";

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
