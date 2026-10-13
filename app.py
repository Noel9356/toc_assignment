import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY_BYTES = 2_000_000
QUOTE = r"[\"']?"

EMAIL = (
    r"(?P<email>(?<![A-Za-z0-9._%+\-])"
    r"(?P<emailUser>[A-Za-z0-9._%+\-]+)@"
    r"(?P<emailDomain>[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}))"
)

CARD = (
    r"(?P<card>(?<!\d)(?:"
    r"\d{4}(?P<cardSep>[- .]?)\d{4}(?P=cardSep)\d{4}(?P=cardSep)\d{4}"
    r"|\d{4}(?P<cardAmexSep>[- ])\d{6}(?P=cardAmexSep)\d{5}"
    r")(?!\d))"
)

PHONE = (
    r"(?P<phone>(?<![\d+])(?:"
    r"\+66[- ]?\d{1,2}[- ]?\d{3}[- ]?\d{4}"
    r"|\d{3}(?P<phoneSep>[-. ])\d{3}(?P=phoneSep)\d{4}"
    r"|0\d{9}"
    r"|0\d(?P<landSep>[- ])\d{3}(?P=landSep)\d{4}"
    r")(?!\d))"
)

DOB = (
    r"(?P<dob>(?P<dobLabel>(?<![A-Za-z0-9])(?:DOB|Date\s+of\s+Birth|วันเกิด)"
    + QUOTE + r"\s*[:=]\s*" + QUOTE + r")"
    r"(?:"
    r"(?P<dayA>\d{1,2})(?P<sepA>[/\.\-])(?P<monthA>\d{1,2})(?P=sepA)(?P<yearA>\d{4})"
    r"|(?P<yearB>\d{4})(?P<sepB>[/\.\-])(?P<monthB>\d{1,2})(?P=sepB)(?P<dayB>\d{1,2})"
    r")(?!\d))"
)

ADDRESS = (
    r"(?P<address>(?P<addrLabel>(?<![A-Za-z0-9])(?:Address|ที่อยู่)"
    + QUOTE + r"\s*[:=]\s*" + QUOTE
    + r"(?:(?:บ้านเลขที่|เลขที่|No\.?)\s*)?)"
    r"(?P<addrNo>\d+(?:[/\-]\d+)*))"
)

PATTERN = re.compile("|".join([EMAIL, CARD, PHONE, DOB, ADDRESS]), re.IGNORECASE)


def hide_digits(value, keep=4):
    return re.sub(r"\d", "X", value[:-keep]) + value[-keep:]


def mask_email(match):
    user = match.group("emailUser")
    if len(user) == 1:
        masked_user = "*"
    elif len(user) == 2:
        masked_user = user[0] + "*"
    else:
        masked_user = user[0] + "*" * (len(user) - 2) + user[-1]
    return masked_user + "@" + match.group("emailDomain")


def mask_card(match):
    return hide_digits(match.group("card"))


def mask_phone(match):
    return hide_digits(match.group("phone"))


def mask_dob(match):
    if match.group("yearA") is not None:
        separator = match.group("sepA")
        year = match.group("yearA")
        date = "XX" + separator + "XX" + separator + year[:2] + "XX"
    else:
        separator = match.group("sepB")
        year = match.group("yearB")
        date = year[:2] + "XX" + separator + "XX" + separator + "XX"
    return match.group("dobLabel") + date


def mask_address(match):
    return match.group("addrLabel") + re.sub(r"\d", "X", match.group("addrNo"))


MASKERS = {
    "email": mask_email,
    "card": mask_card,
    "phone": mask_phone,
    "dob": mask_dob,
    "address": mask_address,
}


