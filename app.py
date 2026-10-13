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
/* ============ THEME TOKENS ============ */
html[data-theme="aurora"]{
  --bg:#070a18; --text:#eef1ff; --muted:#a7b0dd;
  --panel:rgba(255,255,255,.06); --line:rgba(255,255,255,.16);
  --accent:#8b7bff; --accentText:#fff; --a1:#8b7bff; --a2:#ff6b9d;
  --track:rgba(255,255,255,.09); --redact:#04060d; --redactText:#e9edff;
  --radius:22px; --shadow:0 24px 60px -18px rgba(0,0,0,.75); --blur:blur(20px);
  --font:"Sarabun","Noto Sans Thai",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"JetBrains Mono",ui-monospace,Menlo,Consolas,"Noto Sans Thai",monospace;
  --cEmail:#ffb866; --cCard:#ff7fae; --cPhone:#5fcbff; --cDob:#bda6ff; --cAddress:#7ee38f;
}
html[data-theme="terminal"]{
  --bg:#020a05; --text:#8dffb8; --muted:#4bd68a;
  --panel:rgba(0,25,10,.75); --line:#2b9a5c;
  --accent:#39ff88; --accentText:#020a05; --a1:#39ff88; --a2:#0affc0;
  --track:#06210f; --redact:#39ff88; --redactText:#020a05;
  --radius:6px; --shadow:0 0 30px rgba(57,255,136,.16); --blur:none;
  --font:ui-monospace,Menlo,Consolas,"Noto Sans Thai",monospace;
  --mono:ui-monospace,Menlo,Consolas,"Noto Sans Thai",monospace;
  --cEmail:#ffd43b; --cCard:#ff7b7b; --cPhone:#5cd8ff; --cDob:#e08cff; --cAddress:#b2ff8a;
}
html[data-theme="paper"]{
  --bg:#efe9db; --text:#151515; --muted:#635b4a;
  --panel:#fbf8f0; --line:#c9bfa6;
  --accent:#b3261e; --accentText:#fff; --a1:#b3261e; --a2:#e0653f;
  --track:#e2dac6; --redact:#111; --redactText:#fbf8f0;
  --radius:8px; --shadow:6px 6px 0 rgba(0,0,0,.13); --blur:none;
  --font:"Sarabun","Noto Sans Thai",Georgia,serif;
  --mono:"Courier New",Courier,"Noto Sans Thai",monospace;
  --cEmail:#b83f0a; --cCard:#b01038; --cPhone:#1a44c0; --cDob:#5f22c4; --cAddress:#116b32;
}

/* ============ BASE ============ */
*,*::before,*::after{box-sizing:border-box}
body{
  margin:0;min-height:100vh;background:var(--bg);color:var(--text);
  font-family:var(--font);font-size:15px;line-height:1.6;
  transition:background .5s ease,color .3s ease;-webkit-font-smoothing:antialiased;
}
button{font:inherit;color:inherit;background:none;border:0;cursor:pointer}
::selection{background:color-mix(in srgb,var(--accent) 35%,transparent)}

