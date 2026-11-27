// Extra `wrangler pages dev` servers over the same build, with different secrets,
// to see how the gate behaves when Cloudflare's secrets change.
import { type ChildProcess, spawn, spawnSync } from "node:child_process";
import { request } from "@playwright/test";

export type Server = { url: string; stop: () => void };

async function answers(url: string): Promise<boolean> {
  try {
    await (await request.newContext()).get(`${url}/robots.txt`, { timeout: 1000 });
    return true;
  } catch {
    return false;
  }
}

export async function startServer(port: number, bindings: Record<string, string>): Promise<Server> {
  const url = `http://127.0.0.1:${port}`;
  // A leftover server would answer with the wrong secrets and make the test lie
  if (await answers(url)) throw new Error(`port ${port} is already in use: stop the old server first`);
  const args = ["wrangler", "pages", "dev", "dist", "--ip", "127.0.0.1", "--port", String(port)];
  for (const [k, v] of Object.entries(bindings)) args.push("--binding", `"${k}=${v}"`);
  const proc: ChildProcess = spawn("npx", args, {
    shell: true,
    stdio: "ignore",
    env: { ...process.env, WRANGLER_SEND_METRICS: "false" },
  });
  const stop = () => {
    // Synchronous, so it finishes before the worker exits
    if (process.platform !== "win32") return void proc.kill();
    if (proc.pid) spawnSync("taskkill", ["/pid", String(proc.pid), "/T", "/F"]);
    // wrangler's workerd process can outlive its parent's tree on Windows: stop whatever still holds the port
    const byPort = `Get-NetTCPConnection -State Listen -LocalPort ${port} -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }`;
    spawnSync("powershell", ["-NoProfile", "-Command", byPort]);
  };
  for (let i = 0; i < 120; i++) {
    // Any HTTP answer means it's up (a server missing secrets answers 503 on purpose)
    if (await answers(url)) return { url, stop };
    await new Promise((r) => setTimeout(r, 500));
  }
  stop();
  throw new Error(`server on ${port} didn't start`);
}

// One port block per Playwright project, so phone and desktop runs never share a server
export const portsFor = (project: string) => (project === "phone" ? [8790, 8791, 8792] : [8793, 8794, 8795]);
