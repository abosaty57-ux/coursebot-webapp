import os
import sqlite3
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "qa.db")


# ── DB helpers ────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS qa (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                q_no    TEXT UNIQUE NOT NULL,
                question TEXT NOT NULL,
                answer   TEXT NOT NULL,
                track    TEXT DEFAULT '',
                lecture  TEXT DEFAULT '',
                date_added TEXT DEFAULT ''
            )
        """)
        conn.commit()


# ── API endpoints ─────────────────────────────────────────────────────────────
@app.route("/api/qa")
def get_qa():
    track   = request.args.get("track", "").strip()
    lecture = request.args.get("lecture", "").strip()
    search  = request.args.get("search", "").strip()

    query  = "SELECT * FROM qa WHERE 1=1"
    params = []

    if track:
        query += " AND track = ?"
        params.append(track)
    if lecture:
        query += " AND lecture = ?"
        params.append(lecture)
    if search:
        query += " AND (question LIKE ? OR answer LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY id DESC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/filters")
def get_filters():
    with get_db() as conn:
        tracks   = [r[0] for r in conn.execute("SELECT DISTINCT track FROM qa WHERE track != '' ORDER BY track").fetchall()]
        lectures = [r[0] for r in conn.execute("SELECT DISTINCT lecture FROM qa WHERE lecture != '' ORDER BY lecture").fetchall()]
    return jsonify({"tracks": tracks, "lectures": lectures})


@app.route("/api/sync", methods=["POST"])
def sync_all():
    secret = request.headers.get("X-Secret")
    if secret != os.getenv("WEBAPP_SECRET", ""):
        return jsonify({"error": "unauthorized"}), 401
    _ensure_db()
    data = request.json
    rows = data.get("rows", [])
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM qa")
            for row in rows:
                conn.execute(
                    "INSERT INTO qa (q_no, question, answer, track, lecture, date_added) VALUES (?,?,?,?,?,?)",
                    (row["q_no"], row["question"], row["answer"],
                     row.get("track", ""), row.get("lecture", ""), row.get("date_added", ""))
                )
            conn.commit()
        return jsonify({"ok": True, "count": len(rows)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/add", methods=["POST"])
def add_qa():
    secret = request.headers.get("X-Secret")
    if secret != os.getenv("WEBAPP_SECRET", ""):
        return jsonify({"error": "unauthorized"}), 401
    _ensure_db()
    data = request.json
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO qa (q_no, question, answer, track, lecture, date_added) VALUES (?,?,?,?,?,?)",
                (data["q_no"], data["question"], data["answer"],
                 data.get("track", ""), data.get("lecture", ""), data.get("date_added", ""))
            )
            conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Mini App HTML ─────────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Q&A Reference</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--tg-theme-bg-color, #fff);
         color: var(--tg-theme-text-color, #000);
         padding: 12px; }
  h1 { font-size: 18px; font-weight: 600; margin-bottom: 12px; }
  .filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
  .filters input, .filters select {
    flex: 1; min-width: 120px; padding: 8px 10px; border-radius: 8px; font-size: 14px;
    border: 1px solid var(--tg-theme-hint-color, #ccc);
    background: var(--tg-theme-secondary-bg-color, #f5f5f5);
    color: var(--tg-theme-text-color, #000); }
  .filters button {
    padding: 8px 14px; border-radius: 8px; border: none; cursor: pointer; font-size: 14px;
    background: var(--tg-theme-button-color, #2ea6ff);
    color: var(--tg-theme-button-text-color, #fff); }
  .count { font-size: 13px; color: var(--tg-theme-hint-color, #888); margin-bottom: 10px; }
  .card { border-radius: 10px; padding: 12px 14px; margin-bottom: 10px;
          background: var(--tg-theme-secondary-bg-color, #f5f5f5);
          border-left: 4px solid var(--tg-theme-button-color, #2ea6ff); }
  .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
  .q-no { font-size: 12px; font-weight: 600; color: var(--tg-theme-button-color, #2ea6ff); }
  .tags { display: flex; gap: 5px; flex-wrap: wrap; }
  .tag { font-size: 11px; padding: 2px 7px; border-radius: 99px;
         background: var(--tg-theme-bg-color, #e8f4ff);
         color: var(--tg-theme-hint-color, #555); border: 1px solid var(--tg-theme-hint-color, #ccc); }
  .question { font-size: 14px; font-weight: 500; margin-bottom: 6px; }
  .answer { font-size: 13px; color: var(--tg-theme-hint-color, #555); line-height: 1.5; }
  .answer.collapsed { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .toggle { font-size: 12px; color: var(--tg-theme-button-color, #2ea6ff); cursor: pointer; margin-top: 4px; display: inline-block; }
  .empty { text-align: center; padding: 40px 20px; color: var(--tg-theme-hint-color, #888); font-size: 14px; }
  .loading { text-align: center; padding: 40px; color: var(--tg-theme-hint-color, #888); }
</style>
</head>
<body>
<h1>📚 Q&A Reference</h1>
<div class="filters">
  <input type="text" id="search" placeholder="🔍 Search questions or answers…" oninput="debounceLoad()">
  <select id="track" onchange="loadQA()"><option value="">All Tracks</option></select>
  <select id="lecture" onchange="loadQA()"><option value="">All Lectures</option></select>
  <button onclick="clearFilters()">✕ Clear</button>
</div>
<div class="count" id="count"></div>
<div id="results"><div class="loading">Loading…</div></div>

<script>
let debounceTimer;
function debounceLoad() { clearTimeout(debounceTimer); debounceTimer = setTimeout(loadQA, 400); }

async function loadFilters() {
  const res = await fetch('/api/filters');
  const { tracks, lectures } = await res.json();
  const ts = document.getElementById('track');
  const ls = document.getElementById('lecture');
  tracks.forEach(t => { const o = document.createElement('option'); o.value = t; o.textContent = t; ts.appendChild(o); });
  lectures.forEach(l => { const o = document.createElement('option'); o.value = l; o.textContent = l; ls.appendChild(o); });
}

async function loadQA() {
  const search  = document.getElementById('search').value.trim();
  const track   = document.getElementById('track').value;
  const lecture = document.getElementById('lecture').value;
  const params  = new URLSearchParams();
  if (search)  params.set('search', search);
  if (track)   params.set('track', track);
  if (lecture) params.set('lecture', lecture);

  document.getElementById('results').innerHTML = '<div class="loading">Loading…</div>';
  const res  = await fetch('/api/qa?' + params.toString());
  const data = await res.json();
  render(data);
}

function render(data) {
  document.getElementById('count').textContent = data.length + ' result' + (data.length !== 1 ? 's' : '');
  if (!data.length) {
    document.getElementById('results').innerHTML = '<div class="empty">No results found 🤷</div>';
    return;
  }
  document.getElementById('results').innerHTML = data.map((q, i) => `
    <div class="card">
      <div class="card-header">
        <span class="q-no">${q.q_no}</span>
        <div class="tags">
          ${q.track   ? '<span class="tag">📚 ' + q.track   + '</span>' : ''}
          ${q.lecture ? '<span class="tag">📖 ' + q.lecture + '</span>' : ''}
        </div>
      </div>
      <div class="question">❓ ${q.question}</div>
      <div class="answer collapsed" id="ans-${i}">💡 ${q.answer}</div>
      <span class="toggle" onclick="toggle(${i})">Show more ▼</span>
    </div>
  `).join('');
}

function toggle(i) {
  const el = document.getElementById('ans-' + i);
  const btn = el.nextElementSibling;
  if (el.classList.contains('collapsed')) {
    el.classList.remove('collapsed'); btn.textContent = 'Show less ▲';
  } else {
    el.classList.add('collapsed'); btn.textContent = 'Show more ▼';
  }
}

function clearFilters() {
  document.getElementById('search').value = '';
  document.getElementById('track').value = '';
  document.getElementById('lecture').value = '';
  loadQA();
}

loadFilters();
loadQA();
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
