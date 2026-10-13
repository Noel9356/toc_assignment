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
    r"(?P<dayA>\d{1,2})(?P<sepA>[/.\-])(?P<monthA>\d{1,2})(?P=sepA)(?P<yearA>\d{4})"
    r"|(?P<yearB>\d{4})(?P<sepB>[/.\-])(?P<monthB>\d{1,2})(?P=sepB)(?P<dayB>\d{1,2})"
    r")(?!\d))"
)

ADDRESS = (
    r"(?P<address>(?P<addrLabel>(?<![A-Za-z0-9])(?:Address|ที่อยู่)"
    + QUOTE + r"\s*[:=]\s*" + QUOTE
    + r"(?:(?:บ้านเลขที่|เลขที่|No\.?)\s*)?)"
    r"(?P<addrNo>\d+(?:[/\-]\d+)*))"
)

PATTERN = re.compile("|".join([EMAIL, CARD, PHONE, DOB, ADDRESS]), re.IGNORECASE)


def hide_digits(s, keep=4):
    return re.sub(r"\d", "X", s[:-keep]) + s[-keep:]


def mask_email(m):
    user = m.group("emailUser")
    n = len(user)
    if n == 1:
        head = "*"
    elif n == 2:
        head = user[0] + "*"
    else:
        head = user[0] + "*" * (n - 2) + user[-1]
    return head + "@" + m.group("emailDomain")


def mask_card(m):
    return hide_digits(m.group("card"))


def mask_phone(m):
    return hide_digits(m.group("phone"))


def mask_dob(m):
    if m.group("yearA") is not None:
        sep, year = m.group("sepA"), m.group("yearA")
        date = "XX" + sep + "XX" + sep + year[:2] + "XX"
    else:
        sep, year = m.group("sepB"), m.group("yearB")
        date = year[:2] + "XX" + sep + "XX" + sep + "XX"
    return m.group("dobLabel") + date


def mask_address(m):
    return m.group("addrLabel") + re.sub(r"\d", "X", m.group("addrNo"))


MASKERS = {
    "email": mask_email,
    "card": mask_card,
    "phone": mask_phone,
    "dob": mask_dob,
    "address": mask_address,
}


