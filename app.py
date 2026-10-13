#!/usr/bin/env python3
"""PDPA Data Masking - ระบบเซ็นเซอร์ข้อมูลลูกค้าเพื่อความปลอดภัย

Web application ที่ใช้ regex ของ Python (โมดูล re) ในการเซ็นเซอร์ข้อมูลส่วนบุคคล
ไม่ต้องติดตั้งไลบรารีเพิ่ม (ใช้ http.server ของ standard library)

วิธีรัน:   python app.py            แล้วเปิด http://localhost:8000
ทดสอบ:    python app.py --test     (ตรวจตัวอย่างจากโจทย์ทั้งหมด)
"""

import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY_BYTES = 1_000_000

# ---------------------------------------------------------------------------
# Regex: รวมทุกรูปแบบเป็น pattern เดียว (alternation) เพื่อให้สแกนข้อความรอบเดียว
# และไม่ให้ผลลัพธ์ของแต่ละกฎซ้อนทับกัน ลำดับสำคัญ: email -> card -> phone -> dob -> address
# ---------------------------------------------------------------------------

EMAIL = (
    r"(?P<email>"
    r"(?P<emailUser>[A-Za-z0-9._%+\-]+)@"
    r"(?P<emailDomain>[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,})"
    r")"
)

# XXXX-XXXX-XXXX-XXXX (รองรับคั่นด้วยช่องว่าง หรือเลข 16 หลักติดกันด้วย)
CARD = (
    r"(?P<card>(?<!\d)\d{4}(?P<cardSep>[- ]?)\d{4}(?P=cardSep)"
    r"\d{4}(?P=cardSep)\d{4}(?!\d))"
)

# XXX-XXX-XXXX (รองรับ . หรือช่องว่าง และเบอร์ 10 หลักติดกันที่ขึ้นต้นด้วย 0)
PHONE = (
    r"(?P<phone>(?<!\d)(?:"
    r"\d{3}(?P<phoneSep>[-. ])\d{3}(?P=phoneSep)\d{4}"
    r"|0\d{9}"
    r")(?!\d))"
)

# DOB:25/12/2549  (ปี พ.ศ. 4 หลัก)
DOB = (
    r"(?P<dob>(?P<dobLabel>\b(?:DOB|วันเกิด)\s*:\s*)"
    r"(?P<dobDay>\d{1,2})(?P<dobSep>[/.\-])(?P<dobMonth>\d{1,2})(?P=dobSep)"
    r"(?P<dobYear>\d{4})(?!\d))"
)

# Address: <เลขที่บ้าน> ... เซ็นเซอร์เฉพาะเลขที่บ้าน (รองรับ 12/3, 99-1)
ADDRESS = (
    r"(?P<address>(?P<addrLabel>\b(?:Address|ที่อยู่)\s*:\s*)"
    r"(?P<addrNo>\d+(?:[/\-]\d+)*))"
)

PATTERN = re.compile("|".join([EMAIL, CARD, PHONE, DOB, ADDRESS]), re.IGNORECASE)

KINDS = ["email", "card", "phone", "dob", "address"]


# ---------------------------------------------------------------------------
# Masking functions
# ---------------------------------------------------------------------------

def maskDigits(text, keep=4):
    """แทนตัวเลขด้วย X ยกเว้น keep ตัวท้าย (คงเครื่องหมายคั่นไว้)"""
    head, tail = text[:-keep], text[-keep:]
    return re.sub(r"\d", "X", head) + tail


def maskEmail(m):
    user = m.group("emailUser")
    size = len(user)
    if size == 1:
        hidden = "*"
    elif size == 2:
        hidden = user[0] + "*"
    else:
        hidden = user[0] + "*" * (size - 2) + user[-1]
    return hidden + "@" + m.group("emailDomain")


def maskCard(m):
    return maskDigits(m.group("card"))


def maskPhone(m):
    return maskDigits(m.group("phone"))


def maskDob(m):
    sep = m.group("dobSep")
    year = m.group("dobYear")
    return m.group("dobLabel") + "XX" + sep + "XX" + sep + year[:2] + "XX"


def maskAddress(m):
    return m.group("addrLabel") + re.sub(r"\d", "X", m.group("addrNo"))


MASKERS = {
    "email": maskEmail,
    "card": maskCard,
    "phone": maskPhone,
    "dob": maskDob,
    "address": maskAddress,
}


def detectKind(m):
    for kind in KINDS:
        if m.group(kind) is not None:
            return kind
    return None