/* ============ ANIMATED BACKGROUND ============ */
.bg{position:fixed;inset:0;z-index:-1;overflow:hidden;pointer-events:none}
.blob{position:absolute;width:52vmax;height:52vmax;border-radius:50%;filter:blur(90px);opacity:.5}
.blob.b1{background:radial-gradient(circle,#8b7bff,transparent 65%);top:-18vmax;left:-12vmax;animation:d1 22s ease-in-out infinite alternate}
.blob.b2{background:radial-gradient(circle,#ff6b9d,transparent 65%);top:-10vmax;right:-16vmax;animation:d2 26s ease-in-out infinite alternate}
.blob.b3{background:radial-gradient(circle,#4dc3ff,transparent 65%);bottom:-24vmax;left:20vmax;animation:d3 30s ease-in-out infinite alternate}
@keyframes d1{to{transform:translate(10vmax,8vmax) scale(1.15)}}
@keyframes d2{to{transform:translate(-8vmax,10vmax) scale(1.1)}}
@keyframes d3{to{transform:translate(6vmax,-8vmax) scale(1.2)}}
html[data-theme="terminal"] .bg{display:none}
html[data-theme="paper"] .blob{opacity:.22;filter:blur(70px)}
html[data-theme="terminal"] body::after{
  content:"";position:fixed;inset:0;pointer-events:none;z-index:60;
  background:repeating-linear-gradient(0deg,rgba(0,0,0,.22) 0 1px,transparent 1px 3px);
}
html[data-theme="paper"] body{
  background-image:linear-gradient(rgba(0,0,0,.045) 1px,transparent 1px);
  background-size:100% 30px;
}

/* ============ NAV ============ */
.nav{
  position:sticky;top:0;z-index:40;display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  justify-content:space-between;
  padding:12px clamp(14px,3.5vw,36px);border-bottom:1px solid var(--line);
  background:color-mix(in srgb,var(--bg) 80%,transparent);
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
}
.seg{display:inline-flex;gap:3px;padding:4px;border:1px solid var(--line);border-radius:15px;background:var(--panel)}
.seg button{font-size:.85rem;color:var(--muted);padding:7px 15px;border-radius:11px;transition:.2s;font-weight:500}
.seg button:hover{color:var(--text)}
.seg button.active{background:var(--accent);color:var(--accentText);font-weight:700;box-shadow:0 6px 16px -8px var(--accent)}

.themes{display:flex;gap:8px}
.swatch{width:32px;height:32px;padding:0;border-radius:50%;border:2px solid var(--line);transition:.2s}
.swatch:hover{transform:scale(1.12)}
.swatch.active{border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 32%,transparent)}
.swatch[data-theme="aurora"]{background:linear-gradient(135deg,#8b7bff,#ff6b9d)}
.swatch[data-theme="terminal"]{background:#04120a;border-color:#39ff88}
.swatch[data-theme="paper"]{background:#efe9db;border-color:#b3261e}

/* ============ LAYOUT ============ */
main{max-width:1320px;margin:0 auto;padding:clamp(16px,2.6vw,30px) clamp(14px,3.5vw,36px) 64px}

.filters{display:flex;flex-wrap:wrap;gap:9px;align-items:center;margin-bottom:16px}
.filtersLabel{font-size:.82rem;color:var(--muted);margin-right:2px;font-weight:500}
.filter{
  display:inline-flex;align-items:center;gap:8px;padding:7px 14px;border-radius:999px;
  font-size:.85rem;font-weight:500;border:1px solid var(--line);background:var(--panel);
  color:var(--text);transition:.2s;user-select:none;
}
.filter:hover{transform:translateY(-2px);border-color:var(--accent)}
.filter .dot{width:9px;height:9px;border-radius:50%;background:var(--k);box-shadow:0 0 9px var(--k);flex:none}
.filter b{
  font-family:var(--mono);font-size:.72rem;font-weight:700;min-width:22px;text-align:center;
  padding:1px 6px;border-radius:999px;
  background:color-mix(in srgb,var(--k) 26%,transparent);color:var(--k);
}
.filter[aria-pressed="false"]{
  border-style:dashed;background:transparent;color:var(--muted);
}
.filter[aria-pressed="false"] .dot{background:var(--muted);box-shadow:none}
.filter[aria-pressed="false"] b{background:transparent;color:var(--muted)}

#allBtn{--k:var(--accent);font-weight:600}
[data-k="email"]{--k:var(--cEmail)}
[data-k="card"]{--k:var(--cCard)}
[data-k="phone"]{--k:var(--cPhone)}
[data-k="dob"]{--k:var(--cDob)}
[data-k="address"]{--k:var(--cAddress)}

.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}

.panel{
  position:relative;display:flex;flex-direction:column;overflow:hidden;
  border:1px solid var(--line);border-radius:var(--radius);
  background:var(--panel);box-shadow:var(--shadow);
  backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);
  transition:border-color .25s,box-shadow .25s;
}
.panel.drag{border-color:var(--accent);box-shadow:0 0 0 4px color-mix(in srgb,var(--accent) 24%,transparent),var(--shadow)}

.pHead{display:flex;align-items:center;gap:10px;padding:13px 17px;border-bottom:1px solid var(--line);font-size:.92rem;font-weight:600}
.pHead .meta{margin-left:auto;font-family:var(--mono);font-size:.76rem;font-weight:400;color:var(--muted)}
.led{width:9px;height:9px;border-radius:50%;background:var(--accent);box-shadow:0 0 10px var(--accent);animation:pulse 2s ease-in-out infinite;flex:none}
html[data-theme="terminal"] .led{border-radius:0;animation:blink 1.1s steps(2) infinite}
html[data-theme="paper"] .led{box-shadow:none;animation:none}
@keyframes pulse{50%{opacity:.3}}
@keyframes blink{50%{opacity:0}}

.pulse{position:absolute;top:0;left:0;right:0;height:2px;overflow:hidden;opacity:0;transition:opacity .2s}
.pulse::after{content:"";position:absolute;inset:0;transform:translateX(-100%);background:linear-gradient(90deg,transparent,var(--accent),transparent)}
.panel.busy .pulse{opacity:1}
.panel.busy .pulse::after{animation:sweep 1.1s linear infinite}
@keyframes sweep{to{transform:translateX(100%)}}

/* ============ EDITOR / OUTPUT ============ */
.editor{position:relative;height:clamp(300px,44vh,440px)}
textarea,.backdrop{
  font:14.5px/1.75 var(--mono);padding:18px 20px;margin:0;border:0;tab-size:4;
  white-space:pre-wrap;overflow-wrap:break-word;word-break:normal;letter-spacing:normal;
}
textarea{
  position:absolute;inset:0;width:100%;height:100%;z-index:1;resize:none;overflow:auto;outline:0;
  background:transparent;color:var(--text);caret-color:var(--accent);
}
textarea::placeholder{color:var(--muted);opacity:1}
.backdrop{position:absolute;inset:0;overflow:hidden;color:transparent;pointer-events:none;will-change:transform}
.backdrop mark{
  color:transparent;border-radius:4px;padding:0;
  background:color-mix(in srgb,var(--k) 32%,transparent);box-shadow:inset 0 -2px 0 var(--k);
}

.output{
  height:clamp(300px,44vh,440px);overflow:auto;padding:14px 0;counter-reset:ln;
  font:14.5px/1.75 var(--mono);
}
.ln{display:flex;counter-increment:ln;padding-right:18px}
.ln::before{
  content:counter(ln);flex:none;width:3.1em;padding-right:14px;text-align:right;
  color:var(--muted);opacity:.85;user-select:none;font-size:.85em;
}
.ln.hit{background:color-mix(in srgb,var(--accent) 10%,transparent);box-shadow:inset 3px 0 0 var(--accent)}
.ln.hit::before{color:var(--accent);opacity:1;font-weight:700}
.tx{flex:1;min-width:0;white-space:pre-wrap;overflow-wrap:break-word}
.tx:empty::after{content:"\200b"}

.output mark{
  position:relative;color:inherit;font-weight:700;padding:1px 5px;border-radius:6px;cursor:help;
  background:color-mix(in srgb,var(--k) 26%,transparent);box-shadow:inset 0 -2px 0 var(--k);
  animation:pop .3s ease both;
}
@keyframes pop{from{opacity:.35}}
.output mark::after{
  content:attr(data-label);position:absolute;left:50%;bottom:100%;transform:translate(-50%,-6px);
  background:var(--text);color:var(--bg);font:600 11.5px/1 var(--font);padding:6px 10px;
  border-radius:7px;white-space:nowrap;opacity:0;pointer-events:none;transition:opacity .16s;z-index:6;
}
.output mark:hover::after{opacity:1}
html[data-mode="plain"] .output mark{background:none;box-shadow:none;padding:0;font-weight:inherit}
html[data-mode="redact"] .output mark{background:var(--redact);color:transparent;box-shadow:none;border-radius:3px}
html[data-mode="redact"] .output mark:hover{color:var(--redactText)}

.empty{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:20px;text-align:center;color:var(--muted)}
.empty .ico{font-size:36px;opacity:.7;margin-bottom:6px}
.empty p{margin:0;font-size:.95rem;color:var(--text);font-family:var(--font);font-weight:600}
.empty span{font-size:.8rem;color:var(--muted)}

.output::-webkit-scrollbar,textarea::-webkit-scrollbar{width:10px;height:10px}
.output::-webkit-scrollbar-track,textarea::-webkit-scrollbar-track{background:transparent}
.output::-webkit-scrollbar-thumb,textarea::-webkit-scrollbar-thumb{
  background:var(--line);border-radius:999px;border:3px solid transparent;background-clip:padding-box;
}
.output::-webkit-scrollbar-thumb:hover,textarea::-webkit-scrollbar-thumb:hover{background:var(--muted);background-clip:padding-box}
.output,textarea{scrollbar-width:thin;scrollbar-color:var(--line) transparent}

/* ============ FOOTER / BUTTONS ============ */
.pFoot{display:flex;align-items:center;gap:9px;padding:11px 15px;border-top:1px solid var(--line);flex-wrap:wrap}
.pFoot .hint{margin-left:auto;font-size:.78rem;color:var(--muted);font-family:var(--mono)}
.btn{
  display:inline-flex;align-items:center;gap:7px;font-size:.85rem;font-weight:500;
  padding:8px 15px;border-radius:12px;border:1px solid var(--line);background:var(--panel);
  color:var(--text);transition:.2s;
}
.btn:hover{transform:translateY(-2px);border-color:var(--accent)}
.btn:active{transform:translateY(0)}
.btn[aria-pressed="false"]{opacity:.6}
.btn.primary{
  border-color:transparent;color:#fff;background:linear-gradient(135deg,var(--a1),var(--a2));
  box-shadow:0 10px 24px -14px var(--a1);
}
html[data-theme="terminal"] .btn.primary{color:var(--accentText);border-radius:4px}
html[data-theme="paper"] .btn.primary{border-radius:4px;box-shadow:3px 3px 0 rgba(0,0,0,.2)}

/* ============ DASHBOARD ============ */
.dash{
  margin-top:18px;display:flex;gap:24px;align-items:center;flex-wrap:wrap;
  padding:18px 22px;border:1px solid var(--line);border-radius:var(--radius);
  background:var(--panel);box-shadow:var(--shadow);
  backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);
}
.dashNum{display:flex;flex-direction:column;align-items:center;min-width:112px}
.dashNum strong{
  font-size:2.5rem;line-height:1;font-family:var(--mono);font-weight:700;
  background:linear-gradient(135deg,var(--a1),var(--a2));
  -webkit-background-clip:text;background-clip:text;color:transparent;
}
html[data-theme="terminal"] .dashNum strong{background:none;color:var(--accent)}
.dashNum span{font-size:.75rem;color:var(--muted);margin-top:6px;text-align:center;line-height:1.3;font-weight:500}
.dashBody{flex:1;min-width:220px}
.summary{margin:0 0 10px;font-size:.92rem;font-weight:600}
.bar{display:flex;height:10px;border-radius:999px;overflow:hidden;background:var(--track)}
.bar i{display:block;height:100%;width:0;background:var(--k);transition:width .5s cubic-bezier(.2,.8,.2,1)}

/* ============ TOAST ============ */
.toast{
  position:fixed;left:50%;bottom:26px;transform:translate(-50%,16px);
  background:var(--text);color:var(--bg);padding:10px 20px;border-radius:999px;
  font-size:.88rem;font-weight:600;opacity:0;pointer-events:none;transition:.28s;z-index:70;
  box-shadow:0 14px 34px -14px rgba(0,0,0,.7);
}
.toast.show{opacity:1;transform:translate(-50%,0)}

@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<div class="bg" aria-hidden="true">
  <span class="blob b1"></span><span class="blob b2"></span><span class="blob b3"></span>
</div>

<nav class="nav">
  <div class="seg" id="modeSeg" role="group" aria-label="โหมดแสดงผล">
    <button type="button" data-mode="highlight" class="active">ไฮไลต์</button>
    <button type="button" data-mode="redact">แถบดำ</button>
    <button type="button" data-mode="plain">ปกติ</button>
  </div>
  <div class="themes" id="themes" role="group" aria-label="ธีมสี">
    <button type="button" class="swatch" data-theme="aurora" title="Aurora" aria-label="ธีม Aurora"></button>
    <button type="button" class="swatch" data-theme="terminal" title="Terminal" aria-label="ธีม Terminal"></button>
    <button type="button" class="swatch" data-theme="paper" title="Paper" aria-label="ธีม Paper"></button>
  </div>
</nav>

<main>
  <div class="filters" id="filters"><span class="filtersLabel">ตรวจสอบ:</span></div>

  <div class="grid">
    <section class="panel" id="inPanel">
      <div class="pHead"><span class="led"></span><span>ข้อความต้นฉบับ</span><span class="meta" id="inMeta">0 ตัวอักษร</span></div>
      <div class="pulse"></div>
      <div class="editor">
        <div class="backdrop" id="backdrop" aria-hidden="true"></div>
        <textarea id="input" spellcheck="false" autofocus aria-label="ข้อความต้นฉบับ"
          placeholder="พิมพ์ หรือวางข้อความที่นี่…&#10;&#10;ตัวอย่าง:&#10;โทร 081-234-5678&#10;อีเมล somchai.j@company.co.th&#10;บัตรเครดิต 4539 8712 0045 1123"></textarea>
      </div>
      <div class="pFoot">
        <button class="btn" id="clearBtn" type="button">🧹 ล้าง</button>
        <button class="btn" id="hlBtn" type="button" aria-pressed="true" title="เปิด/ปิดไฮไลต์ตัวอย่างในช่องข้อความต้นฉบับ">🔆 ไฮไลต์ตัวอย่าง</button>
        <span class="hint">ลากไฟล์ .txt / .log มาวางได้</span>
      </div>
    </section>

    <section class="panel" id="outPanel">
      <div class="pHead"><span class="led"></span><span>ข้อความที่ปกป้องแล้ว</span><span class="meta" id="outMeta">0 รายการ</span></div>
      <div class="pulse"></div>
      <div class="output" id="output"></div>
      <div class="pFoot">
        <button class="btn primary" id="copyBtn" type="button">📋 คัดลอกผลลัพธ์</button>
        <button class="btn" id="saveBtn" type="button">⬇️ ดาวน์โหลด</button>
        <span class="hint">Ctrl+Shift+C</span>
      </div>
    </section>
  </div>

  <section class="dash">
    <div class="dashNum">
      <strong id="totalNum">0</strong>
      <span>รายการ<br>ถูกปกป้อง</span>
    </div>
    <div class="dashBody">
      <p class="summary" id="summary" aria-live="polite">พิมพ์หรือวางข้อความเพื่อเริ่มตรวจสอบ</p>
      <div class="bar" id="bar"></div>
    </div>
  </section>
</main>

<div class="toast" id="toast" role="status"></div>

<script>
const KINDS = ["email", "card", "phone", "dob", "address"];
const LABELS = { email: "อีเมล", card: "บัตรเครดิต", phone: "เบอร์โทร", dob: "วันเกิด", address: "ที่อยู่" };
const ZERO = { email: 0, card: 0, phone: 0, dob: 0, address: 0 };

const root = document.documentElement;
const input = document.getElementById("input");
const backdrop = document.getElementById("backdrop");
const output = document.getElementById("output");
const inPanel = document.getElementById("inPanel");
const outPanel = document.getElementById("outPanel");
const inMeta = document.getElementById("inMeta");
const outMeta = document.getElementById("outMeta");
const summary = document.getElementById("summary");
const totalNum = document.getElementById("totalNum");
const toastEl = document.getElementById("toast");
const barBox = document.getElementById("bar");
const filtersBox = document.getElementById("filters");
const hlBtn = document.getElementById("hlBtn");

let enabled = new Set(KINDS);
let showBackdrop = read("backdrop") !== "off";
let timer = null, seq = 0, ctrl = null, plain = "", toastT = null, shownTotal = 0;
let lastData = null, lastText = "";

/* ---------- storage ---------- */
function save(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
function read(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
try {
  const raw = JSON.parse(read("kinds") || "null");
  if (Array.isArray(raw)) {
    const kept = raw.filter(k => KINDS.includes(k));
    if (kept.length) enabled = new Set(kept);
  }
} catch (e) {}

/* ---------- ui helpers ---------- */
function el(tag, cls) { const n = document.createElement(tag); if (cls) n.className = cls; return n; }
function toast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add("show");
  clearTimeout(toastT);
  toastT = setTimeout(() => toastEl.classList.remove("show"), 1700);
}

/* ---------- theme / mode ---------- */
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

/* ---------- filter chips + meter bars ---------- */
const filterEls = {}, countEls = {}, bars = {};

KINDS.forEach(k => {
  const b = el("button", "filter");
  b.type = "button";
  b.dataset.k = k;
  b.setAttribute("aria-pressed", "true");
  const dot = el("span", "dot");
  const name = el("span"); name.textContent = LABELS[k];
  const num = el("b"); num.textContent = "0";
  b.append(dot, name, num);
  b.addEventListener("click", () => {
    if (enabled.has(k)) enabled.delete(k); else enabled.add(k);
    save("kinds", JSON.stringify([...enabled]));
    syncFilters();
    refresh();
  });
  filtersBox.appendChild(b);
  filterEls[k] = b; countEls[k] = num;

  const seg = el("i"); seg.dataset.k = k; barBox.appendChild(seg); bars[k] = seg;
});

const allBtn = el("button", "filter");
allBtn.type = "button"; allBtn.id = "allBtn"; allBtn.textContent = "ทั้งหมด";
allBtn.addEventListener("click", () => {
  enabled = new Set(KINDS);
  save("kinds", JSON.stringify([...enabled]));
  syncFilters();
  refresh();
});
filtersBox.appendChild(allBtn);

function syncFilters() {
  for (const k of KINDS) {
    const on = enabled.has(k);
    filterEls[k].setAttribute("aria-pressed", String(on));
  }
}

/* ---------- apply enabled filters to server segments ---------- */
function applyFilters(segments) {
  const out = [];
  const stats = { email: 0, card: 0, phone: 0, dob: 0, address: 0 };
  let masked = "";
  for (const s of segments) {
    if (s.kind && !enabled.has(s.kind)) {
      // turned off → keep original text untouched
      out.push({ text: s.orig, kind: null });
      masked += s.orig;
    } else {
      out.push(s);
      masked += s.text;
      if (s.kind) stats[s.kind]++;
    }
  }
  return { segments: out, stats, masked };
}

/* ---------- backdrop (highlight behind textarea) ---------- */
function paintBackdrop(segments) {
  const frag = document.createDocumentFragment();
  if (segments && showBackdrop) {
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
  backdrop.style.transform = "translateY(" + (-input.scrollTop) + "px)";
}
input.addEventListener("scroll", () => {
  backdrop.style.transform = "translateY(" + (-input.scrollTop) + "px)";
});

/* ---------- output ---------- */
function emptyState() {
  const box = el("div", "empty");
  const ico = el("div", "ico"); ico.textContent = "🔍";
  const p = el("p"); p.textContent = "ผลลัพธ์จะปรากฏที่นี่";
  const s = el("span"); s.textContent = "เริ่มพิมพ์ข้อความด้านซ้ายได้เลย";
  box.append(ico, p, s);
  return box;
}

function paintOutput(segments) {
  if (!segments.length) {
    output.replaceChildren(emptyState());
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
        const m = el("mark");
        m.dataset.k = s.kind;
        m.dataset.label = LABELS[s.kind];
        m.textContent = part;
        cur.tx.appendChild(m);
        cur.hit = true;
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

/* ---------- animated total ---------- */
function animateTotal(target) {
  const from = shownTotal;
  shownTotal = target;
  if (from === target) { totalNum.textContent = target; return; }
  const t0 = performance.now(), dur = 420;
  function step(t) {
    const p = Math.min(1, (t - t0) / dur);
    const e = 1 - Math.pow(1 - p, 3);
    totalNum.textContent = Math.round(from + (target - from) * e);
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

/* ---------- meter ---------- */
function paintMeter(stats, info, hasText) {
  let total = 0;
  for (const k of KINDS) total += stats[k] || 0;
  for (const k of KINDS) {
    const v = stats[k] || 0;
    countEls[k].textContent = v;
    bars[k].style.width = total ? (v / total * 100) + "%" : "0%";
  }
  animateTotal(total);
  outMeta.textContent = total + " รายการ";

  if (!hasText) summary.textContent = "พิมพ์หรือวางข้อความเพื่อเริ่มตรวจสอบ";
  else if (total) summary.textContent = "ตรวจพบและปกป้อง " + total + " รายการ · อยู่ใน " + info.hits + " จาก " + info.lines + " บรรทัด";
  else if (enabled.size < KINDS.length) summary.textContent = "ไม่พบข้อมูลในประเภทที่เลือกไว้ (บางประเภทถูกปิดอยู่)";
  else summary.textContent = "ไม่พบข้อมูลส่วนบุคคลในข้อความนี้ 🎉";
}

/* ---------- render from a server payload ---------- */
function render(data) {
  const f = applyFilters(data.segments);
  plain = f.masked;
  paintBackdrop(f.segments);
  paintMeter(f.stats, paintOutput(f.segments), true);
}

/* re-render without a network round-trip (used by filter toggles) */
function refresh() {
  if (lastData && lastText === input.value) render(lastData);
  else run();
}

/* ---------- main run ---------- */
async function run() {
  const mine = ++seq;
  const text = input.value;
  inMeta.textContent = text.length.toLocaleString("th-TH") + " ตัวอักษร";

  if (ctrl) ctrl.abort();
  if (!text) {
    lastData = null; lastText = "";
    plain = "";
    paintBackdrop(null);
    outPanel.classList.remove("busy");
    paintMeter(ZERO, paintOutput([]), false);
    return;
  }

  ctrl = new AbortController();
  outPanel.classList.add("busy");
  try {
    const res = await fetch("/api/mask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text }),
      signal: ctrl.signal
    });
    if (res.status === 413) { toast("ข้อความยาวเกินไป"); return; }
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    if (mine !== seq) return;
    lastData = data;
    lastText = text;
    render(data);
  } catch (e) {
    if (e.name === "AbortError") return;
    toast("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้");
  } finally {
    if (mine === seq) outPanel.classList.remove("busy");
  }
}

function onInput() {
  paintBackdrop(null);
  clearTimeout(timer);
  timer = setTimeout(run, 130);
}

/* ---------- events ---------- */
input.addEventListener("input", onInput);

document.getElementById("modeSeg").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (b) applyMode(b.dataset.mode);
});
document.getElementById("themes").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (b) applyTheme(b.dataset.theme);
});

document.getElementById("clearBtn").addEventListener("click", () => {
  input.value = "";
  input.scrollTop = 0;
  onInput();
  input.focus();
});

/* toggle the live highlight preview inside the input panel */
function syncHlBtn() {
  hlBtn.setAttribute("aria-pressed", String(showBackdrop));
}
hlBtn.addEventListener("click", () => {
  showBackdrop = !showBackdrop;
  save("backdrop", showBackdrop ? "on" : "off");
  syncHlBtn();
  paintBackdrop(lastData && lastText === input.value ? applyFilters(lastData.segments).segments : null);
});

async function doCopy() {
  if (!plain) { toast("ยังไม่มีผลลัพธ์ให้คัดลอก"); return; }
  try {
    await navigator.clipboard.writeText(plain);
    toast("คัดลอกผลลัพธ์แล้ว ✓");
  } catch (e) {
    toast("คัดลอกไม่สำเร็จ");
  }
}
document.getElementById("copyBtn").addEventListener("click", doCopy);

document.getElementById("saveBtn").addEventListener("click", () => {
  if (!plain) { toast("ยังไม่มีผลลัพธ์ให้ดาวน์โหลด"); return; }
  const blob = new Blob([plain], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = el("a");
  a.href = url; a.download = "masked.txt";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("ดาวน์โหลดแล้ว ⬇️");
});

document.addEventListener("keydown", e => {
  const mod = e.ctrlKey || e.metaKey;
  if (!mod) return;
  if (e.key === "Enter") { e.preventDefault(); run(); }
  else if (e.shiftKey && (e.key === "c" || e.key === "C")) { e.preventDefault(); doCopy(); }
});

/* ---------- drag & drop ---------- */
["dragenter", "dragover"].forEach(ev =>
  inPanel.addEventListener(ev, e => { e.preventDefault(); inPanel.classList.add("drag"); }));
["dragleave", "drop"].forEach(ev =>
  inPanel.addEventListener(ev, e => { e.preventDefault(); inPanel.classList.remove("drag"); }));
inPanel.addEventListener("drop", e => {
  const file = e.dataTransfer.files[0];
  if (!file) return;
  if (file.size > 900000) { toast("ไฟล์ใหญ่เกินไป (สูงสุด 900 KB)"); return; }
  const reader = new FileReader();
  reader.onload = () => { input.value = String(reader.result); onInput(); };
  reader.readAsText(file);
});
window.addEventListener("dragover", e => e.preventDefault());
window.addEventListener("drop", e => e.preventDefault());

/* ---------- boot ---------- */
applyTheme(read("theme") || "aurora");
applyMode(read("mode") || "highlight");
syncFilters();
syncHlBtn();
run();
</script>
</body>
</html>"""


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