def mask_text(text):
    segments = []
    stats = {k: 0 for k in MASKERS}
    pos = 0
    for m in PATTERN.finditer(text):
        if m.start() > pos:
            segments.append({"text": text[pos:m.start()], "kind": None})
        kind = m.lastgroup
        segments.append({"text": MASKERS[kind](m), "orig": m.group(0), "kind": kind})
        stats[kind] += 1
        pos = m.end()
    if pos < len(text):
        segments.append({"text": text[pos:], "kind": None})
    masked = "".join(s["text"] for s in segments)
    return masked, segments, stats


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="th" data-theme="aurora" data-mode="highlight">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDPA Data Masking</title>
<style>
html[data-theme="aurora"] {
    --bg: #0b1020; --text: #e8ecff; --muted: #8e99c4; --panel: rgba(255, 255, 255, .06);
    --line: rgba(255, 255, 255, .14); --accent: #8b7bff; --accentText: #0b1020; --track: rgba(255, 255, 255, .1);
    --redact: #04060d; --redactText: #e8ecff; --radius: 20px; --shadow: 0 20px 60px rgba(0, 0, 0, .45);
    --blur: blur(18px);
    --font: "Sarabun", "Noto Sans Thai", system-ui, -apple-system, "Segoe UI", sans-serif;
    --mono: "JetBrains Mono", ui-monospace, Menlo, Consolas, "Noto Sans Thai", monospace;
    --cEmail: #ffa94d; --cCard: #ff6b9d; --cPhone: #4dc3ff; --cDob: #b197fc; --cAddress: #69db7c;
}
html[data-theme="terminal"] {
    --bg: #020a05; --text: #6dffa6; --muted: #2f9c5f; --panel: rgba(0, 20, 8, .85);
    --line: #1d7a47; --accent: #39ff88; --accentText: #020a05; --track: #06210f;
    --redact: #39ff88; --redactText: #020a05; --radius: 4px; --shadow: 0 0 28px rgba(57, 255, 136, .18);
    --blur: none;
    --font: ui-monospace, Menlo, Consolas, "Noto Sans Thai", monospace;
    --mono: ui-monospace, Menlo, Consolas, "Noto Sans Thai", monospace;
    --cEmail: #ffd43b; --cCard: #ff6b6b; --cPhone: #4dd2ff; --cDob: #da77f2; --cAddress: #b2ff8a;
}
html[data-theme="paper"] {
    --bg: #efe9db; --text: #1b1b1b; --muted: #7a7160; --panel: #fbf8f0;
    --line: #cfc6b0; --accent: #b3261e; --accentText: #ffffff; --track: #ddd4bf;
    --redact: #111111; --redactText: #fbf8f0; --radius: 3px; --shadow: 6px 6px 0 rgba(0, 0, 0, .12);
    --blur: none;
    --font: "Sarabun", "Noto Sans Thai", Georgia, serif;
    --mono: "Courier New", Courier, "Noto Sans Thai", monospace;
    --cEmail: #c2410c; --cCard: #be123c; --cPhone: #1d4ed8; --cDob: #6d28d9; --cAddress: #15803d;
}
* { box-sizing: border-box; }
body {
    margin: 0; background: var(--bg); color: var(--text); font-family: var(--font);
    line-height: 1.55; min-height: 100vh; transition: background .4s, color .4s;
}
.bg { position: fixed; inset: 0; z-index: -1; pointer-events: none; opacity: 0; transition: opacity .6s; }
html[data-theme="aurora"] .bg {
    opacity: 1;
    background:
        radial-gradient(40% 50% at 15% 20%, rgba(139, 123, 255, .38), transparent 60%),
        radial-gradient(35% 45% at 85% 15%, rgba(255, 107, 157, .3), transparent 60%),
        radial-gradient(45% 55% at 70% 90%, rgba(77, 195, 255, .3), transparent 60%);
    background-size: 140% 140%;
    animation: drift 18s ease-in-out infinite alternate;
}
@keyframes drift { to { background-position: 100% 100%; filter: hue-rotate(45deg); } }
html[data-theme="terminal"] body::after {
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 50;
    background: repeating-linear-gradient(0deg, rgba(0, 0, 0, .22) 0 1px, transparent 1px 3px);
}
html[data-theme="paper"] body {
    background-image: linear-gradient(rgba(0, 0, 0, .05) 1px, transparent 1px);
    background-size: 100% 28px;
}
main { max-width: 1240px; margin: 0 auto; padding: 24px 20px 56px; }
.topbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.group { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 12px; overflow: hidden; background: var(--panel); backdrop-filter: var(--blur); }
.seg button { border: 0; border-radius: 0; background: transparent; }
.seg button.active { background: var(--accent); color: var(--accentText); font-weight: 600; }
button {
    font: inherit; color: var(--text); cursor: pointer; padding: 8px 14px; border-radius: 12px;
    border: 1px solid var(--line); background: var(--panel); backdrop-filter: var(--blur); transition: .18s;
}
button:hover { border-color: var(--accent); transform: translateY(-1px); }
.themes { display: flex; gap: 8px; align-items: center; }
.swatch { width: 28px; height: 28px; padding: 0; border-radius: 50%; border-width: 2px; }
.swatch.active { outline: 2px solid var(--accent); outline-offset: 3px; }
.swatch[data-theme="aurora"] { background: linear-gradient(135deg, #8b7bff, #ff6b9d); }
.swatch[data-theme="terminal"] { background: #020a05; border-color: #39ff88; }
.swatch[data-theme="paper"] { background: #efe9db; border-color: #b3261e; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }
@media (max-width: 860px) { .grid { grid-template-columns: 1fr; } }
.panel {
    background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    box-shadow: var(--shadow); backdrop-filter: var(--blur); transition: .3s;
}
.panel.drag { outline: 2px dashed var(--accent); outline-offset: -8px; }
.panelHead {
    display: flex; align-items: center; gap: 10px; padding: 13px 18px;
    border-bottom: 1px solid var(--line); font-weight: 600;
}
.panelHead small { margin-left: auto; color: var(--muted); font-weight: 400; font-family: var(--mono); }
.led { width: 9px; height: 9px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 10px var(--accent); animation: pulse 2s infinite; }
html[data-theme="terminal"] .led { border-radius: 0; animation: blink 1s steps(2) infinite; }
@keyframes pulse { 50% { opacity: .35; } }
@keyframes blink { 50% { opacity: 0; } }
.editor { position: relative; }
textarea, .backdrop {
    font: 15px/1.75 var(--mono); padding: 16px 18px; margin: 0; border: 0; tab-size: 4;
    white-space: pre-wrap; overflow-wrap: break-word; word-break: normal; letter-spacing: normal;
}
textarea {
    position: relative; z-index: 1; display: block; width: 100%; min-height: 320px; resize: none; overflow: hidden;
    outline: 0; background: transparent; color: var(--text); caret-color: var(--accent);
}
textarea::placeholder { color: var(--muted); }
.backdrop { position: absolute; inset: 0; overflow: hidden; color: transparent; pointer-events: none; }
.backdrop mark {
    color: transparent; border-radius: 3px; padding: 0;
    background: color-mix(in srgb, var(--k) 26%, transparent); box-shadow: inset 0 -2px 0 var(--k);
}
.dropHint { padding: 10px 18px; border-top: 1px solid var(--line); color: var(--muted); font-size: .85rem; }
.output { padding: 12px 0; font: 15px/1.75 var(--mono); min-height: 320px; counter-reset: ln; }
.output .empty { display: block; padding: 4px 18px; color: var(--muted); }
.ln { display: flex; counter-increment: ln; padding-right: 18px; }
.ln::before {
    content: counter(ln); flex: none; width: 3.2em; padding-right: 14px; text-align: right;
    color: var(--muted); user-select: none; opacity: .7;
}
.ln.hit { background: color-mix(in srgb, var(--accent) 10%, transparent); box-shadow: inset 3px 0 0 var(--accent); }
.ln.hit::before { color: var(--accent); opacity: 1; }
.tx { flex: 1; min-width: 0; white-space: pre-wrap; overflow-wrap: break-word; }
.tx:empty::after { content: "\200b"; }
.output mark {
    position: relative; color: inherit; font-weight: 600; padding: 0 4px; border-radius: 5px; cursor: help;
    background: color-mix(in srgb, var(--k) 24%, transparent); box-shadow: inset 0 -2px 0 var(--k);
}
.output mark::after {
    content: attr(data-label); position: absolute; left: 50%; bottom: 100%; transform: translate(-50%, -4px);
    background: var(--text); color: var(--bg); font: 600 12px/1 var(--font); padding: 5px 9px; border-radius: 6px;
    white-space: nowrap; opacity: 0; pointer-events: none; transition: opacity .15s; z-index: 5;
}
.output mark:hover::after { opacity: 1; }
html[data-mode="plain"] .output mark { background: none; box-shadow: none; padding: 0; font-weight: inherit; }
html[data-mode="redact"] .output mark { background: var(--redact); color: transparent; box-shadow: none; border-radius: 3px; }
html[data-mode="redact"] .output mark:hover { color: var(--redactText); }
mark[data-k="email"] { --k: var(--cEmail); }
mark[data-k="card"] { --k: var(--cCard); }
mark[data-k="phone"] { --k: var(--cPhone); }
mark[data-k="dob"] { --k: var(--cDob); }
mark[data-k="address"] { --k: var(--cAddress); }
.meter { margin-top: 18px; padding: 16px 18px 18px; }
.summary { font-weight: 600; margin-bottom: 12px; }
.bar { display: flex; height: 12px; border-radius: 999px; overflow: hidden; background: var(--track); }
.bar i { display: block; height: 100%; width: 0; background: var(--k); transition: width .45s cubic-bezier(.2, .8, .2, 1); }
.bar i[data-k="email"] { --k: var(--cEmail); }
.bar i[data-k="card"] { --k: var(--cCard); }
.bar i[data-k="phone"] { --k: var(--cPhone); }
.bar i[data-k="dob"] { --k: var(--cDob); }
.bar i[data-k="address"] { --k: var(--cAddress); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.chip {
    display: inline-flex; align-items: center; gap: 8px; padding: 6px 13px; border: 1px solid var(--line);
    border-radius: 999px; font-size: .9rem; transition: opacity .3s;
}
.chip.off { opacity: .45; }
.chip .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--k); }
.chip b { font-family: var(--mono); }
.chip[data-k="email"] { --k: var(--cEmail); }
.chip[data-k="card"] { --k: var(--cCard); }
.chip[data-k="phone"] { --k: var(--cPhone); }
.chip[data-k="dob"] { --k: var(--cDob); }
.chip[data-k="address"] { --k: var(--cAddress); }
.toast {
    position: fixed; left: 50%; bottom: 28px; transform: translate(-50%, 20px); opacity: 0; pointer-events: none;
    background: var(--text); color: var(--bg); padding: 9px 18px; border-radius: 999px; font-weight: 600;
    transition: .3s; z-index: 60;
}
.toast.show { opacity: 1; transform: translate(-50%, 0); }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
</style>
</head>
<body>
<div class="bg"></div>
<main>
    <div class="topbar">
        <div class="group">
            <div class="seg" id="modeSeg" role="group" aria-label="โหมดแสดงผล">
                <button data-mode="highlight" class="active">ไฮไลต์</button>
                <button data-mode="redact">แถบดำ</button>
                <button data-mode="plain">ปกติ</button>
            </div>
            <div class="themes" id="themes" role="group" aria-label="ธีม">
                <button class="swatch" data-theme="aurora" aria-label="Aurora" title="Aurora"></button>
                <button class="swatch" data-theme="terminal" aria-label="Terminal" title="Terminal"></button>
                <button class="swatch" data-theme="paper" aria-label="Paper" title="Paper"></button>
            </div>
        </div>
        <div class="group">
            <button id="copyBtn">📋 คัดลอกผลลัพธ์</button>
            <button id="saveBtn">⬇️ ดาวน์โหลด .txt</button>
        </div>
    </div>

    <div class="grid">
        <section class="panel" id="inPanel">
            <div class="panelHead"><span class="led"></span><span>Input: ข้อความต้นฉบับ</span><small id="inCount">0 ตัวอักษร</small></div>
            <div class="editor">
                <div class="backdrop" id="backdrop" aria-hidden="true"></div>
                <textarea id="input" spellcheck="false" aria-label="ข้อความต้นฉบับ" placeholder="พิมพ์หรือวางข้อความที่นี่ เช่น&#10;Card 1234-5678-9012-3456 tel 093-245-7894 somchai.d@company.com"></textarea>
            </div>
            <div class="dropHint">วางไฟล์ .txt หรือ .log ลงในช่องนี้ได้</div>
        </section>
        <section class="panel">
            <div class="panelHead"><span class="led"></span><span>Output: ข้อความที่เซ็นเซอร์แล้ว</span><small id="outCount">0 รายการ</small></div>
            <div class="output" id="output"></div>
        </section>
    </div>

    <section class="panel meter">
        <div class="summary" id="summary"></div>
        <div class="bar" id="bar"></div>
        <div class="chips" id="chips"></div>
    </section>
</main>
<div class="toast" id="toast"></div>

<script>
const KINDS = ["email", "card", "phone", "dob", "address"];
const LABELS = { email: "อีเมล", card: "บัตรเครดิต", phone: "เบอร์โทร", dob: "วันเกิด", address: "ที่อยู่" };
const root = document.documentElement;
const input = document.getElementById("input");
const backdrop = document.getElementById("backdrop");
const output = document.getElementById("output");
const inPanel = document.getElementById("inPanel");
const toastEl = document.getElementById("toast");
let timer = null, seq = 0, ctrl = null, plain = "", toastT = null;

function save(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
function read(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

function el(tag, cls) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    return node;
}

function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    clearTimeout(toastT);
    toastT = setTimeout(() => toastEl.classList.remove("show"), 1600);
}

function applyTheme(name) {
    root.dataset.theme = name;
    document.querySelectorAll("#themes button").forEach(b => b.classList.toggle("active", b.dataset.theme === name));
    save("theme", name);
}

function applyMode(name) {
    root.dataset.mode = name;
    document.querySelectorAll("#modeSeg button").forEach(b => b.classList.toggle("active", b.dataset.mode === name));
    save("mode", name);
}

function fit() {
    input.style.height = "auto";
    input.style.height = Math.max(input.scrollHeight, 320) + "px";
}

const bars = {}, chips = {}, counts = {};
(function buildMeter() {
    const bar = document.getElementById("bar");
    const chipBox = document.getElementById("chips");
    for (const k of KINDS) {
        const seg = el("i"); seg.dataset.k = k; bar.appendChild(seg); bars[k] = seg;
        const chip = el("span", "chip off"); chip.dataset.k = k;
        const dot = el("span", "dot");
        const count = el("b"); count.textContent = "0";
        chip.append(dot, document.createTextNode(LABELS[k]), count);
        chipBox.appendChild(chip); chips[k] = chip; counts[k] = count;
    }
})();

function paintBackdrop(segments) {
    const frag = document.createDocumentFragment();
    if (segments) {
        for (const s of segments) {
            if (s.kind) {
                const m = el("mark"); m.dataset.k = s.kind; m.textContent = s.orig;
                frag.appendChild(m);
            } else {
                frag.appendChild(document.createTextNode(s.text));
            }
        }
    } else {
        frag.appendChild(document.createTextNode(input.value));
    }
    frag.appendChild(document.createTextNode("\u200b"));
    backdrop.replaceChildren(frag);
}

function paintOutput(segments) {
    if (!segments.length) {
        const empty = el("span", "empty");
        empty.textContent = "ผลลัพธ์จะแสดงที่นี่...";
        output.replaceChildren(empty);
        return { lines: 0, hits: 0 };
    }
    const lines = [];
    function newLine() {
        const row = el("div", "ln");
        const tx = el("span", "tx");
        row.appendChild(tx);
        lines.push({ row, tx, hit: false });
        return lines[lines.length - 1];
    }
    let cur = newLine();
    for (const s of segments) {
        const parts = s.text.split("\n");
        parts.forEach((part, i) => {
            if (i > 0) cur = newLine();
            if (!part) return;
            if (s.kind) {
                const m = el("mark"); m.dataset.k = s.kind; m.dataset.label = LABELS[s.kind]; m.textContent = part;
                cur.tx.appendChild(m); cur.hit = true;
            } else {
                cur.tx.appendChild(document.createTextNode(part));
            }
        });
    }
    const frag = document.createDocumentFragment();
    let hits = 0;
    for (const l of lines) {
        if (l.hit) { l.row.classList.add("hit"); hits++; }
        frag.appendChild(l.row);
    }
    output.replaceChildren(frag);
    return { lines: lines.length, hits };
}

function paintMeter(stats, info, hasText) {
    let total = 0;
    for (const k of KINDS) total += stats[k];
    for (const k of KINDS) {
        bars[k].style.width = total ? (stats[k] / total * 100) + "%" : "0%";
        counts[k].textContent = stats[k];
        chips[k].classList.toggle("off", !stats[k]);
    }
    let msg = "พิมพ์หรือวางข้อความเพื่อเริ่มตรวจสอบ";
    if (hasText) {
        msg = total
            ? "ตรวจพบและเซ็นเซอร์ " + total + " รายการ ใน " + info.hits + " จาก " + info.lines + " บรรทัด"
            : "ยังไม่พบข้อมูลส่วนบุคคลในข้อความ";
    }
    document.getElementById("summary").textContent = msg;
    document.getElementById("outCount").textContent = total + " รายการ";
}

const zeroStats = { email: 0, card: 0, phone: 0, dob: 0, address: 0 };

async function run() {
    const mine = ++seq;
    const text = input.value;
    document.getElementById("inCount").textContent = text.length + " ตัวอักษร";
    if (ctrl) ctrl.abort();
    if (!text) {
        plain = "";
        paintBackdrop(null);
        paintMeter(zeroStats, paintOutput([]), false);
        return;
    }
    ctrl = new AbortController();
    try {
        const res = await fetch("/api/mask", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }), signal: ctrl.signal
        });
        if (res.status === 413) { toast("ข้อความยาวเกินไป"); return; }
        if (!res.ok) throw new Error(res.status);
        const data = await res.json();
        if (mine !== seq) return;
        plain = data.masked;
        paintBackdrop(data.segments);
        paintMeter(data.stats, paintOutput(data.segments), true);
    } catch (e) {
        if (e.name === "AbortError") return;
        toast("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้");
    }
}