def maskText(text):
    """คืนค่า (ข้อความที่เซ็นเซอร์แล้ว, segments สำหรับไฮไลต์, สถิติ)"""
    segments = []
    stats = {kind: 0 for kind in KINDS}
    pos = 0
    for m in PATTERN.finditer(text):
        if m.start() > pos:
            segments.append({"text": text[pos:m.start()], "kind": None})
        kind = detectKind(m)
        segments.append({"text": MASKERS[kind](m), "kind": kind})
        stats[kind] += 1
        pos = m.end()
    if pos < len(text):
        segments.append({"text": text[pos:], "kind": None})
    masked = "".join(s["text"] for s in segments)
    return masked, segments, stats


# ---------------------------------------------------------------------------
# Self test (ตัวอย่างจากโจทย์ + edge cases)
# ---------------------------------------------------------------------------

def runTests():
    cases = [
        ("1234-5678-9012-3456", "XXXX-XXXX-XXXX-3456"),
        ("somchai.d@company.com", "s*******d@company.com"),
        ("093-245-7894", "XXX-XXX-7894"),
        ("DOB:25/12/2549", "DOB:XX/XX/25XX"),
        (
            "Address: 689 ซอยลาดกระบัง 19 ถนนลาดกระบัง แขวงลาดกระบัง เขตลาดกระบัง กรุงเทพฯ",
            "Address: XXX ซอยลาดกระบัง 19 ถนนลาดกระบัง แขวงลาดกระบัง เขตลาดกระบัง กรุงเทพฯ",
        ),
        # edge cases
        ("ab@x.co", "a*@x.co"),
        ("a@x.co", "*@x.co"),
        ("1234 5678 9012 3456", "XXXX XXXX XXXX 3456"),
        ("0932457894", "XXXXXX7894"),
        ("Address: 12/3 หมู่ 5 ต.บางพลี", "Address: XX/X หมู่ 5 ต.บางพลี"),
        ("dob: 1/2/2530", "dob: XX/XX/25XX"),
        ("ordernumber 12345 ไม่ใช่ข้อมูลส่วนบุคคล", "ordernumber 12345 ไม่ใช่ข้อมูลส่วนบุคคล"),
    ]
    failed = 0
    for source, expected in cases:
        actual = maskText(source)[0]
        ok = actual == expected
        failed += not ok
        print(("PASS" if ok else "FAIL"), "|", source, "=>", actual)
    print("\nall passed" if not failed else "\n%d failed" % failed)
    return failed


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDPA Data Masking</title>
<style>
:root {
    --bg: #f4f6fb; --card: #ffffff; --text: #1d2433; --muted: #6b7488;
    --border: #dde2ee; --accent: #3b5bdb; --accentSoft: #e7ecff;
    --email: #e8590c; --card-c: #c2255c; --phone: #1c7ed6; --dob: #7048e8; --address: #2b8a3e;
    --shadow: 0 6px 24px rgba(30, 40, 90, .08);
}
@media (prefers-color-scheme: dark) {
    :root {
        --bg: #0f1320; --card: #181d2e; --text: #e6e9f5; --muted: #8b94ad;
        --border: #2a3150; --accent: #748ffc; --accentSoft: #222a4d;
        --email: #ff922b; --card-c: #f06595; --phone: #4dabf7; --dob: #9775fa; --address: #51cf66;
        --shadow: 0 6px 24px rgba(0, 0, 0, .35);
    }
}
* { box-sizing: border-box; }
body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: "Sarabun", "Noto Sans Thai", system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.55;
}
header { padding: 28px 20px 8px; max-width: 1200px; margin: 0 auto; }
h1 { margin: 0; font-size: 1.7rem; display: flex; align-items: center; gap: 10px; }
.sub { color: var(--muted); margin: 4px 0 0; }
main { max-width: 1200px; margin: 0 auto; padding: 16px 20px 40px; }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; align-items: center; }
button {
    font: inherit; cursor: pointer; border: 1px solid var(--border); background: var(--card);
    color: var(--text); padding: 8px 14px; border-radius: 10px; transition: .15s;
}
button:hover { border-color: var(--accent); transform: translateY(-1px); }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.spacer { flex: 1; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 860px) { .grid { grid-template-columns: 1fr; } }
.panel {
    background: var(--card); border: 1px solid var(--border); border-radius: 16px;
    box-shadow: var(--shadow); display: flex; flex-direction: column; min-height: 340px;
}
.panelHead {
    padding: 12px 16px; border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; font-weight: 600;
}
.panelHead small { color: var(--muted); font-weight: 400; }
textarea, .output {
    flex: 1; width: 100%; border: 0; outline: 0; resize: vertical; background: transparent;
    color: var(--text); padding: 16px; font: 0.95rem/1.7 "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace;
    min-height: 280px; white-space: pre-wrap; word-break: break-word;
}
.output { overflow: auto; }
.placeholder { color: var(--muted); }
mark { padding: 1px 4px; border-radius: 5px; font-weight: 600; color: #fff; }
.highlightOff mark { background: transparent !important; color: inherit; padding: 0; font-weight: inherit; }
mark.email { background: var(--email); } mark.card { background: var(--card-c); }
mark.phone { background: var(--phone); } mark.dob { background: var(--dob); }
mark.address { background: var(--address); }
.stats { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 0; }
.chip {
    display: flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: 999px;
    background: var(--card); border: 1px solid var(--border); font-size: .9rem;
}
.dot { width: 10px; height: 10px; border-radius: 50%; }
.chip b { font-size: 1.05rem; }
.total { background: var(--accentSoft); border-color: transparent; }
.rules { margin-top: 22px; background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 6px 16px 12px; }
.rules h2 { font-size: 1.05rem; }
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--muted); font-weight: 600; }
code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .85rem; }
footer { text-align: center; color: var(--muted); font-size: .85rem; padding-bottom: 28px; }
</style>
</head>
<body>
<header>
    <h1>🛡️ PDPA Data Masking</h1>
    <p class="sub">ระบบเซ็นเซอร์ข้อมูลลูกค้าเพื่อความปลอดภัย &mdash; พิมพ์หรือวาง Log แล้วดูผลลัพธ์ทันที (ประมวลผลด้วย Python <code>re</code>)</p>
