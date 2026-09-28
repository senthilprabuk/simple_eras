#!/usr/bin/env node
// Headless-browser driver for the ERAS frontend (Windows), with no dependencies: it starts
// Edge (or Chrome) headless and speaks the DevTools protocol over Node's built-in
// WebSocket. Reads one command per line from stdin, like chromium-cli:
//
//   nav <url>                  open a page and wait for it to load
//   wait-for text=<text>       wait (30s) until the page shows the text
//   wait-for <css>             wait (30s) until an element matches
//   wait-gone text=<text>|<css>  wait (30s) until it is gone, e.g. text=Loading
//   fill <css> <text>          focus the input and type (fires React's onChange)
//   click text=<text>          click the button/link whose text contains <text>
//   click <css>                click the first element matching <css>
//   scroll-to text=<text>|<css>  bring it to the top of the view (screenshots show the view only)
//   viewport <w>x<h>           resize the page, e.g. viewport 460x900
//   text [chars]               print the page's visible text (default 600 chars)
//   eval <js>                  print the value of a JS expression
//   screenshot [name]          save a PNG; prints its path
//   console                    print console errors, exceptions and failed loads so far
//
// Blank lines and lines starting with # are skipped. The first failing command
// saves failure.png and exits 1. Screenshots go to $SHOTS_DIR, default
// <os tmpdir>/run-simple-eras/shots. The browser is $BROWSER, else Edge, else Chrome.

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BROWSERS = [
  process.env.BROWSER,
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
].filter(Boolean);
const SHOTS_DIR = process.env.SHOTS_DIR || join(tmpdir(), "run-simple-eras", "shots");
const TIMEOUT_MS = 30_000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function until(what, fn, timeout = TIMEOUT_MS) {
  const end = Date.now() + timeout;
  for (;;) {
    const value = await fn();
    if (value) return value;
    if (Date.now() > end) throw new Error(`timed out after ${timeout / 1000}s waiting for ${what}`);
    await sleep(250);
  }
}

async function launchBrowser() {
  const exe = BROWSERS.find((p) => existsSync(p));
  if (!exe) throw new Error(`no Edge or Chrome found; set BROWSER. Tried: ${BROWSERS.join(", ")}`);
  const profile = mkdtempSync(join(tmpdir(), "run-simple-eras-profile-"));
  const child = spawn(exe, [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--hide-scrollbars", "--window-size=1280,800", "--remote-debugging-port=0",
    `--user-data-dir=${profile}`, "about:blank",
  ], { stdio: "ignore" });
  // With port 0 the browser picks a free port and writes it to DevToolsActivePort.
  const portFile = join(profile, "DevToolsActivePort");
  const [port, path] = await until("the browser's DevTools port", () =>
    existsSync(portFile) && readFileSync(portFile, "utf8").trim().split("\n").length === 2
      ? readFileSync(portFile, "utf8").trim().split("\n") : null, 20_000);
  return { child, profile, url: `ws://127.0.0.1:${port}${path}` };
}

class CDP {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 0;
    this.pending = new Map();
    this.listeners = [];
    ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(`${msg.error.message}`));
        else resolve(msg.result);
      } else if (msg.method) {
        for (const listener of this.listeners) listener(msg);
      }
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.nextId;
    this.ws.send(JSON.stringify({ id, method, params, sessionId }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }
}

async function connect(url) {
  const ws = new WebSocket(url);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", () => reject(new Error(`cannot connect to ${url}`)), { once: true });
  });
  return new CDP(ws);
}

