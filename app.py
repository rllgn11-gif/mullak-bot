# =========================
# 🔥 IMPORTS
# =========================
import os, json, time, jwt, requests, hmac, hashlib
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import telebot
from functools import wraps
from collections import defaultdict
import threading

app = Flask(__name__)

# =========================
# 🔐 CONFIG
# =========================
BOT_TOKEN  = os.environ.get("BOT_TOKEN","")
JWT_SECRET = os.environ.get("JWT_SECRET","SUPER_SECRET_12345678901234567890")
SUPABASE_URL = os.environ.get("SUPABASE_URL","")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY","")
ADMIN_ID = os.environ.get("ADMIN_ID","")

bot = telebot.TeleBot(BOT_TOKEN)

# =========================
# 🚦 RATE LIMIT
# =========================
rate_data = defaultdict(list)
lock = threading.Lock()

def rate_limit(max_calls, period):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ip = request.remote_addr
            key = f"{f.__name__}:{ip}"
            now = time.time()

            with lock:
                calls = [t for t in rate_data[key] if now - t < period]
                if len(calls) >= max_calls:
                    return jsonify({"error":"Too many requests"}),429
                calls.append(now)
                rate_data[key] = calls

            return f(*args, **kwargs)
        return wrapped
    return decorator

# =========================
# 🛠️ SUPABASE
# =========================
def headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

def sb(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"

def select(table, filters=None):
    r = requests.get(sb(table), headers=headers(), params=filters or {})
    return r.json()

def insert(table,data):
    r = requests.post(sb(table), headers=headers(), json=data)
    return r.json()

def update(table, filters, data):
    requests.patch(sb(table), headers=headers(), params=filters, json=data)

# =========================
# 🔐 JWT
# =========================
def create_token(uid):
    return jwt.encode({
        "user_id": uid,
        "exp": int(time.time()) + 604800
    }, JWT_SECRET, algorithm="HS256")

def verify_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except:
        return None

def auth_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        token = request.headers.get("Authorization","").replace("Bearer ","")
        user = verify_token(token)
        if not user:
            return jsonify({"error":"unauthorized"}),401
        return f(user,*args,**kwargs)
    return wrap

# =========================
# 📊 SESSION TRACK
# =========================
@app.route("/api/session/start", methods=["POST"])
def start_session():
    uid = request.json.get("user_id")
    session = insert("sessions", {
        "user_id": uid,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": 0
    })
    return jsonify(session)

@app.route("/api/session/end", methods=["POST"])
def end_session():
    d = request.json or {}
    sid = d.get("session_id")
    duration = int(d.get("duration",0))

    if sid:
        update("sessions",
               {"id":f"eq.{sid}"},
               {"duration_seconds":duration,
                "ended_at": datetime.now(timezone.utc).isoformat()})
    return "",204

# =========================
# 📊 ANALYTICS (BOT ONLY)
# =========================
def analytics_text(sessions):
    if not sessions:
        return "📊 لا يوجد بيانات"

    users = set(s["user_id"] for s in sessions)
    total = len(sessions)

    avg = int(sum(s.get("duration_seconds",0) for s in sessions)/len(sessions))
    m = avg//60
    s = avg%60

    return f"""
📊 إحصائيات الاستخدام
━━━━━━━━━━━━━━
👥 المستخدمون: {len(users)}
📱 الجلسات: {total}
⏱️ المتوسط: {m}:{s:02d}
"""

@bot.message_handler(commands=["stats"])
def stats(msg):
    if str(msg.from_user.id) != str(ADMIN_ID):
        return

    sessions = select("sessions")
    bot.send_message(msg.chat.id, analytics_text(sessions))

# =========================
# 📄 PDF ENDPOINTS
# =========================

def html_wrapper(title, body):
    return f"""
    <html dir="rtl">
    <head><meta charset="utf-8">
    <style>
    body{{font-family:Arial;padding:20px}}
    h1{{color:#333}}
    table{{width:100%;border-collapse:collapse}}
    td,th{{border:1px solid #ccc;padding:8px}}
    </style>
    </head>
    <body>
    <h1>{title}</h1>
    {body}
    <script>window.print()</script>
    </body>
    </html>
    """

# =========================
# 🧑‍💼 PDF المستأجرين
# =========================
@app.route("/api/pdf/tenants")
@auth_required
def pdf_tenants(user):
    data = select("tenants", {"user_id":f"eq.{user['user_id']}"})

    rows = "".join([f"<tr><td>{t['name']}</td><td>{t['rent']}</td></tr>" for t in data])

    return Response(html_wrapper("المستأجرين", f"<table><tr><th>الاسم</th><th>الإيجار</th></tr>{rows}</table>"),
                    mimetype="text/html")

# =========================
# 🏢 PDF العقارات
# =========================
@app.route("/api/pdf/properties")
@auth_required
def pdf_props(user):
    data = select("properties", {"user_id":f"eq.{user['user_id']}"})

    rows = "".join([f"<tr><td>{p['name']}</td><td>{p['location']}</td></tr>" for p in data])

    return Response(html_wrapper("العقارات", f"<table><tr><th>الاسم</th><th>الموقع</th></tr>{rows}</table>"),
                    mimetype="text/html")

# =========================
# 💸 PDF المصروفات
# =========================
@app.route("/api/pdf/expenses")
@auth_required
def pdf_expenses(user):
    data = select("expenses", {"user_id":f"eq.{user['user_id']}"})

    rows = "".join([f"<tr><td>{e['category']}</td><td>{e['amount']}</td></tr>" for e in data])

    return Response(html_wrapper("المصروفات", f"<table><tr><th>التصنيف</th><th>المبلغ</th></tr>{rows}</table>"),
                    mimetype="text/html")

# =========================
# 🤖 WEBHOOK
# =========================
@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.data.decode())])
    return "",200

# =========================
# 🚀 RUN
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