</header>
<main>
    <div class="toolbar">
        <button class="primary" id="sampleBtn">📄 โหลด Log ตัวอย่าง</button>
        <button id="clearBtn">🧹 ล้าง</button>
        <span class="spacer"></span>
        <label><input type="checkbox" id="hlToggle" checked> ไฮไลต์ส่วนที่ถูกเซ็นเซอร์</label>
        <button id="copyBtn">📋 คัดลอกผลลัพธ์</button>
    </div>

    <div class="grid">
        <section class="panel">
            <div class="panelHead"><span>Input &mdash; ข้อความต้นฉบับ</span><small id="inCount">0 ตัวอักษร</small></div>
            <textarea id="input" spellcheck="false" placeholder="พิมพ์หรือวางข้อความที่นี่ เช่น&#10;Card 1234-5678-9012-3456 tel 093-245-7894 somchai.d@company.com"></textarea>
        </section>
        <section class="panel">
            <div class="panelHead"><span>Output &mdash; ข้อความที่เซ็นเซอร์แล้ว</span><small id="outCount">0 รายการ</small></div>
            <div class="output" id="output"><span class="placeholder">ผลลัพธ์จะแสดงที่นี่...</span></div>
        </section>
    </div>

    <div class="stats" id="stats"></div>

    <section class="rules">
        <h2>กฎการเซ็นเซอร์</h2>
        <table>
            <tr><th>ประเภท</th><th>รูปแบบ</th><th>ตัวอย่างผลลัพธ์</th></tr>
            <tr><td>💳 บัตรเครดิต</td><td><code>XXXX-XXXX-XXXX-XXXX</code></td><td><code>XXXX-XXXX-XXXX-3456</code></td></tr>
            <tr><td>✉️ อีเมล</td><td>ซ่อนชื่อผู้ใช้ เหลือตัวแรก/ตัวท้าย</td><td><code>s*******d@company.com</code></td></tr>
            <tr><td>📞 เบอร์โทร</td><td><code>XXX-XXX-XXXX</code></td><td><code>XXX-XXX-7894</code></td></tr>
            <tr><td>🎂 วันเกิด</td><td><code>DOB:dd/mm/yyyy</code> (พ.ศ.)</td><td><code>DOB:XX/XX/25XX</code></td></tr>
            <tr><td>🏠 ที่อยู่</td><td><code>Address:</code> เลขที่บ้านเท่านั้น</td><td><code>Address: XXX ซอยลาดกระบัง ...</code></td></tr>
        </table>
    </section>
</main>
<footer>Python <code>re</code> เพียงอย่างเดียวในการจับรูปแบบ &middot; ข้อมูลไม่ถูกบันทึกบนเซิร์ฟเวอร์</footer>

