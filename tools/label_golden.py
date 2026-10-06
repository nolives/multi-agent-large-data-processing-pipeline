"""Local labeling page for the golden set. Standard library only; no network or model calls.

    python3 tools/label_golden.py

Serves http://localhost:8765 and saves every change to evals/golden_50_labeled.csv, so labeling can stop and resume.
The source file is never modified. Labels are a person's judgments: nothing here suggests or prefills them.
"""

import argparse
import csv
import io
import json
import socketserver
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.common import FIELDS, write_text_atomic  # noqa: E402

TOPICS = ("access", "usability", "playback", "downloads", "catalog", "billing", "support", "other")
INTENTS = ("cancellation", "complaint", "request", "praise", "unclear")
SENTIMENTS = ("-1", "-0.5", "0", "0.5", "1")
LABELS = ("topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review")
EXTRA = ("ambiguous", "notes")
COLUMNS = (*FIELDS, *LABELS, *EXTRA)
REQUIRED = ("topic", "intent", "sentiment", "severity", "evidence_quote")


def read_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return [{k: row.get(k) or "" for k in COLUMNS} for row in csv.DictReader(f, strict=True)]


def save_rows(path, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write_text_atomic(path, buffer.getvalue())


def validate(row, labels):
    """Return a cleaned label dict, or raise ValueError naming the problem."""
    clean = {}
    for key, allowed in (("topic", TOPICS), ("intent", INTENTS), ("sentiment", SENTIMENTS), ("severity", "12345")):
        value = str(labels.get(key, "")).strip()
        if value and value not in allowed:
            raise ValueError(f"{key} must be one of {', '.join(allowed)}")
        clean[key] = value
    quote = str(labels.get("evidence_quote", ""))
    if quote and quote not in row["review_text"]:
        raise ValueError("The evidence quote is not an exact substring of the review text")
    clean["evidence_quote"] = quote
    entities = [e.strip().lower() for e in str(labels.get("entities", "")).split(";")]
    clean["entities"] = "; ".join(dict.fromkeys(e for e in entities if e))
    clean["notes"] = str(labels.get("notes", "")).strip()
    started = any(clean[k] for k in REQUIRED)
    for key in ("needs_review", "ambiguous"):
        clean[key] = ("true" if labels.get(key) in (True, "true") else "false") if started else ""
    return clean


def is_complete(row):
    return all(row[k] for k in REQUIRED)


def make_handler(output):
    rows = read_rows(output)
    by_id = {row["review_id"]: row for row in rows}

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, kind="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                self.reply(200, PAGE.encode("utf-8"), "text/html")
            elif self.path == "/api/rows":
                self.reply(200, {"rows": rows, "topics": TOPICS, "intents": INTENTS, "output": str(output)})
            else:
                self.reply(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/api/save":
                return self.reply(404, {"error": "not found"})
            try:
                payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                row = by_id[payload["review_id"]]
                row.update(validate(row, payload["labels"]))
                save_rows(output, rows)
            except KeyError:
                return self.reply(400, {"error": "Unknown review_id"})
            except ValueError as e:
                return self.reply(400, {"error": str(e)})
            self.reply(200, {"row": row, "complete": is_complete(row), "done": sum(map(is_complete, rows))})

        def log_message(self, *args):
            pass

    return Handler, rows


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Golden set labeling</title>
<style>
:root { --bg:#fbfaf7; --panel:#fff; --ink:#1d1d1b; --muted:#6b6a65; --line:#dcd9d0; --accent:#1f6f54; --accent-ink:#fff; --warn:#a4541a; }
@media (prefers-color-scheme: dark) { :root { --bg:#161614; --panel:#1f1f1c; --ink:#ecebe6; --muted:#9c9a92; --line:#383731; --accent:#5fc49f; --accent-ink:#10231c; --warn:#e6a26b; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui, sans-serif; }
main { max-width:860px; margin:0 auto; padding:20px 16px 60px; }
header { display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap; }
h1 { font-size:18px; margin:0; }
.muted { color:var(--muted); font-size:13px; }
#dots { display:flex; flex-wrap:wrap; gap:4px; margin:12px 0 16px; }
#dots button { width:26px; height:24px; padding:0; font-size:11px; border-radius:4px; }
#dots .done { background:var(--accent); color:var(--accent-ink); border-color:var(--accent); }
#dots .current { outline:2px solid var(--ink); outline-offset:1px; }
#text { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; font-size:17px; white-space:pre-wrap; overflow-wrap:anywhere; }
fieldset { border:0; padding:0; margin:18px 0 0; }
legend { font-weight:600; padding:0; margin-bottom:6px; }
.choices { display:flex; flex-wrap:wrap; gap:6px; }
button { font:inherit; color:var(--ink); background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:6px 10px; cursor:pointer; text-align:left; }
button small { display:block; color:var(--muted); font-size:11.5px; line-height:1.3; max-width:190px; }
button.on { background:var(--accent); border-color:var(--accent); color:var(--accent-ink); }
button.on small { color:var(--accent-ink); opacity:.85; }
input[type=text], textarea { font:inherit; color:var(--ink); background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:7px 9px; width:100%; }
#quote { background:var(--panel); border:1px dashed var(--line); border-radius:6px; padding:8px 10px; min-height:38px; white-space:pre-wrap; overflow-wrap:anywhere; margin-bottom:6px; }
label.check { display:inline-flex; gap:6px; align-items:center; margin-right:18px; }
nav { display:flex; justify-content:space-between; align-items:center; gap:10px; margin-top:24px; }
#status { font-size:13px; } #status.error { color:var(--warn); font-weight:600; }
details { margin-top:10px; } pre { margin:6px 0 0; font-size:12.5px; white-space:pre-wrap; color:var(--muted); }
</style></head><body><main>
<header><h1>Golden set labeling</h1><span class="muted"><span id="count"></span> · saves to <span id="output"></span></span></header>
<div id="dots"></div>
<div id="text"></div>
<details><summary class="muted">Show metadata (stars, likes, version, date) — not a basis for labels</summary><pre id="meta"></pre></details>

<fieldset><legend>Topic</legend><div class="choices" id="topic"></div></fieldset>
<fieldset><legend>Intent <span class="muted">(first that fits, left to right)</span></legend><div class="choices" id="intent"></div></fieldset>
<fieldset><legend>Severity</legend><div class="choices" id="severity"></div></fieldset>
<fieldset><legend>Sentiment</legend><div class="choices" id="sentiment"></div></fieldset>
<fieldset><legend>Evidence quote <span class="muted">(select words in the review above, then press the button)</span></legend>
  <div id="quote"></div>
  <div class="choices"><button id="useSelection">Use selection</button><button id="useAll">Use whole text</button><button id="clearQuote">Clear</button></div></fieldset>
<fieldset><legend>Entities <span class="muted">(named in the text; separate with semicolons; may be empty)</span></legend><input type="text" id="entities" placeholder="ads; premium; shuffle"></fieldset>
<fieldset><legend>Flags</legend>
  <label class="check"><input type="checkbox" id="needs_review"> needs review</label>
  <label class="check"><input type="checkbox" id="ambiguous"> ambiguous (more than one defensible label)</label></fieldset>
<fieldset><legend>Notes <span class="muted">(optional; say which other label was defensible)</span></legend><input type="text" id="notes"></fieldset>
<nav><button id="prev">← Previous</button><span id="status" class="muted"></span><button id="next">Next →</button></nav>
</main>
<script>
const HELP = {
  topic: {access:"login, signup, password, account", usability:"navigation, controls, queue, playlists, ads", playback:"won't play, crashes, lag, audio quality",
          downloads:"downloading, offline, saved music", catalog:"missing songs, search, recommendations, lyrics", billing:"price, charges, paywalls, premium-only controls",
          support:"contacting support, its response", other:"general praise/criticism, unrelated"},
  intent: {cancellation:"leaving or threatening to", complaint:"negative experience, incl. mixed", request:"wants a change, no failure", praise:"positive, no problem", unclear:"unrelated or meaningless"},
  severity: {1:"no problem: praise, request, unclear", 2:"annoyance or generic criticism", 3:"degraded or restricted, some use remains", 4:"core task clearly blocked", 5:"explicit financial, privacy or data harm"},
  sentiment: {"-1":"strongly negative", "-0.5":"negative", "0":"neutral or mixed", "0.5":"positive", "1":"strongly positive"}
};
const ORDER = {topic:null, intent:null, severity:["1","2","3","4","5"], sentiment:["-1","-0.5","0","0.5","1"]};
let rows = [], at = 0;
const $ = id => document.getElementById(id);
const complete = r => ["topic","intent","sentiment","severity","evidence_quote"].every(k => r[k]);

function status(message, error) { $("status").textContent = message; $("status").className = error ? "error" : "muted"; }

function render() {
  const r = rows[at];
  $("text").textContent = r.review_text;
  $("meta").textContent = `stars ${r.review_rating} · likes ${r.review_likes} · version ${r.app_version || "(missing)"} · ${r.review_timestamp}\n${r.review_id}`;
  for (const field of Object.keys(ORDER))
    for (const b of $(field).children) b.classList.toggle("on", b.dataset.value === r[field]);
  $("quote").textContent = r.evidence_quote;
  $("entities").value = r.entities; $("notes").value = r.notes;
  $("needs_review").checked = r.needs_review === "true"; $("ambiguous").checked = r.ambiguous === "true";
  const done = rows.filter(complete).length;
  $("count").textContent = `Review ${at + 1} of ${rows.length} · ${done} labeled`;
  [...$("dots").children].forEach((d, i) => { d.classList.toggle("done", complete(rows[i])); d.classList.toggle("current", i === at); });
  $("prev").disabled = at === 0; $("next").disabled = at === rows.length - 1;
}

async function save(change) {
  const r = rows[at], labels = {...r, ...change};
  labels.needs_review = labels.needs_review === true || labels.needs_review === "true";
  labels.ambiguous = labels.ambiguous === true || labels.ambiguous === "true";
  try {
    const response = await fetch("/api/save", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({review_id:r.review_id, labels})});
    const body = await response.json();
    if (!response.ok) { status(body.error, true); return; }
    Object.assign(r, body.row);
    status(body.complete ? "Saved · this review is complete" : "Saved");
  } catch (e) { status("Not saved: is the labeling program still running?", true); }
  render();
}

function go(i) { at = Math.max(0, Math.min(rows.length - 1, i)); status(""); render(); window.scrollTo(0, 0); }

async function start() {
  const data = await (await fetch("/api/rows")).json();
  rows = data.rows; $("output").textContent = data.output;
  ORDER.topic = data.topics; ORDER.intent = data.intents;
  for (const [field, values] of Object.entries(ORDER))
    for (const value of values) {
      const b = document.createElement("button");
      b.dataset.value = value; b.append(value);
      const s = document.createElement("small"); s.textContent = HELP[field][value]; b.append(s);
      b.onclick = () => save({[field]: rows[at][field] === value ? "" : value});
      $(field).append(b);
    }
  rows.forEach((_, i) => { const d = document.createElement("button"); d.textContent = i + 1; d.onclick = () => go(i); $("dots").append(d); });
  $("useSelection").onclick = () => {
    const selection = window.getSelection();
    if (!selection.rangeCount || !$("text").contains(selection.anchorNode) || !selection.toString()) return status("Select some words in the review first.", true);
    save({evidence_quote: selection.toString()});
  };
  $("useAll").onclick = () => save({evidence_quote: rows[at].review_text});
  $("clearQuote").onclick = () => save({evidence_quote: ""});
  $("entities").onchange = e => save({entities: e.target.value});
  $("notes").onchange = e => save({notes: e.target.value});
  $("needs_review").onchange = e => save({needs_review: e.target.checked});
  $("ambiguous").onchange = e => save({ambiguous: e.target.checked});
  $("prev").onclick = () => go(at - 1); $("next").onclick = () => go(at + 1);
  const firstOpen = rows.findIndex(r => !complete(r));
  go(firstOpen < 0 ? 0 : firstOpen);
}
start();
</script></body></html>
"""


class LoopbackServer(ThreadingHTTPServer):
    def server_bind(self):
        # Skip HTTPServer's reverse hostname lookup: it is unneeded on loopback and can raise a macOS network prompt.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path("data/golden_50_to_label.csv"))
    parser.add_argument("--output", type=Path, default=Path("evals/golden_50_labeled.csv"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if not args.output.exists():
        save_rows(args.output, read_rows(args.input))
    handler, rows = make_handler(args.output)
    server = LoopbackServer(("127.0.0.1", args.port), handler)
    print(f"{sum(map(is_complete, rows))} of {len(rows)} reviews labeled so far. Saving to {args.output}")
    print(f"Open http://localhost:{args.port} in a browser. Press Ctrl+C here to stop; progress is already saved.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
