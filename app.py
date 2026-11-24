"""
DDS Creations Forum - backend (Flask + SQLite, standard library only besides Flask).

Run locally:   python app.py            -> http://127.0.0.1:5000
Environment:   VV_DB_PATH   path to the SQLite file   (default: ./ddscreations.db)
               VV_ADMIN     username that becomes admin (default: first user to register)
               PORT         port for local run         (default: 5000)
"""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from functools import wraps

from flask import Flask, g, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("VV_DB_PATH", os.path.join(BASE_DIR, "ddscreations.db"))
STATIC_DIR = os.path.join(BASE_DIR, "static")
SESSION_DAYS = 30
PAGE_SIZE = 20

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024  # 256 KB per request

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
    display_name TEXT NOT NULL,
    headline TEXT DEFAULT '',
    role TEXT NOT NULL DEFAULT 'member',      -- member | pro | admin
    pw_hash TEXT NOT NULL,
    pw_salt TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    icon TEXT NOT NULL DEFAULT '#',
    sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    locked INTEGER NOT NULL DEFAULT 0,
    views INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_activity INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    accepted INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS votes (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_type TEXT NOT NULL,                -- thread | post
    target_id INTEGER NOT NULL,
    value INTEGER NOT NULL,                   -- 1 or -1
    PRIMARY KEY (user_id, target_type, target_id)
);
CREATE INDEX IF NOT EXISTS idx_threads_cat ON threads(category_id, last_activity);
CREATE INDEX IF NOT EXISTS idx_posts_thread ON posts(thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_votes_target ON votes(target_type, target_id);
"""

DEFAULT_CATEGORIES = [
    ("resume-review", "Resume Review", "Post your resume (remove phone/address) and get feedback from hiring pros.", "R", 1),
    ("interview-prep", "Interview Prep", "Questions you were asked, how to answer, mock-interview partners.", "I", 2),
    ("salary-offers", "Salary & Offers", "Is this offer fair? Negotiation, CTC breakdowns, notice periods.", "₹", 3),
    ("career-switch", "Career Switch", "Moving domains, upskilling, freshers and comebacks after a break.", "S", 4),
    ("ask-hr", "Ask an HR Pro", "Anything about policies, background checks, PF, relieving letters.", "H", 5),
    ("referrals", "Referrals & Openings", "Genuine openings and referral offers. No paid-job scams.", "J", 6),
]


# ---------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    if db.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO categories (slug, name, description, icon, sort) VALUES (?,?,?,?,?)",
            DEFAULT_CATEGORIES,
        )
    db.commit()
    db.close()


def now():
    return int(time.time())


# ---------------------------------------------------------------- security helpers
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return digest, salt


def verify_password(password, digest, salt):
    return hmac.compare_digest(hash_password(password, salt)[0], digest)


_rate = defaultdict(deque)


def rate_limited(key, limit, window):
    """Return True when `key` has made more than `limit` calls in `window` seconds."""
    q = _rate[key]
    t = time.time()
    while q and q[0] < t - window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(t)
    return False


def client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()


def current_user():
    if "user" in g:
        return g.user
    g.user = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        row = get_db().execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND s.expires_at > ?",
            (auth[7:], now()),
        ).fetchone()
        g.user = row
    return g.user


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            return err("Please log in first.", 401)
        return fn(*a, **kw)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        u = current_user()
        if not u or u["role"] != "admin":
            return err("Admins only.", 403)
        return fn(*a, **kw)
    return wrapper


def err(msg, code=400):
    return jsonify({"error": msg}), code


def body():
    return request.get_json(silent=True) or {}


def public_user(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "headline": row["headline"],
        "role": row["role"],
        "created_at": row["created_at"],
    }


def score_of(target_type, target_id):
    return get_db().execute(
        "SELECT COALESCE(SUM(value),0) FROM votes WHERE target_type=? AND target_id=?",
        (target_type, target_id),
    ).fetchone()[0]


def my_vote(target_type, target_id):
    u = current_user()
    if not u:
        return 0
    r = get_db().execute(
        "SELECT value FROM votes WHERE user_id=? AND target_type=? AND target_id=?",
        (u["id"], target_type, target_id),
    ).fetchone()
    return r["value"] if r else 0


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp


# ---------------------------------------------------------------- auth
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,24}$")


@app.post("/api/auth/register")
def register():
    if rate_limited(("reg", client_ip()), 5, 3600):
        return err("Too many sign-ups from this network. Try again later.", 429)
    d = body()
    username = (d.get("username") or "").strip()
    password = d.get("password") or ""
    display = (d.get("display_name") or username).strip()[:40]
    if not USERNAME_RE.match(username):
        return err("Username must be 3-24 letters, numbers or underscores.")
    if len(password) < 8:
        return err("Password must be at least 8 characters.")
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        return err("That username is taken.")
    is_first = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    admin_name = os.environ.get("VV_ADMIN")
    role = "admin" if (admin_name and admin_name.lower() == username.lower()) or (not admin_name and is_first) else "member"
    digest, salt = hash_password(password)
    cur = db.execute(
        "INSERT INTO users (username, display_name, role, pw_hash, pw_salt, created_at) VALUES (?,?,?,?,?,?)",
        (username, display or username, role, digest, salt, now()),
    )
    db.commit()
    return _new_session(cur.lastrowid)


@app.post("/api/auth/login")
def login():
    if rate_limited(("login", client_ip()), 10, 600):
        return err("Too many login attempts. Wait 10 minutes.", 429)
    d = body()
    row = get_db().execute("SELECT * FROM users WHERE username=?", ((d.get("username") or "").strip(),)).fetchone()
    if not row or not verify_password(d.get("password") or "", row["pw_hash"], row["pw_salt"]):
        return err("Wrong username or password.", 401)
    return _new_session(row["id"])


def _new_session(user_id):
    db = get_db()
    token = secrets.token_urlsafe(32)
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
    db.execute("INSERT INTO sessions VALUES (?,?,?)", (token, user_id, now() + SESSION_DAYS * 86400))
    db.commit()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return jsonify({"token": token, "user": public_user(user)})


@app.post("/api/auth/logout")
@login_required
def logout():
    db = get_db()
    db.execute("DELETE FROM sessions WHERE token=?", (request.headers["Authorization"][7:],))
    db.commit()
    return jsonify({"ok": True})


@app.get("/api/me")
def me():
    u = current_user()
    return jsonify({"user": public_user(u) if u else None})


@app.patch("/api/me")
@login_required
def update_me():
    d = body()
    display = (d.get("display_name") or current_user()["display_name"]).strip()[:40]
    headline = (d.get("headline") or "").strip()[:100]
    db = get_db()
    db.execute("UPDATE users SET display_name=?, headline=? WHERE id=?", (display, headline, current_user()["id"]))
    db.commit()
    return jsonify({"user": public_user(db.execute("SELECT * FROM users WHERE id=?", (current_user()["id"],)).fetchone())})


# ---------------------------------------------------------------- categories & threads
@app.get("/api/categories")
def categories():
    rows = get_db().execute(
        "SELECT c.*, COUNT(t.id) AS thread_count, MAX(t.last_activity) AS last_activity "
        "FROM categories c LEFT JOIN threads t ON t.category_id = c.id "
        "GROUP BY c.id ORDER BY c.sort"
    ).fetchall()
    return jsonify({"categories": [dict(r) for r in rows]})


@app.get("/api/stats")
def stats():
    db = get_db()
    return jsonify({
        "members": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "threads": db.execute("SELECT COUNT(*) FROM threads").fetchone()[0],
        "replies": db.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
    })


THREAD_LIST_SQL = """
SELECT t.id, t.title, substr(t.body, 1, 220) AS excerpt, t.pinned, t.locked, t.views,
       t.created_at, t.last_activity, c.slug AS category_slug, c.name AS category_name,
       u.username, u.display_name, u.role,
       (SELECT COUNT(*) FROM posts p WHERE p.thread_id = t.id) AS reply_count,
       (SELECT COALESCE(SUM(value),0) FROM votes v WHERE v.target_type='thread' AND v.target_id=t.id) AS score,
       (SELECT COUNT(*) FROM posts p WHERE p.thread_id = t.id AND p.accepted = 1) AS solved
FROM threads t
JOIN categories c ON c.id = t.category_id
JOIN users u ON u.id = t.user_id
"""


@app.get("/api/threads")
def list_threads():
    where, params = [], []
    if request.args.get("category"):
        where.append("c.slug = ?")
        params.append(request.args["category"])
    if request.args.get("user"):
        where.append("u.username = ?")
        params.append(request.args["user"])
    q = (request.args.get("q") or "").strip()
    if q:
        where.append("(t.title LIKE ? OR t.body LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    sort = {
        "new": "t.created_at DESC",
        "top": "score DESC, t.created_at DESC",
        "unanswered": "reply_count ASC, t.created_at DESC",
    }.get(request.args.get("sort"), "t.pinned DESC, t.last_activity DESC")
    page = max(1, request.args.get("page", 1, type=int))
    sql = THREAD_LIST_SQL + (" WHERE " + " AND ".join(where) if where else "")
    total = get_db().execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
    rows = get_db().execute(
        f"{sql} ORDER BY {sort} LIMIT ? OFFSET ?", params + [PAGE_SIZE, (page - 1) * PAGE_SIZE]
    ).fetchall()
    return jsonify({"threads": [dict(r) for r in rows], "page": page,
                    "pages": max(1, -(-total // PAGE_SIZE)), "total": total})


@app.post("/api/threads")
@login_required
def create_thread():
    u = current_user()
    if rate_limited(("post", u["id"]), 5, 600):
        return err("You're posting fast. Wait a few minutes.", 429)
    d = body()
    title = (d.get("title") or "").strip()
    text = (d.get("body") or "").strip()
    if not 8 <= len(title) <= 150:
        return err("Title should be 8-150 characters.")
    if not 20 <= len(text) <= 20000:
        return err("Post body should be 20-20,000 characters.")
    db = get_db()
    cat = db.execute("SELECT id FROM categories WHERE slug=?", (d.get("category") or "",)).fetchone()
    if not cat:
        return err("Pick a valid category.")
    t = now()
    cur = db.execute(
        "INSERT INTO threads (category_id, user_id, title, body, created_at, last_activity) VALUES (?,?,?,?,?,?)",
        (cat["id"], u["id"], title, text, t, t),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.get("/api/threads/<int:tid>")
def get_thread(tid):
    db = get_db()
    if not rate_limited(("view", client_ip(), tid), 1, 3600):
        db.execute("UPDATE threads SET views = views + 1 WHERE id=?", (tid,))
        db.commit()
    row = db.execute(THREAD_LIST_SQL.replace("substr(t.body, 1, 220)", "t.body") + " WHERE t.id = ?", (tid,)).fetchone()
    if not row:
        return err("Thread not found.", 404)
    thread = dict(row)
    thread["body_full"] = thread.pop("excerpt")
    thread["my_vote"] = my_vote("thread", tid)
    posts = db.execute(
        "SELECT p.id, p.body, p.accepted, p.created_at, u.username, u.display_name, u.role, u.headline "
        "FROM posts p JOIN users u ON u.id = p.user_id WHERE p.thread_id = ? ORDER BY p.accepted DESC, p.created_at",
        (tid,),
    ).fetchall()
    out = []
    for p in posts:
        item = dict(p)
        item["score"] = score_of("post", p["id"])
        item["my_vote"] = my_vote("post", p["id"])
        out.append(item)
    return jsonify({"thread": thread, "posts": out})


@app.post("/api/threads/<int:tid>/posts")
@login_required
def reply(tid):
    u = current_user()
    if rate_limited(("post", u["id"]), 10, 600):
        return err("You're replying fast. Wait a few minutes.", 429)
    db = get_db()
    th = db.execute("SELECT locked FROM threads WHERE id=?", (tid,)).fetchone()
    if not th:
        return err("Thread not found.", 404)
    if th["locked"] and u["role"] != "admin":
        return err("This thread is locked.", 403)
    text = (body().get("body") or "").strip()
    if not 2 <= len(text) <= 10000:
        return err("Reply should be 2-10,000 characters.")
    cur = db.execute("INSERT INTO posts (thread_id, user_id, body, created_at) VALUES (?,?,?,?)",
                     (tid, u["id"], text, now()))
    db.execute("UPDATE threads SET last_activity=? WHERE id=?", (now(), tid))
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.post("/api/posts/<int:pid>/accept")
@login_required
def accept(pid):
    """Thread author (or admin) marks the reply that solved their question."""
    db = get_db()
    row = db.execute("SELECT p.thread_id, t.user_id AS owner FROM posts p JOIN threads t ON t.id=p.thread_id WHERE p.id=?",
                     (pid,)).fetchone()
    if not row:
        return err("Reply not found.", 404)
    u = current_user()
    if u["id"] != row["owner"] and u["role"] != "admin":
        return err("Only the person who asked can accept an answer.", 403)
    db.execute("UPDATE posts SET accepted = 0 WHERE thread_id=?", (row["thread_id"],))
    db.execute("UPDATE posts SET accepted = 1 WHERE id=?", (pid,))
    db.commit()
    return jsonify({"ok": True})


@app.post("/api/vote")
@login_required
def vote():
    d = body()
    ttype, tid, val = d.get("target_type"), d.get("target_id"), d.get("value")
    if ttype not in ("thread", "post") or not isinstance(tid, int) or val not in (1, -1, 0):
        return err("Bad vote.")
    db = get_db()
    table = "threads" if ttype == "thread" else "posts"
    if not db.execute(f"SELECT 1 FROM {table} WHERE id=?", (tid,)).fetchone():
        return err("Not found.", 404)
    uid = current_user()["id"]
    if val == 0:
        db.execute("DELETE FROM votes WHERE user_id=? AND target_type=? AND target_id=?", (uid, ttype, tid))
    else:
        db.execute(
            "INSERT INTO votes VALUES (?,?,?,?) ON CONFLICT(user_id, target_type, target_id) DO UPDATE SET value=excluded.value",
            (uid, ttype, tid, val),
        )
    db.commit()
    return jsonify({"score": score_of(ttype, tid), "my_vote": val})


@app.delete("/api/threads/<int:tid>")
@login_required
def delete_thread(tid):
    db = get_db()
    row = db.execute("SELECT user_id FROM threads WHERE id=?", (tid,)).fetchone()
    if not row:
        return err("Not found.", 404)
    u = current_user()
    if row["user_id"] != u["id"] and u["role"] != "admin":
        return err("You can only delete your own threads.", 403)
    db.execute("DELETE FROM votes WHERE target_type='post' AND target_id IN (SELECT id FROM posts WHERE thread_id=?)", (tid,))
    db.execute("DELETE FROM votes WHERE target_type='thread' AND target_id=?", (tid,))
    db.execute("DELETE FROM posts WHERE thread_id=?", (tid,))
    db.execute("DELETE FROM threads WHERE id=?", (tid,))
    db.commit()
    return jsonify({"ok": True})


@app.delete("/api/posts/<int:pid>")
@login_required
def delete_post(pid):
    db = get_db()
    row = db.execute("SELECT user_id FROM posts WHERE id=?", (pid,)).fetchone()
    if not row:
        return err("Not found.", 404)
    u = current_user()
    if row["user_id"] != u["id"] and u["role"] != "admin":
        return err("You can only delete your own replies.", 403)
    db.execute("DELETE FROM votes WHERE target_type='post' AND target_id=?", (pid,))
    db.execute("DELETE FROM posts WHERE id=?", (pid,))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------- admin
@app.post("/api/threads/<int:tid>/<action>")
@admin_required
def moderate(tid, action):
    col = {"pin": ("pinned", 1), "unpin": ("pinned", 0), "lock": ("locked", 1), "unlock": ("locked", 0)}.get(action)
    if not col:
        return err("Unknown action.", 404)
    db = get_db()
    db.execute(f"UPDATE threads SET {col[0]}=? WHERE id=?", (col[1], tid))
    db.commit()
    return jsonify({"ok": True})


@app.post("/api/users/<username>/role")
@admin_required
def set_role(username):
    role = body().get("role")
    if role not in ("member", "pro", "admin"):
        return err("Role must be member, pro or admin.")
    db = get_db()
    db.execute("UPDATE users SET role=? WHERE username=?", (role, username))
    db.commit()
    return jsonify({"ok": True})


@app.get("/api/users/<username>")
def user_profile(username):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        return err("User not found.", 404)
    stats = {
        "threads": db.execute("SELECT COUNT(*) FROM threads WHERE user_id=?", (row["id"],)).fetchone()[0],
        "replies": db.execute("SELECT COUNT(*) FROM posts WHERE user_id=?", (row["id"],)).fetchone()[0],
        "accepted": db.execute("SELECT COUNT(*) FROM posts WHERE user_id=? AND accepted=1", (row["id"],)).fetchone()[0],
        "reputation": db.execute(
            "SELECT COALESCE(SUM(v.value),0) FROM votes v "
            "LEFT JOIN posts p ON v.target_type='post' AND p.id=v.target_id "
            "LEFT JOIN threads t ON v.target_type='thread' AND t.id=v.target_id "
            "WHERE p.user_id=? OR t.user_id=?", (row["id"], row["id"])).fetchone()[0],
    }
    return jsonify({"user": public_user(row), "stats": stats})


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "time": now()})


# ---------------------------------------------------------------- frontend
@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/static/<path:name>")
def static_files(name):
    return send_from_directory(STATIC_DIR, name)


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
