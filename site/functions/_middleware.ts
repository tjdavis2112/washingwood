// Passphrase gate (ADR-0006). Cloudflare Pages runs this before every request.
//
// - The landing screen (/enter/) and robots.txt are the only things served without a valid cookie.
//   Pages redirect there; everything else (site data, images, scripts) gets a 401.
// - POST /enter/ checks the passphrase in constant time. On success it sets a session cookie:
//   HMAC keyed by SESSION_KEY over the passphrase. Changing either secret signs everyone out,
//   and a stolen cookie can't be used to guess the passphrase offline without SESSION_KEY.
// - Missing secrets fail closed (503 for everything).
// - Every response carries noindex, anti-framing and no-shared-cache headers.

interface Env {
  SITE_PASSPHRASE?: string; // Cloudflare secret: the shared passphrase members type
  SESSION_KEY?: string; // Cloudflare secret: 32+ random bytes; signs session cookies
  ASSETS: Fetcher; // the static build
}

const LANDING = "/enter/";
const COOKIE_NAME = "__Host-ww_session"; // __Host-: Secure, Path=/, no Domain, so subdomains can't plant it
const MAX_AGE = 365 * 24 * 60 * 60; // about a year, in seconds
const SESSION_LABEL = "washingwood-session-v1|"; // prefixed to the passphrase before signing
const PUBLIC_PATHS = new Set(["/robots.txt"]);

const SECURITY_HEADERS = {
  "X-Robots-Tag": "noindex, nofollow",
  "X-Frame-Options": "DENY",
  "Content-Security-Policy": "frame-ancestors 'none'",
  "Referrer-Policy": "same-origin",
  // League pages and images must never sit in a shared cache
  "Cache-Control": "private, no-cache",
};

const encoder = new TextEncoder();

export const onRequest: PagesFunction<Env> = async (context) => {
  const response = await gate(context);
  // Redirects and some asset responses are immutable; copy before adding headers
  const out = new Response(response.body, response);
  for (const [k, v] of Object.entries(SECURITY_HEADERS)) out.headers.set(k, v);
  return out;
};

async function gate({ request, env, next }: EventContext<Env, string, unknown>): Promise<Response> {
  const url = new URL(request.url);
  const { SITE_PASSPHRASE: passphrase, SESSION_KEY: sessionKey } = env;
  if (!passphrase || !sessionKey) return new Response("Site not configured", { status: 503 }); // fail closed
  if (PUBLIC_PATHS.has(url.pathname)) return next();

  const session = await sessionValue(sessionKey, passphrase);
  const signedIn = timingSafeEqual(readCookie(request, COOKIE_NAME) ?? "", session);
  const onLanding = url.pathname === LANDING || url.pathname === "/enter";

  if (onLanding && request.method === "POST") {
    return (await passphraseMatches(request, passphrase)) ? signInResponse(url, session) : wrongPassphrase(env, url);
  }
  if (onLanding) return signedIn ? redirect(new URL("/", url), 302) : next();
  if (signedIn) return next();

  // Signed out: send page navigations to the landing screen, refuse everything else
  const wantsPage = request.method === "GET" && (request.headers.get("Accept") ?? "").includes("text/html");
  return wantsPage ? redirect(new URL(LANDING, url), 302) : new Response("Passphrase required", { status: 401 });
}

async function passphraseMatches(request: Request, passphrase: string): Promise<boolean> {
  const form = await request.formData().catch(() => null);
  const given = form?.get("passphrase");
  // Compare fixed-length digests so neither content nor length leaks through timing
  return typeof given === "string" && timingSafeEqual(await digest(given), await digest(passphrase));
}

function signInResponse(url: URL, session: string): Response {
  const res = redirect(new URL("/", url), 303);
  res.headers.append("Set-Cookie", `${COOKIE_NAME}=${session}; Max-Age=${MAX_AGE}; Path=/; HttpOnly; Secure; SameSite=Lax`);
  return res;
}

async function wrongPassphrase(env: Env, url: URL): Promise<Response> {
  // The landing page with its error line shown (it ships hidden)
  const page = await env.ASSETS.fetch(new URL(LANDING, url));
  const shown = new HTMLRewriter()
    .on("[data-gate-error]", { element: (el) => void el.removeAttribute("hidden") })
    .transform(page);
  return new Response(shown.body, { status: 401, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

function redirect(to: URL, status: 302 | 303): Response {
  return new Response(null, { status, headers: { Location: to.toString() } });
}

async function sessionValue(sessionKey: string, passphrase: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", encoder.encode(sessionKey), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
  ]);
  return base64url(await crypto.subtle.sign("HMAC", key, encoder.encode(SESSION_LABEL + passphrase)));
}

async function digest(text: string): Promise<string> {
  return base64url(await crypto.subtle.digest("SHA-256", encoder.encode(text)));
}

function timingSafeEqual(a: string, b: string): boolean {
  // Length is not secret here (both sides are fixed-length encodings); content is compared without early exit
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function readCookie(request: Request, name: string): string | undefined {
  for (const part of (request.headers.get("Cookie") ?? "").split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return undefined;
}

function base64url(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}