async function main() {
  mkdirSync(SHOTS_DIR, { recursive: true });
  const script = readFileSync(0, "utf8").split(/\r?\n/).map((l) => l.trim()).filter((l) => l && !l.startsWith("#"));

  const browser = await launchBrowser();
  const cdp = await connect(browser.url);
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const page = (method, params) => cdp.send(method, params, sessionId);

  const problems = [];
  cdp.listeners.push((msg) => {
    if (msg.sessionId !== sessionId) return;
    if (msg.method === "Runtime.exceptionThrown") {
      const d = msg.params.exceptionDetails;
      problems.push(`exception: ${d.exception?.description || d.text}`);
    } else if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
      problems.push(`console.error: ${msg.params.args.map((a) => a.value ?? a.description ?? "").join(" ")}`);
    } else if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
      problems.push(`log: ${msg.params.entry.text} ${msg.params.entry.url || ""}`.trim());
    }
  });
  await page("Page.enable");
  await page("Runtime.enable");
  await page("Log.enable");

  const evaluate = async (expression) => {
    const { result, exceptionDetails } = await page("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (exceptionDetails) throw new Error(exceptionDetails.exception?.description || exceptionDetails.text);
    return result.value;
  };
  // text= prefers an exact match, so "click text=1" hits the 1 button, not 10.
  const selectorFor = (arg) => arg.startsWith("text=")
    ? `((t) => { const all = [...document.querySelectorAll('button, a, [role=button], label')].filter(e => e.innerText);
        return all.find(e => e.innerText.trim() === t) || all.find(e => e.innerText.includes(t)); })(${JSON.stringify(arg.slice(5))})`
    : `document.querySelector(${JSON.stringify(arg)})`;

  let shots = 0;
  const screenshot = async (name) => {
    // A capture during the check-in's slide between screens shows both screens at once.
    // Wait for finite animations to finish; infinite ones (spinners) never do.
    await until("animations to settle", () => evaluate(
      "document.getAnimations().filter(a => a.playState === 'running' && a.effect && a.effect.getComputedTiming().iterations !== Infinity).length === 0",
    ), 3000).catch(() => {});
    const { data } = await page("Page.captureScreenshot", { format: "png" });
    const file = join(SHOTS_DIR, `${String(++shots).padStart(2, "0")}-${name || "shot"}.png`);
    writeFileSync(file, Buffer.from(data, "base64"));
    return file;
  };

  const commands = {
    async nav(url) {
      await page("Page.navigate", { url });
      await until("the page to load", () => evaluate("document.readyState === 'complete'"));
      return url;
    },
    async "wait-for"(arg) {
      const check = arg.startsWith("text=")
        ? `!!document.body && document.body.innerText.includes(${JSON.stringify(arg.slice(5))})`
        : `!!document.querySelector(${JSON.stringify(arg)})`;
      await until(arg, () => evaluate(check));
      return "found";
    },
    async "wait-gone"(arg) {
      const check = arg.startsWith("text=")
        ? `!!document.body && !document.body.innerText.includes(${JSON.stringify(arg.slice(5))})`
        : `!document.querySelector(${JSON.stringify(arg)})`;
      await until(`${arg} to go`, () => evaluate(check));
      return "gone";
    },
    async fill(arg) {
      const space = arg.indexOf(" ");
      const [selector, value] = space < 0 ? [arg, ""] : [arg.slice(0, space), arg.slice(space + 1)];
      const found = await evaluate(`(() => { const e = ${selectorFor(selector)}; if (!e) return false; e.focus(); e.select && e.select(); return true; })()`);
      if (!found) throw new Error(`no element for ${selector}`);
      // insertText goes through the browser's input pipeline, so React sees the change.
      await page("Input.insertText", { text: value });
      return `${selector} filled`;
    },
    async click(arg) {
      const clicked = await evaluate(`(() => { const e = ${selectorFor(arg)}; if (!e) return false; e.scrollIntoView({block: 'center'}); e.click(); return true; })()`);
      if (!clicked) throw new Error(`nothing to click for ${arg}`);
      return "clicked";
    },
    async "scroll-to"(arg) {
      const found = await evaluate(`(() => { const e = ${arg.startsWith("text=")
        ? `[...document.querySelectorAll('h1, h2, h3, h4, p, span, button, a, label, dt, td')].find(e => e.innerText && e.innerText.includes(${JSON.stringify(arg.slice(5))}))`
        : selectorFor(arg)}; if (!e) return false; e.scrollIntoView({block: 'start'}); return true; })()`);
      if (!found) throw new Error(`nothing to scroll to for ${arg}`);
      return "scrolled";
    },
    async viewport(arg) {
      const [width, height] = arg.split("x").map(Number);
      await page("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 600 });
      return `${width}x${height}`;
    },
    async text(arg) {
      return "\n" + String(await evaluate("document.body ? document.body.innerText : ''")).slice(0, Number(arg) || 600);
    },
    async eval(arg) {
      return JSON.stringify(await evaluate(arg));
    },
    async screenshot(arg) {
      return await screenshot(arg);
    },
    async console() {
      return problems.length ? "\n" + problems.join("\n") : "no errors";
    },
  };

  let failed = false;
  for (const line of script) {
    const space = line.indexOf(" ");
    const [name, arg] = space < 0 ? [line, ""] : [line.slice(0, space), line.slice(space + 1)];
    // A check-in link's token is a credential for the patient's day: keep it out of the output.
    const shown = (s) => String(s).replace(/token=[^\s&"]+/g, "token=…");
    try {
      if (!commands[name]) throw new Error(`unknown command: ${name}`);
      console.log(`> ${shown(line)}\n  ${shown(await commands[name](arg))}`);
    } catch (err) {
      console.log(`> ${shown(line)}\n  FAILED: ${err.message}`);
      console.log(`  failure screenshot: ${await screenshot("failure").catch(() => "(none)")}`);
      if (problems.length) console.log(`  console:\n  ${problems.join("\n  ")}`);
      failed = true;
      break;
    }
  }

  await cdp.send("Browser.close").catch(() => {});
  await until("the browser to exit", () => browser.child.exitCode !== null, 10_000).catch(() => browser.child.kill());
  rmSync(browser.profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  process.exit(failed ? 1 : 0);
}

main().catch((err) => {
  console.error(`driver error: ${err.message}`);
  process.exit(2);
});