function onInput() {
    paintBackdrop(null);
    fit();
    clearTimeout(timer);
    timer = setTimeout(run, 120);
}

input.addEventListener("input", onInput);
window.addEventListener("resize", fit);

document.getElementById("modeSeg").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b) applyMode(b.dataset.mode);
});
document.getElementById("themes").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b) applyTheme(b.dataset.theme);
});

document.getElementById("copyBtn").onclick = async () => {
    try {
        await navigator.clipboard.writeText(plain);
        toast("คัดลอกผลลัพธ์แล้ว");
    } catch (e) {
        toast("คัดลอกไม่สำเร็จ");
    }
};

document.getElementById("saveBtn").onclick = () => {
    const blob = new Blob([plain], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = el("a");
    a.href = url; a.download = "masked.txt";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast("ดาวน์โหลดแล้ว");
};

["dragenter", "dragover"].forEach(ev => inPanel.addEventListener(ev, (e) => { e.preventDefault(); inPanel.classList.add("drag"); }));
["dragleave", "drop"].forEach(ev => inPanel.addEventListener(ev, (e) => { e.preventDefault(); inPanel.classList.remove("drag"); }));
inPanel.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (!file) return;
    if (file.size > 900000) { toast("ไฟล์ใหญ่เกินไป (สูงสุด 900 KB)"); return; }
    const reader = new FileReader();
    reader.onload = () => { input.value = String(reader.result); onInput(); };
    reader.readAsText(file);
});
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

applyTheme(read("theme") || "aurora");
applyMode(read("mode") || "highlight");
fit();
run();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, ctype, body):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, "application/json; charset=utf-8", json.dumps(obj).encode("utf-8"))

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HTML_PAGE.encode("utf-8"))
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/mask":
            self._json(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json(400, {"error": "bad length"})
            return
        if n < 0 or n > MAX_BODY_BYTES:
            self._json(413, {"error": "payload too large"})
            return
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
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