<script>
const LABELS = {
    email: ["อีเมล", "--email"], card: ["บัตรเครดิต", "--card-c"], phone: ["เบอร์โทร", "--phone"],
    dob: ["วันเกิด", "--dob"], address: ["ที่อยู่", "--address"]
};
const sampleLog = [
    "2026-10-13 09:14:02 INFO  [auth] login ok user=somchai.d@company.com",
    "2026-10-13 09:14:05 DEBUG [payment] card=1234-5678-9012-3456 amount=1,250.00 THB",
    "2026-10-13 09:15:41 WARN  [profile] update contact tel=093-245-7894 mail=pimchanok_88@bank.co.th",
    "2026-10-13 09:16:10 INFO  [kyc] customer DOB:25/12/2549 verified",
    "2026-10-13 09:16:11 INFO  [kyc] Address: 689 ซอยลาดกระบัง 19 ถนนลาดกระบัง แขวงลาดกระบัง เขตลาดกระบัง กรุงเทพฯ",
    "2026-10-13 09:17:30 ERROR [payment] declined card 4111 1111 1111 1111 contact 0812345678",
    "2026-10-13 09:18:02 INFO  [batch] processed 12345 records, txn=20261013091802 (ไม่มีข้อมูลส่วนบุคคล)"
].join("\n");

const input = document.getElementById("input");
const output = document.getElementById("output");
const statsBox = document.getElementById("stats");
let timer = null, seq = 0;

function render(segments, stats) {
    output.textContent = "";
    if (!segments.length) {
        const s = document.createElement("span");
        s.className = "placeholder"; s.textContent = "ผลลัพธ์จะแสดงที่นี่...";
        output.appendChild(s);
    }
    for (const seg of segments) {
        if (seg.kind) {
            const m = document.createElement("mark");
            m.className = seg.kind; m.title = LABELS[seg.kind][0]; m.textContent = seg.text;
            output.appendChild(m);
        } else {
            output.appendChild(document.createTextNode(seg.text));
        }
    }
    statsBox.textContent = "";
    let total = 0;
    for (const k of Object.keys(LABELS)) {
        total += stats[k];
        const c = document.createElement("div"); c.className = "chip";
        const d = document.createElement("span"); d.className = "dot"; d.style.background = "var(" + LABELS[k][1] + ")";
        const b = document.createElement("b"); b.textContent = stats[k];
        c.append(d, document.createTextNode(LABELS[k][0] + " "), b);
        statsBox.appendChild(c);
    }
    const t = document.createElement("div"); t.className = "chip total";
    const tb = document.createElement("b"); tb.textContent = total;
    t.append(document.createTextNode("รวมที่ถูกเซ็นเซอร์ "), tb);
    statsBox.appendChild(t);
    document.getElementById("outCount").textContent = total + " รายการ";
}

async function mask() {
    const mine = ++seq;
    const text = input.value;
    document.getElementById("inCount").textContent = text.length + " ตัวอักษร";
    try {
        const res = await fetch("/api/mask", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text })
        });
        const data = await res.json();
        if (mine === seq) { render(data.segments, data.stats); output.dataset.plain = data.masked; }
    } catch (e) {
        output.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้: " + e;
    }
}

input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(mask, 120); });
document.getElementById("sampleBtn").onclick = () => { input.value = sampleLog; mask(); };
document.getElementById("clearBtn").onclick = () => { input.value = ""; mask(); input.focus(); };
document.getElementById("hlToggle").onchange = (e) => output.classList.toggle("highlightOff", !e.target.checked);
document.getElementById("copyBtn").onclick = async (e) => {
    await navigator.clipboard.writeText(output.dataset.plain || "");
    const old = e.target.textContent; e.target.textContent = "✅ คัดลอกแล้ว";
    setTimeout(() => (e.target.textContent = old), 1200);
};
mask();
</script>
</body>
</html>
"""


class MaskHandler(BaseHTTPRequestHandler):
    def sendBytes(self, status, contentType, body):
        self.send_response(status)
        self.send_header("Content-Type", contentType)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def sendJson(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.sendBytes(status, "application/json; charset=utf-8", body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.sendBytes(200, "text/html; charset=utf-8", HTML_PAGE.encode("utf-8"))
        else:
            self.sendJson(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/mask":
            self.sendJson(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self.sendJson(413, {"error": "payload too large"})
            return
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
            text = str(data.get("text", ""))
        except (ValueError, AttributeError):
            self.sendJson(400, {"error": "invalid json"})
            return
        masked, segments, stats = maskText(text)
        self.sendJson(200, {"masked": masked, "segments": segments, "stats": stats})

    def log_message(self, fmt, *args):
        pass  # ไม่บันทึก request เพราะอาจมีข้อมูลส่วนบุคคล


def main():
    if "--test" in sys.argv:
        sys.exit(1 if runTests() else 0)
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), MaskHandler)
    print("PDPA Data Masking running at http://localhost:%d  (Ctrl+C to stop)" % port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