def mask_text(text):
    segments = []
    stats = {kind: 0 for kind in MASKERS}
    position = 0

    for match in PATTERN.finditer(text):
        if match.start() > position:
            segments.append({"text": text[position:match.start()], "kind": None})

        kind = match.lastgroup
        segments.append({
            "text": MASKERS[kind](match),
            "orig": match.group(0),
            "kind": kind,
        })
        stats[kind] += 1
        position = match.end()

    if position < len(text):
        segments.append({"text": text[position:], "kind": None})

    masked = "".join(segment["text"] for segment in segments)
    return masked, segments, stats


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="th" data-theme="light" data-mode="highlight">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDPA Data Masking</title>
<style>
:root {
  color-scheme: light;
  --bg: #f4f6f8;
  --panel: #fff;
  --text: #252b33;
  --muted: #687482;
  --line: #dce2e8;
  --accent: #2563a6;
  --accent-soft: #e8f1fb;
  --warning: #8b4b08;
  --warning-bg: #fff4df;
  --email: #a85d08;
  --card: #b23c57;
  --phone: #176c9d;
  --dob: #7252a5;
  --address: #28754c;
  --radius: 10px;
  --font: "Sarabun", "Noto Sans Thai", system-ui, sans-serif;
  --mono: ui-monospace, SFMono-Regular, Consolas, "Noto Sans Thai", monospace;
}
html[data-theme="dark"] {
  color-scheme: dark;
  --bg: #171b20;
  --panel: #20262d;
  --text: #e6ebf0;
  --muted: #a3afbb;
  --line: #3b454f;
  --accent: #82b7f0;
  --accent-soft: #263b50;
  --warning: #ffd18a;
  --warning-bg: #3c2d1b;
  --email: #f0b66e;
  --card: #ff9cad;
  --phone: #80c9f0;
  --dob: #c0a1f4;
  --address: #91d6a8;
}
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; background: var(--bg); color: var(--text); font: 15px/1.55 var(--font); }
button, textarea { font: inherit; }
button { cursor: pointer; }
button:focus-visible, textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
button:disabled { cursor: not-allowed; opacity: .48; }
.topbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 15px max(20px, calc((100% - 1180px) / 2)); background: var(--panel); border-bottom: 1px solid var(--line); }
.brand { min-width: 0; }
.brand h1 { margin: 0; font-size: 1.1rem; font-weight: 700; }
.brand p { margin: 2px 0 0; color: var(--muted); font-size: .86rem; }
.top-actions { display: flex; align-items: center; gap: 8px; }
.button { min-height: 40px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 7px; background: var(--panel); color: var(--text); font-size: .9rem; }
.button:hover:not(:disabled) { border-color: var(--accent); }
.button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
html[data-theme="dark"] .button.primary { color: #171b20; }
main { width: min(1180px, calc(100% - 40px)); margin: 24px auto 40px; }
.filters { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 10px; }
.filters-title { margin-right: 4px; color: var(--muted); font-size: .9rem; }
.filter { display: inline-flex; align-items: center; gap: 7px; min-height: 40px; padding: 6px 10px; border: 1px solid var(--line); border-radius: 7px; background: var(--panel); color: var(--text); font-size: .88rem; }
.filter[aria-pressed="false"] { color: var(--muted); background: transparent; border-style: dashed; }
.filter .dot { width: 8px; height: 8px; flex: none; border-radius: 50%; background: var(--kind-color); }
.filter .count { color: var(--muted); font: .8rem var(--mono); }
[data-k="email"] { --kind-color: var(--email); }
[data-k="card"] { --kind-color: var(--card); }
[data-k="phone"] { --kind-color: var(--phone); }
[data-k="dob"] { --kind-color: var(--dob); }
[data-k="address"] { --kind-color: var(--address); }
#allBtn { color: var(--accent); }
.filter-warning { margin: 0 0 14px; padding: 10px 12px; border: 1px solid color-mix(in srgb, var(--warning) 35%, var(--line)); border-radius: 7px; background: var(--warning-bg); color: var(--warning); font-size: .88rem; }
.filter-warning[hidden] { display: none; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.panel { min-width: 0; overflow: hidden; border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel); }
.panel-head, .panel-foot { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 12px 14px; }
.panel-head { border-bottom: 1px solid var(--line); font-weight: 650; }
.panel-foot { border-top: 1px solid var(--line); }
.meta { margin-left: auto; color: var(--muted); font-size: .82rem; font-weight: 400; }
.status { display: inline-flex; align-items: center; gap: 7px; color: var(--muted); font-size: .82rem; font-weight: 400; }
.status::before { width: 7px; height: 7px; flex: none; border-radius: 50%; background: #479467; content: ""; }
#outPanel.busy .status { color: var(--accent); }
#outPanel.busy .status::before { background: var(--accent); animation: pulse .9s ease-in-out infinite alternate; }
@keyframes pulse { to { opacity: .3; } }
.editor { position: relative; height: 390px; overflow: hidden; }
textarea, .backdrop { width: 100%; margin: 0; padding: 15px 16px; border: 0; font: 13.5px/1.75 var(--mono); letter-spacing: normal; tab-size: 4; white-space: pre-wrap; overflow-wrap: anywhere; }
textarea { position: absolute; inset: 0; height: 100%; z-index: 1; resize: none; overflow: auto; background: transparent; color: var(--text); caret-color: var(--accent); scrollbar-gutter: stable; }
textarea::placeholder { color: var(--muted); opacity: 1; }
.backdrop { position: absolute; top: 0; left: 0; padding-right: calc(16px + var(--sbw, 0px)); color: transparent; pointer-events: none; }
.backdrop mark, .tx mark { border-radius: 3px; background: color-mix(in srgb, var(--kind-color) 20%, transparent); box-shadow: inset 0 -2px 0 var(--kind-color); }
.backdrop mark.unmasked, .tx mark.unmasked { background: color-mix(in srgb, #f59e0b 20%, transparent); box-shadow: inset 0 -2px 0 #d97706; }
.output { height: 390px; overflow: auto; padding: 12px 0; font: 13.5px/1.75 var(--mono); }
.line { display: flex; padding-right: 14px; }
.line-number { width: 42px; flex: none; padding-right: 12px; color: var(--muted); text-align: right; user-select: none; font-size: .82em; }
.line.hit { background: color-mix(in srgb, var(--accent) 7%, transparent); }
.line.hit .line-number { color: var(--accent); }
.tx { flex: 1; min-width: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.tx:empty::after { content: "\200b"; }
.tx mark { color: inherit; padding: 1px 3px; }
.tx mark.unmasked { text-decoration: underline; text-decoration-style: wavy; text-decoration-color: #d97706; text-underline-offset: 3px; }
html[data-mode="plain"] .tx mark:not(.unmasked) { background: transparent; box-shadow: none; padding: 0; }
html[data-mode="redact"] .tx mark:not(.unmasked) { background: #252a31; box-shadow: none; color: transparent; }
html[data-mode="redact"] .tx mark:not(.unmasked):hover { color: #fff; }
.empty { display: grid; min-height: 100%; place-content: center; gap: 5px; padding: 20px; text-align: center; }
.empty strong { font-weight: 600; }
.empty span { color: var(--muted); font-size: .88rem; }
.mode-switch { display: inline-flex; gap: 3px; padding: 3px; border: 1px solid var(--line); border-radius: 7px; }
.mode-switch button { min-height: 32px; padding: 5px 9px; border: 0; border-radius: 5px; background: transparent; color: var(--muted); font-size: .82rem; }
.mode-switch button.active { background: var(--accent-soft); color: var(--text); }
.mode-switch button:focus-visible { outline: 2px solid var(--accent); }
.hint { margin-left: auto; color: var(--muted); font-size: .82rem; }
.summary { display: flex; align-items: center; gap: 12px; margin-top: 15px; padding: 14px 16px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel); }
.summary-number { min-width: 38px; font: 700 1.5rem/1 var(--mono); color: var(--accent); }
.summary-text { font-size: .92rem; }
.summary-text small { display: block; margin-top: 2px; color: var(--muted); font-size: .82rem; }
.privacy-note { margin: 10px 2px 0; color: var(--muted); font-size: .83rem; }
.toast { position: fixed; bottom: 20px; left: 50%; z-index: 5; max-width: calc(100% - 32px); padding: 9px 14px; border-radius: 7px; background: var(--text); color: var(--bg); opacity: 0; pointer-events: none; transform: translate(-50%, 8px); transition: opacity .15s, transform .15s; font-size: .9rem; }
.toast.show { opacity: 1; transform: translate(-50%, 0); }
.panel.drag { outline: 2px dashed var(--accent); outline-offset: -5px; }
.file-input { display: none; }
@media (max-width: 800px) { .grid { grid-template-columns: 1fr; } .editor, .output { height: 320px; } }
@media (max-width: 520px) {
  .topbar { align-items: flex-start; padding: 13px 16px; }
  .brand p { max-width: 220px; }
  main { width: calc(100% - 24px); margin-top: 16px; }
  .panel-head, .panel-foot { padding: 10px; }
  .hint { width: 100%; margin-left: 0; }
  .summary { align-items: flex-start; }
  .meta { font-size: .78rem; }
}
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
</style>
</head>
<body>
<header class="topbar">
  <div class="brand">
    <h1>PDPA Data Masking</h1>
    <p>ค้นหาและปกปิดข้อมูลส่วนบุคคลในข้อความ</p>
  </div>
  <div class="top-actions">
    <button class="button" id="themeBtn" type="button" aria-pressed="false">โหมดมืด</button>
  </div>
</header>
<main>
  <div class="filters" id="filters"><span class="filters-title">ประเภทข้อมูลที่ต้องการปกปิด</span></div>
  <p class="filter-warning" id="filterWarning" role="alert" hidden></p>
  <div class="grid">
    <section class="panel" id="inPanel">
      <div class="panel-head"><span>ข้อความต้นฉบับ</span><span class="meta" id="inMeta">0 ตัวอักษร</span></div>
      <div class="editor">
        <div class="backdrop" id="backdrop" aria-hidden="true"></div>
        <textarea id="input" spellcheck="false" autofocus aria-label="ข้อความต้นฉบับ" placeholder="พิมพ์หรือวางข้อความที่นี่…&#10;&#10;ตัวอย่าง:&#10;โทร 081-234-5678&#10;อีเมล somchai@example.com&#10;บัตรเครดิต 4111 1111 1111 1111"></textarea>
      </div>
      <div class="panel-foot">
        <button class="button" id="clearBtn" type="button">ล้างข้อความ</button>
        <button class="button" id="exampleBtn" type="button">ใส่ตัวอย่าง</button>
        <button class="button" id="fileBtn" type="button">เลือกไฟล์ .txt/.log</button>
        <input class="file-input" id="fileInput" type="file" accept=".txt,.log,text/plain" tabindex="-1" aria-label="เลือกไฟล์ข้อความ">
        <button class="button" id="hlBtn" type="button" aria-pressed="true">ไฮไลต์ข้อมูลที่พบ</button>
        <span class="hint">ลากไฟล์มาวางได้ · Ctrl+Enter ตรวจทันที</span>
      </div>
    </section>
    <section class="panel" id="outPanel">
      <div class="panel-head"><span>ผลลัพธ์</span><span class="status" id="statusText" role="status" aria-live="polite">รอรับข้อความ</span><span class="meta" id="outMeta">0 รายการ</span></div>
      <div class="output" id="output"></div>
      <div class="panel-foot">
        <div class="mode-switch" id="modeSeg" role="group" aria-label="รูปแบบการแสดงผล">
          <button type="button" data-mode="highlight" class="active" aria-pressed="true">ไฮไลต์</button>
          <button type="button" data-mode="redact" aria-pressed="false">แถบดำ</button>
          <button type="button" data-mode="plain" aria-pressed="false">ปกติ</button>
        </div>
        <button class="button primary" id="copyBtn" type="button" disabled>คัดลอกผลลัพธ์</button>
        <button class="button" id="saveBtn" type="button" disabled>ดาวน์โหลด</button>
      </div>
    </section>
  </div>
  <section class="summary">
    <div class="summary-number" id="totalNum">0</div>
    <div class="summary-text"><span id="summaryText">พิมพ์หรือวางข้อความเพื่อเริ่มตรวจสอบ</span><small id="summaryDetail">จำนวนข้อมูลที่ตรวจพบในทุกประเภท</small></div>
  </section>
  <p class="privacy-note">การตรวจจับอาศัยรูปแบบข้อมูลที่กำหนดไว้ จึงอาจพลาดข้อมูลส่วนบุคคลบางรูปแบบ ควรตรวจผลลัพธ์ก่อนนำไปเผยแพร่</p>
</main>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>
const KINDS = ["email", "card", "phone", "dob", "address"];
const LABELS = { email: "อีเมล", card: "บัตรเครดิต", phone: "เบอร์โทรศัพท์", dob: "วันเกิด", address: "ที่อยู่" };
const ZERO = { email: 0, card: 0, phone: 0, dob: 0, address: 0 };
const MAX_BODY_BYTES = 2000000;
const root = document.documentElement;
const input = document.getElementById("input");
const backdrop = document.getElementById("backdrop");
const editor = document.querySelector(".editor");
const output = document.getElementById("output");
const inPanel = document.getElementById("inPanel");
const outPanel = document.getElementById("outPanel");
const inMeta = document.getElementById("inMeta");
const outMeta = document.getElementById("outMeta");
const statusText = document.getElementById("statusText");
const summaryText = document.getElementById("summaryText");
const summaryDetail = document.getElementById("summaryDetail");
const totalNum = document.getElementById("totalNum");
const toastEl = document.getElementById("toast");
const filtersBox = document.getElementById("filters");
const filterWarning = document.getElementById("filterWarning");
const hlBtn = document.getElementById("hlBtn");
const themeBtn = document.getElementById("themeBtn");
const copyBtn = document.getElementById("copyBtn");
const saveBtn = document.getElementById("saveBtn");
const fileInput = document.getElementById("fileInput");

let enabled = new Set(KINDS);
let showBackdrop = read("backdrop") !== "off";
let timer = null;
let sequence = 0;
let controller = null;
let plain = "";
let toastTimer = null;
let lastData = null;
let lastText = "";
let resultReady = false;

function save(key, value) {
  try { localStorage.setItem(key, value); } catch (_) {}
}

function read(key) {
  try { return localStorage.getItem(key); } catch (_) { return null; }
}

try {
  const savedKinds = JSON.parse(read("kinds") || "null");
  if (Array.isArray(savedKinds)) {
    const validKinds = savedKinds.filter(kind => KINDS.includes(kind));
    if (validKinds.length) enabled = new Set(validKinds);
  }
} catch (_) {}

function el(tag, className) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  return node;
}

function toast(message) {
  toastEl.textContent = message;
  toastEl.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove("show"), 2000);
}

function applyTheme(theme) {
  const value = theme === "dark" ? "dark" : "light";
  root.dataset.theme = value;
  themeBtn.textContent = value === "dark" ? "โหมดสว่าง" : "โหมดมืด";
  themeBtn.setAttribute("aria-pressed", String(value === "dark"));
  save("theme", value);
}

function applyMode(mode) {
  const value = ["highlight", "redact", "plain"].includes(mode) ? mode : "highlight";
  root.dataset.mode = value;
  document.querySelectorAll("#modeSeg button").forEach(button => {
    const active = button.dataset.mode === value;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  save("mode", value);
}

function syncScrollbarWidth() {
  const width = input.offsetWidth - input.clientWidth;
  editor.style.setProperty("--sbw", Math.max(0, width) + "px");
}

function syncScroll() {
  backdrop.style.transform = "translateY(" + (-input.scrollTop) + "px)";
}

window.addEventListener("resize", () => {
  syncScrollbarWidth();
  syncScroll();
});
input.addEventListener("scroll", syncScroll);

const filterButtons = {};
const countElements = {};

KINDS.forEach(kind => {
  const button = el("button", "filter");
  button.type = "button";
  button.dataset.k = kind;
  button.setAttribute("aria-pressed", "true");
  const dot = el("span", "dot");
  const label = el("span");
  label.textContent = LABELS[kind];
  const count = el("span", "count");
  count.textContent = "0";
  button.append(dot, label, count);
  button.addEventListener("click", () => {
    if (enabled.has(kind)) enabled.delete(kind);
    else enabled.add(kind);
    save("kinds", JSON.stringify([...enabled]));
    syncFilters();
    refresh();
  });
  filtersBox.appendChild(button);
  filterButtons[kind] = button;
  countElements[kind] = count;
});

const allButton = el("button", "filter");
allButton.type = "button";
allButton.id = "allBtn";
allButton.textContent = "เลือกทั้งหมด";
allButton.addEventListener("click", () => {
  enabled = new Set(KINDS);
  save("kinds", JSON.stringify([...enabled]));
  syncFilters();
  refresh();
});
filtersBox.appendChild(allButton);

function syncFilters() {
  KINDS.forEach(kind => {
    filterButtons[kind].setAttribute("aria-pressed", String(enabled.has(kind)));
  });
  updateFilterWarning(lastData && lastText === input.value ? lastData.stats : null);
}

function updateFilterWarning(stats) {
  const disabledKinds = KINDS.filter(kind => !enabled.has(kind));
  if (!disabledKinds.length) {
    filterWarning.hidden = true;
    filterWarning.textContent = "";
    return;
  }
  const exposed = disabledKinds
    .map(kind => ({ kind, count: stats ? Number(stats[kind] || 0) : 0 }))
    .filter(item => item.count > 0);
  if (exposed.length) {
    const details = exposed.map(item => LABELS[item.kind] + " " + item.count + " รายการ").join(", ");
    filterWarning.textContent = "พบข้อมูลที่ยังไม่ปกปิด: " + details + ". ข้อมูลเหล่านี้จะคงข้อความเดิมไว้ในผลลัพธ์และไฟล์ส่งออก";
  } else {
    filterWarning.textContent = "หมวดที่ไม่ได้เลือกจะไม่ถูกปกปิด หากพบข้อมูลในหมวดนั้น ข้อความเดิมจะอยู่ในผลลัพธ์และไฟล์ส่งออก";
  }
  filterWarning.hidden = false;
}

function applyFilters(segments) {
  const filteredSegments = [];
  const stats = { ...ZERO };
  const unmaskedStats = { ...ZERO };
  let masked = "";
  let unmaskedTotal = 0;

  for (const segment of segments) {
    if (segment.kind && !enabled.has(segment.kind)) {
      filteredSegments.push({ text: segment.orig, kind: null, unmaskedKind: segment.kind });
      masked += segment.orig;
      unmaskedStats[segment.kind]++;
      unmaskedTotal++;
      continue;
    }
    filteredSegments.push(segment);
    masked += segment.text;
    if (segment.kind) stats[segment.kind]++;
  }
  return { segments: filteredSegments, stats, unmaskedStats, unmaskedTotal, masked };
}

function paintBackdrop(segments) {
  const fragment = document.createDocumentFragment();
  if (segments && showBackdrop) {
    segments.forEach(segment => {
      if (segment.kind || segment.unmaskedKind) {
        const mark = el("mark", segment.unmaskedKind ? "unmasked" : "");
        mark.dataset.k = segment.unmaskedKind || segment.kind;
        mark.textContent = segment.orig;
        fragment.appendChild(mark);
      } else {
        fragment.appendChild(document.createTextNode(segment.text));
      }
    });
  } else {
    fragment.appendChild(document.createTextNode(input.value));
  }
  fragment.appendChild(document.createTextNode("\u200b"));
  backdrop.replaceChildren(fragment);
  syncScroll();
}

function emptyState(title, description) {
  const box = el("div", "empty");
  const heading = el("strong");
  heading.textContent = title || "ผลลัพธ์จะแสดงที่นี่";
  const detail = el("span");
  detail.textContent = description || "เริ่มพิมพ์ข้อความทางด้านซ้าย";
  box.append(heading, detail);
  return box;
}

function paintOutputMessage(title, description) {
  output.replaceChildren(emptyState(title, description));
}

function paintOutput(segments) {
  if (!segments.length) {
    output.replaceChildren(emptyState());
    return { lines: 0, hits: 0 };
  }

  const lines = [];
  const makeLine = () => {
    const row = el("div", "line");
    const number = el("span", "line-number");
    number.textContent = String(lines.length + 1);
    const text = el("span", "tx");
    row.append(number, text);
    const line = { row, text, hit: false };
    lines.push(line);
    return line;
  };

  let current = makeLine();
  segments.forEach(segment => {
    const parts = segment.text.split("\n");
    parts.forEach((part, index) => {
      if (index > 0) current = makeLine();
      if (!part) return;
      if (segment.kind || segment.unmaskedKind) {
        const unmasked = Boolean(segment.unmaskedKind);
        const mark = el("mark", unmasked ? "unmasked" : "");
        mark.dataset.k = segment.unmaskedKind || segment.kind;
        if (unmasked) mark.title = "ข้อมูลนี้ไม่ได้ถูกปกปิด";
        mark.textContent = part;
        current.text.appendChild(mark);
        current.hit = true;
      } else {
        current.text.appendChild(document.createTextNode(part));
      }
    });
  });

  const fragment = document.createDocumentFragment();
  let hits = 0;
  lines.forEach(line => {
    if (line.hit) {
      line.row.classList.add("hit");
      hits++;
    }
    fragment.appendChild(line.row);
  });
  output.replaceChildren(fragment);
  return { lines: lines.length, hits };
}

function updateCounts(stats) {
  KINDS.forEach(kind => {
    countElements[kind].textContent = String(stats[kind] || 0);
  });
}

function paintSummary(filteredStats, info, hasText, allStats, unmaskedTotal) {
  const detected = KINDS.reduce((sum, kind) => sum + Number((allStats || ZERO)[kind] || 0), 0);
  const masked = KINDS.reduce((sum, kind) => sum + Number(filteredStats[kind] || 0), 0);
  totalNum.textContent = String(detected);
  outMeta.textContent = hasText ? "ปกปิด " + masked + " / พบ " + detected : "0 รายการ";
  updateCounts(allStats || ZERO);

  if (!hasText) {
    summaryText.textContent = "พิมพ์หรือวางข้อความเพื่อเริ่มตรวจสอบ";
    summaryDetail.textContent = "จำนวนข้อมูลที่ตรวจพบในทุกประเภท";
  } else if (detected) {
    summaryText.textContent = "พบข้อมูล " + detected + " รายการ · ปกปิดแล้ว " + masked + " รายการ";
    summaryDetail.textContent = unmaskedTotal ? "ยังมีข้อมูล " + unmaskedTotal + " รายการที่ไม่ได้ปกปิด" : "ตรวจสอบผลลัพธ์ก่อนนำไปเผยแพร่";
  } else {
    summaryText.textContent = "ไม่พบข้อมูลส่วนบุคคลตามรูปแบบที่รองรับ";
    summaryDetail.textContent = "รูปแบบข้อมูลอื่นอาจไม่ถูกตรวจพบ";
  }
}

function setActionsEnabled(enabledState) {
  copyBtn.disabled = !enabledState;
  saveBtn.disabled = !enabledState;
}

function render(data) {
  const filtered = applyFilters(data.segments);
  plain = filtered.masked;
  resultReady = true;
  paintBackdrop(filtered.segments);
  const info = paintOutput(filtered.segments);
  paintSummary(filtered.stats, info, true, data.stats, filtered.unmaskedTotal);
  statusText.textContent = "ตรวจสอบเสร็จแล้ว";
  setActionsEnabled(Boolean(input.value));
  updateFilterWarning(data.stats);
}

function resetResultForPending() {
  lastData = null;
  lastText = "";
  plain = "";
  resultReady = false;
  setActionsEnabled(false);
  paintBackdrop(null);
  updateCounts(ZERO);
  totalNum.textContent = "0";
  outMeta.textContent = "รอตรวจสอบ";
  summaryText.textContent = "กำลังตรวจสอบข้อความล่าสุด…";
  summaryDetail.textContent = "ผลลัพธ์จะพร้อมเมื่อการตรวจสอบเสร็จสิ้น";
  statusText.textContent = "รอตรวจสอบ…";
  paintOutputMessage("กำลังตรวจสอบข้อความ", "ผลลัพธ์ก่อนหน้าถูกนำออกเพื่อป้องกันการคัดลอกข้อมูลเก่า");
  updateFilterWarning(null);
}

function showError(message, description) {
  lastData = null;
  lastText = "";
  plain = "";
  resultReady = false;
  setActionsEnabled(false);
  statusText.textContent = "ตรวจสอบไม่สำเร็จ";
  outMeta.textContent = "ไม่มีผลลัพธ์";
  updateCounts(ZERO);
  totalNum.textContent = "0";
  summaryText.textContent = message;
  summaryDetail.textContent = description;
  paintOutputMessage(message, description);
  updateFilterWarning(null);
}

function refresh() {
  if (lastData && lastText === input.value) {
    render(lastData);
    return;
  }
  clearTimeout(timer);
  run();
}

async function run() {
  clearTimeout(timer);
  timer = null;
  const currentSequence = ++sequence;
  const text = input.value;
  inMeta.textContent = text.length.toLocaleString("th-TH") + " ตัวอักษร";

  if (controller) controller.abort();
  controller = null;

  if (!text) {
    lastData = null;
    lastText = "";
    plain = "";
    resultReady = false;
    setActionsEnabled(false);
    outPanel.classList.remove("busy");
    paintBackdrop(null);
    paintOutput([]);
    paintSummary(ZERO, { lines: 0, hits: 0 }, false, ZERO, 0);
    statusText.textContent = "รอรับข้อความ";
    updateFilterWarning(null);
    return;
  }

  const requestBody = JSON.stringify({ text });
  if (new TextEncoder().encode(requestBody).length > MAX_BODY_BYTES) {
    showError("ข้อความยาวเกินไป", "จำกัดขนาดคำขอไว้ที่ 2 MB");
    outPanel.classList.remove("busy");
    toast("ข้อความยาวเกินไป");
    return;
  }

  controller = new AbortController();
  outPanel.classList.add("busy");
  statusText.textContent = "กำลังตรวจสอบ…";
  try {
    const response = await fetch("/api/mask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: requestBody,
      signal: controller.signal
    });
    if (currentSequence !== sequence) return;
    if (response.status === 413) {
      showError("ข้อความยาวเกินไป", "ลดขนาดข้อความแล้วลองอีกครั้ง");
      return;
    }
    if (!response.ok) throw new Error(String(response.status));
    const data = await response.json();
    if (currentSequence !== sequence) return;
    lastData = data;
    lastText = text;
    render(data);
  } catch (error) {
    if (error.name !== "AbortError" && currentSequence === sequence) {
      showError("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้", "ตรวจสอบว่าเซิร์ฟเวอร์กำลังทำงาน แล้วกด Ctrl+Enter เพื่อลองใหม่");
      toast("ตรวจสอบข้อความไม่สำเร็จ");
    }
  } finally {
    if (currentSequence === sequence) outPanel.classList.remove("busy");
  }
}

function onInput() {
  clearTimeout(timer);
  if (controller) controller.abort();
  controller = null;
  sequence++;
  inMeta.textContent = input.value.length.toLocaleString("th-TH") + " ตัวอักษร";
  if (!input.value) {
    resetResultForPending();
    outPanel.classList.remove("busy");
    paintOutput([]);
    paintSummary(ZERO, { lines: 0, hits: 0 }, false, ZERO, 0);
    statusText.textContent = "รอรับข้อความ";
    updateFilterWarning(null);
    return;
  }
  resetResultForPending();
  outPanel.classList.add("busy");
  timer = setTimeout(run, 180);
}

input.addEventListener("input", onInput);
themeBtn.addEventListener("click", () => applyTheme(root.dataset.theme === "dark" ? "light" : "dark"));
document.getElementById("modeSeg").addEventListener("click", event => {
  const button = event.target.closest("button[data-mode]");
  if (button) applyMode(button.dataset.mode);
});
document.getElementById("clearBtn").addEventListener("click", () => {
  input.value = "";
  input.scrollTop = 0;
  onInput();
  input.focus();
});
document.getElementById("exampleBtn").addEventListener("click", () => {
  input.value = "ชื่อ: สมชาย ตัวอย่าง\nโทร: 081-234-5678\nอีเมล: somchai@example.com\nวันเกิด: 12/05/1998\nบัตรเครดิต: 4111 1111 1111 1111\nที่อยู่: 123/45 ถนนสุขุมวิท";
  input.scrollTop = 0;
  onInput();
  input.focus();
});

document.getElementById("fileBtn").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  const file = fileInput.files && fileInput.files[0];
  fileInput.value = "";
  loadFile(file);
});

function syncHighlightButton() {
  hlBtn.setAttribute("aria-pressed", String(showBackdrop));
}

hlBtn.addEventListener("click", () => {
  showBackdrop = !showBackdrop;
  save("backdrop", showBackdrop ? "on" : "off");
  syncHighlightButton();
  paintBackdrop(lastData && lastText === input.value ? applyFilters(lastData.segments).segments : null);
});

function getUnmaskedCount() {
  if (!lastData || lastText !== input.value) return 0;
  return KINDS.reduce((sum, kind) => sum + (enabled.has(kind) ? 0 : Number(lastData.stats[kind] || 0)), 0);
}

function confirmExport(action) {
  const count = getUnmaskedCount();
  if (!count) return true;
  return window.confirm("ยังมีข้อมูลส่วนบุคคล " + count + " รายการที่ไม่ได้ปกปิด การ" + action + "จะรวมข้อมูลเหล่านี้ในรูปแบบเดิม ต้องการดำเนินการต่อหรือไม่?");
}

async function copyResult() {
  if (!resultReady || lastText !== input.value) return;
  if (!confirmExport("คัดลอก")) return;
  try {
    await navigator.clipboard.writeText(plain);
    toast("คัดลอกผลลัพธ์แล้ว");
  } catch (_) {
    toast("คัดลอกไม่สำเร็จ โปรดอนุญาตให้เข้าถึงคลิปบอร์ด");
  }
}

copyBtn.addEventListener("click", copyResult);
saveBtn.addEventListener("click", () => {
  if (!resultReady || lastText !== input.value) return;
  if (!confirmExport("ดาวน์โหลด")) return;
  const blob = new Blob([plain], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = el("a");
  link.href = url;
  link.download = "masked.txt";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("ดาวน์โหลดแล้ว");
});

document.addEventListener("keydown", event => {
  if (!(event.ctrlKey || event.metaKey)) return;
  if (event.key === "Enter") {
    event.preventDefault();
    run();
  } else if (event.shiftKey && event.key.toLowerCase() === "c") {
    event.preventDefault();
    copyResult();
  }
});

function loadFile(file) {
  if (!file) return;
  if (file.size > 900000) {
    toast("ไฟล์ใหญ่เกินไป ขนาดสูงสุด 900 KB");
    return;
  }
  if (!/\.(txt|log)$/i.test(file.name) && file.type !== "text/plain") {
    toast("โปรดเลือกไฟล์ .txt หรือ .log");
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    input.value = String(reader.result || "");
    input.scrollTop = 0;
    onInput();
  };
  reader.onerror = () => toast("อ่านไฟล์ไม่สำเร็จ");
  reader.readAsText(file);
}

["dragenter", "dragover"].forEach(type => {
  inPanel.addEventListener(type, event => {
    event.preventDefault();
    inPanel.classList.add("drag");
  });
});
["dragleave", "drop"].forEach(type => {
  inPanel.addEventListener(type, event => {
    event.preventDefault();
    inPanel.classList.remove("drag");
  });
});
inPanel.addEventListener("drop", event => {
  const file = event.dataTransfer.files[0];
  loadFile(file);
});
window.addEventListener("dragover", event => event.preventDefault());
window.addEventListener("drop", event => event.preventDefault());

applyTheme(read("theme") || "light");
applyMode(read("mode") || "highlight");
syncFilters();
syncHighlightButton();
syncScrollbarWidth();
paintOutput([]);
setActionsEnabled(false);
run();
window.addEventListener("load", syncScrollbarWidth);
</script>
</body>
</html>"""



class Handler(BaseHTTPRequestHandler):
    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HTML_PAGE.encode("utf-8"))
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/mask":
            self._json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json(400, {"error": "bad length"})
            return

        if length < 0 or length > MAX_BODY_BYTES:
            self._json(413, {"error": "payload too large"})
            return

        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            text = str(payload.get("text", ""))
        except (ValueError, AttributeError):
            self._json(400, {"error": "invalid json"})
            return

        masked, segments, stats = mask_text(text)
        self._json(200, {"masked": masked, "segments": segments, "stats": stats})

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(os.environ.get("PORT", "8000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
