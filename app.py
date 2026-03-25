# =========================
# 🔥 IMPORTS
# =========================
import os, json, time, jwt, requests, hmac, hashlib
from datetime import datetime, timezone
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
# 🌐 CORS (مهم لحل 404 OPTIONS)
# =========================
CORS(app)

@app.route('/<path:path>', methods=['OPTIONS'])
def options_handler(path):
    return '', 200

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
# 🔐 AUTH (مهم جدًا)
# =========================
@app.route("/auth", methods=["POST"])
def auth():
    data = request.json or {}
    user_id = data.get("initData")  # نستخدمه كمعرف مؤقت

    if not user_id:
        return jsonify({"error":"invalid"}),400

    token = create_token(user_id)

    session = insert("sessions", {
        "user_id": user_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": 0
    })

    return jsonify({
        "token": token,
        "session_id": session[0]["id"] if isinstance(session,list) else ""
    })

# =========================
# 📊 STATS
# =========================
@app.route("/api/stats", methods=["GET"])
@auth_required
def stats_api(user):
    sessions = select("sessions", {"user_id":f"eq.{user['user_id']}"})

    total = len(sessions)
    avg = int(sum(s.get("duration_seconds",0) for s in sessions)/len(sessions)) if sessions else 0

    return jsonify({
        "props":0,
        "tenants":0,
        "income":0,
        "expenses":0,
        "net":0
    })

# =========================
# 📊 SESSION END
# =========================
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
# 📄 PDF
# =========================
def html(title, body):
    return f"""
    <html dir="rtl">
    <head><meta charset="utf-8">
    <style>
    body{{font-family:Arial;padding:20px}}
    table{{width:100%;border-collapse:collapse}}
    td,th{{border:1px solid #ccc;padding:8px}}
    </style>
    </head>
    <body>
    <h2>{title}</h2>
    {body}
    <script>window.print()</script>
    </body>
    </html>
    """

@app.route("/api/pdf/tenants")
@auth_required
def pdf_tenants(user):
    data = select("tenants", {"user_id":f"eq.{user['user_id']}"})
    rows = "".join([f"<tr><td>{t['name']}</td><td>{t['rent']}</td></tr>" for t in data])
    return Response(html("المستأجرين", f"<table><tr><th>الاسم</th><th>الإيجار</th></tr>{rows}</table>"), mimetype="text/html")

@app.route("/api/pdf/properties")
@auth_required
def pdf_props(user):
    data = select("properties", {"user_id":f"eq.{user['user_id']}"})
    rows = "".join([f"<tr><td>{p['name']}</td><td>{p['location']}</td></tr>" for p in data])
    return Response(html("العقارات", f"<table><tr><th>الاسم</th><th>الموقع</th></tr>{rows}</table>"), mimetype="text/html")

@app.route("/api/pdf/expenses")
@auth_required
def pdf_expenses(user):
    data = select("expenses", {"user_id":f"eq.{user['user_id']}"})
    rows = "".join([f"<tr><td>{e['category']}</td><td>{e['amount']}</td></tr>" for e in data])
    return Response(html("المصروفات", f"<table><tr><th>التصنيف</th><th>المبلغ</th></tr>{rows}</table>"), mimetype="text/html")

# =========================
# 🤖 BOT
# =========================
@bot.message_handler(commands=["stats"])
def stats(msg):
    if str(msg.from_user.id) != str(ADMIN_ID):
        return
    sessions = select("sessions")
    bot.send_message(msg.chat.id, f"📊 عدد الجلسات: {len(sessions)}")

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.data.decode())])
    return "",200

# =========================
# 🚀 RUN
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
