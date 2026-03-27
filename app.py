import os
import json
import time
import jwt
import requests
import hmac
import hashlib
import threading
import base64
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from functools import wraps
from collections import defaultdict
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# ============================================================
# 🔑 CONFIG
# ============================================================
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
JWT_SECRET   = os.environ.get("JWT_SECRET", "mullak_secret_2024")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
ADMIN_ID     = os.environ.get("ADMIN_ID", "")
MINI_APP_URL = os.environ.get("MINI_APP_URL", "https://rllgn11-gif.github.io/mullak-bot/")
RAILWAY_URL  = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip().rstrip("/")

# 💳 Geidea Checkout (KSA)
GEIDEA_PUBLIC_KEY   = os.environ.get("GEIDEA_PUBLIC_KEY", "").strip()
GEIDEA_API_PASSWORD = os.environ.get("GEIDEA_API_PASSWORD", "").strip()
GEIDEA_BASE_URL     = os.environ.get("GEIDEA_BASE_URL", "https://api.ksamerchant.geidea.net").strip().rstrip("/")
GEIDEA_HPP_BASE     = os.environ.get("GEIDEA_HPP_BASE", "https://www.ksamerchant.geidea.net/hpp/checkout/")

# 💰 الاشتراك
PLAN_MONTHLY_AMOUNT = float(os.environ.get("PLAN_MONTHLY_AMOUNT", "29"))
PLAN_MONTHLY_DAYS   = 30
TRIAL_DAYS          = 7

ALLOWED_ORIGINS = [
    "https://rllgn11-gif.github.io",
    "https://web.telegram.org",
    "https://k.tgfiles.com",
]
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=False)

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

# ============================================================
# 🌐 CORS
# ============================================================
@app.after_request
def add_cors(response):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"]  = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response

@app.route("/<path:path>", methods=["OPTIONS"])
def options(path):
    return "", 200

# ============================================================
# 🚦 Rate Limiter
# ============================================================
_rate_data = defaultdict(list)
_rate_lock = threading.Lock()

def rate_limit(max_calls: int, period: int):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ip  = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
            key = f"{f.__name__}:{ip}"
            now = time.time()
            with _rate_lock:
                calls = [t for t in _rate_data[key] if now - t < period]
                if len(calls) >= max_calls:
                    return jsonify({"error": "طلبات كثيرة — انتظر قليلاً"}), 429
                calls.append(now)
                _rate_data[key] = calls
            return f(*args, **kwargs)
        return wrapped
    return decorator

# ============================================================
# 🛠️ Supabase
# ============================================================
def sb_headers():
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation"
    }

def sb_select(table, filters=None, select="*", order=None):
    params = {"select": select}
    if filters: params.update(filters)
    if order:   params["order"] = order
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=sb_headers(), params=params)
    r.raise_for_status()
    return r.json()

def sb_insert(table, data):
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=sb_headers(), json=data)
    r.raise_for_status()
    result = r.json()
    return result[0] if isinstance(result, list) else result

def sb_update(table, filters, data):
    r = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}", headers=sb_headers(), params=filters, json=data)
    r.raise_for_status()
    result = r.json()
    return result[0] if isinstance(result, list) and result else {"ok": True}

def sb_delete(table, filters):
    r = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}", headers=sb_headers(), params=filters)
    r.raise_for_status()
    return {"ok": True}

# ============================================================
# 🔐 Telegram HMAC
# ============================================================
def verify_telegram_init_data(init_data: str):
    try:
        decoded   = unquote(init_data)
        data_dict = {}
        for part in decoded.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                data_dict[k] = v
        hash_received = data_dict.pop("hash", None)
        if not hash_received:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data_dict.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected   = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, hash_received):
            return None
        return json.loads(data_dict.get("user", "{}"))
    except Exception as e:
        print(f"Telegram verify error: {e}")
        return None

# ============================================================
# 🎫 JWT
# ============================================================
def create_jwt(user_id, first_name):
    return jwt.encode({
        "user_id":    str(user_id),
        "first_name": first_name,
        "iat": int(time.time()),
        "exp": int(time.time()) + 60 * 60 * 24 * 7
    }, JWT_SECRET, algorithm="HS256")

def verify_jwt_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except:
        return None

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "غير مصرح"}), 401
        user = verify_jwt_token(auth[7:])
        if not user:
            return jsonify({"error": "انتهت الجلسة — أعد فتح التطبيق"}), 401
        return f(user, *args, **kwargs)
    return decorated

# ============================================================
# 💳 نظام الاشتراك
# ============================================================
def get_subscription(user_id: str):
    try:
        rows = sb_select("subscriptions", {"user_id": f"eq.{user_id}"})
        return rows[0] if rows else None
    except Exception:
        return None

def sub_is_active(user_id: str):
    sub = get_subscription(user_id)
    if not sub or not sub.get("expires_at"):
        return False
    try:
        exp_dt = datetime.fromisoformat(sub["expires_at"].replace("Z", "+00:00"))
        return datetime.now(timezone.utc) < exp_dt
    except Exception:
        return False

def sub_days_left(user_id: str):
    sub = get_subscription(user_id)
    if not sub or not sub.get("expires_at"):
        return 0
    try:
        exp_dt = datetime.fromisoformat(sub["expires_at"].replace("Z", "+00:00"))
        return max(0, (exp_dt - datetime.now(timezone.utc)).days)
    except Exception:
        return 0

def require_write(f):
    @wraps(f)
    def decorated(user, *args, **kwargs):
        if not sub_is_active(user["user_id"]):
            return jsonify({"error": "اشتراكك منتهٍ — جدّد للمتابعة", "code": "SUB_EXPIRED"}), 403
        return f(user, *args, **kwargs)
    return decorated

# ============================================================
# 💳 Geidea Helpers
# ============================================================
def geidea_auth():
    return (GEIDEA_PUBLIC_KEY, GEIDEA_API_PASSWORD)

def geidea_signature(amount: float, currency: str, merchant_ref: str, timestamp: str) -> str:
    msg = f"{GEIDEA_PUBLIC_KEY}{amount:.2f}{currency}{merchant_ref}{timestamp}"
    sig = hmac.new(
        GEIDEA_API_PASSWORD.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256
    ).digest()
    return base64.b64encode(sig).decode("utf-8")

def extract_checkout_url(resp_data: dict) -> str:
    if not isinstance(resp_data, dict):
        return ""
    candidates = [
        resp_data.get("paymentUrl"),
        resp_data.get("redirectUrl"),
        resp_data.get("checkoutUrl"),
        (resp_data.get("session") or {}).get("paymentUrl"),
        (resp_data.get("session") or {}).get("redirectUrl"),
        (resp_data.get("session") or {}).get("url"),
    ]
    for url in candidates:
        if isinstance(url, str) and url.strip():
            return url.strip()
    session_id = (resp_data.get("session") or {}).get("id")
    if session_id:
        hpp_base = GEIDEA_HPP_BASE.rstrip("/")
        return f"{hpp_base}/?{session_id}"
    return ""

# ============================================================
# 🔐 Auth
# ============================================================
@app.route("/auth", methods=["POST"])
@rate_limit(max_calls=10, period=60)
def auth():
    data      = request.json or {}
    init_data = data.get("initData", "").strip()

    if not init_data or init_data == "dev_mode":
        return jsonify({"error": "يجب فتح التطبيق من داخل تيليجرام فقط"}), 403

    user = verify_telegram_init_data(init_data)
    if not user:
        return jsonify({"error": "فشل التحقق من تيليجرام"}), 401

    user_id    = str(user["id"])
    first_name = user.get("first_name", "")

    session_id = ""
    try:
        session = sb_insert("sessions", {
            "user_id":    user_id,
            "started_at": datetime.now(timezone.utc).isoformat()
        })
        session_id = session.get("id", "")
    except Exception:
        pass

    token = create_jwt(user_id, first_name)

    sub_status, sub_expires, sub_days = "none", None, 0
    try:
        existing_sub = get_subscription(user_id)
        if not existing_sub:
            trial_exp = (datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)).isoformat()
            sb_insert("subscriptions", {
                "user_id":    user_id,
                "plan":       "trial",
                "status":     "trial",
                "expires_at": trial_exp,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            sub_status, sub_expires, sub_days = "trial", trial_exp, TRIAL_DAYS
        else:
            sub_status  = existing_sub.get("status", "none")
            sub_expires = existing_sub.get("expires_at")
            sub_days    = sub_days_left(user_id)
    except Exception as e:
        print(f"Sub init error: {e}")

    return jsonify({
        "token":       token,
        "user_id":     user_id,
        "first_name":  first_name,
        "username":    user.get("username", ""),
        "session_id":  session_id,
        "sub_status":  sub_status,
        "sub_expires": sub_expires,
        "sub_days":    sub_days,
    })

@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status":             "ok",
        "app":                "مُلّاك 🏠",
        "geidea_configured":  bool(GEIDEA_PUBLIC_KEY and GEIDEA_API_PASSWORD),
        "geidea_base_url":    GEIDEA_BASE_URL,
        "geidea_hpp_base":    GEIDEA_HPP_BASE,
        "railway_url":        RAILWAY_URL or "NOT SET"
    })

# ============================================================
# 📊 Sessions
# ============================================================
@app.route("/api/session/end", methods=["POST"])
def end_session():
    try:
        raw = request.get_data(as_text=True)
        try:   d = json.loads(raw) if raw else {}
        except: d = request.json or {}
        session_id = d.get("session_id", "")
        duration   = max(0, min(int(d.get("duration", 0)), 86400))
        if session_id:
            sb_update("sessions", {"id": f"eq.{session_id}"}, {
                "ended_at":         datetime.now(timezone.utc).isoformat(),
                "duration_seconds": duration
            })
    except Exception:
        pass
    return "", 204

@app.route("/api/session/ping", methods=["POST"])
@require_auth
@rate_limit(max_calls=120, period=60)
def session_ping(user):
    try:
        d = request.json or {}
        sid      = d.get("session_id", "")
        duration = max(0, int(d.get("duration", 0)))
        if sid:
            sb_update("sessions", {"id": f"eq.{sid}"}, {"duration_seconds": duration})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 🏗️ العقارات
# ============================================================
@app.route("/api/properties", methods=["GET"])
@require_auth
@rate_limit(max_calls=60, period=60)
def get_properties(user):
    try:
        return jsonify(sb_select("properties", {"user_id": f"eq.{user['user_id']}"}))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/properties", methods=["POST"])
@require_auth
@require_write
@rate_limit(max_calls=20, period=60)
def add_property(user):
    try:
        d = request.json or {}
        if not d.get("name"):
            return jsonify({"error": "الاسم مطلوب"}), 400
        result = sb_insert("properties", {
            "user_id":       str(user["user_id"]),
            "name":          d.get("name", ""),
            "location":      d.get("location", ""),
            "type":          d.get("type", "مالك"),
            "investor_rent": d.get("investor_rent", 0),
            "contract_desc": d.get("contract_desc", "")
        })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/properties/<prop_id>", methods=["PUT"])
@require_auth
@require_write
def edit_property(user, prop_id):
    try:
        d       = request.json or {}
        allowed = ["name", "location", "type", "investor_rent", "contract_desc"]
        updates = {k: d[k] for k in allowed if k in d}
        result  = sb_update("properties",
            {"id": f"eq.{prop_id}", "user_id": f"eq.{user['user_id']}"}, updates)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/properties/<prop_id>", methods=["DELETE"])
@require_auth
@require_write
def delete_property(user, prop_id):
    try:
        sb_delete("properties", {"id": f"eq.{prop_id}", "user_id": f"eq.{user['user_id']}"})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 🚪 الوحدات
# ============================================================
@app.route("/api/units", methods=["GET"])
@require_auth
def get_units(user):
    try:
        filters = {"user_id": f"eq.{user['user_id']}"}
        prop_id = request.args.get("property_id")
        if prop_id: filters["property_id"] = f"eq.{prop_id}"
        return jsonify(sb_select("units", filters))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/units", methods=["POST"])
@require_auth
@require_write
def add_unit(user):
    try:
        d = request.json or {}
        result = sb_insert("units", {
            "user_id":     str(user["user_id"]),
            "property_id": d.get("property_id"),
            "unit_num":    d.get("unit_num"),
            "unit_type":   d.get("unit_type", "شقة")
        })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/units/<unit_id>", methods=["DELETE"])
@require_auth
@require_write
def delete_unit(user, unit_id):
    try:
        sb_delete("units", {"id": f"eq.{unit_id}", "user_id": f"eq.{user['user_id']}"})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 🧑‍💼 المستأجرون
# ============================================================
@app.route("/api/tenants", methods=["GET"])
@require_auth
def get_tenants(user):
    try:
        return jsonify(sb_select("tenants",
            {"user_id": f"eq.{user['user_id']}"},
            select="*,properties(name,type)"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants", methods=["POST"])
@require_auth
@require_write
@rate_limit(max_calls=20, period=60)
def add_tenant(user):
    try:
        d = request.json or {}
        if not d.get("name"):
            return jsonify({"error": "الاسم مطلوب"}), 400
        row = {
            "user_id":      str(user["user_id"]),
            "name":         d.get("name", ""),
            "phone":        d.get("phone", ""),
            "property_id":  d.get("property_id"),
            "unit_num":     d.get("unit_num"),
            "rent":         d.get("rent", 0),
            "period":       d.get("period", "شهر"),
            "period_count": d.get("period_count", 1),
            "period_label": d.get("period_label", ""),
            "paid":         False
        }
        if d.get("start_date"): row["start_date"] = d["start_date"]
        if d.get("end_date"):   row["end_date"]   = d["end_date"]
        result = sb_insert("tenants", row)
        sb_update("units",
            {"property_id": f"eq.{d['property_id']}",
             "unit_num":    f"eq.{d['unit_num']}",
             "user_id":     f"eq.{user['user_id']}"},
            {"tenant_name": d["name"]})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants/<tenant_id>", methods=["PUT"])
@require_auth
@require_write
def edit_tenant(user, tenant_id):
    try:
        d       = request.json or {}
        allowed = ["name", "phone", "rent", "period", "period_count",
                   "period_label", "start_date", "end_date", "paid"]
        updates = {k: d[k] for k in allowed if k in d}
        result  = sb_update("tenants",
            {"id": f"eq.{tenant_id}", "user_id": f"eq.{user['user_id']}"}, updates)
        if "name" in d:
            tenant_data = sb_select("tenants",
                {"id": f"eq.{tenant_id}", "user_id": f"eq.{user['user_id']}"},
                select="property_id,unit_num")
            if tenant_data:
                t = tenant_data[0]
                sb_update("units",
                    {"property_id": f"eq.{t['property_id']}",
                     "unit_num":    f"eq.{t['unit_num']}",
                     "user_id":     f"eq.{user['user_id']}"},
                    {"tenant_name": d["name"]})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants/<tenant_id>", methods=["DELETE"])
@require_auth
@require_write
def delete_tenant(user, tenant_id):
    try:
        data = sb_select("tenants",
            {"id": f"eq.{tenant_id}", "user_id": f"eq.{user['user_id']}"},
            select="property_id,unit_num")
        if data:
            t = data[0]
            sb_update("units",
                {"property_id": f"eq.{t['property_id']}",
                 "unit_num":    f"eq.{t['unit_num']}",
                 "user_id":     f"eq.{user['user_id']}"},
                {"tenant_name": None})
        sb_delete("tenants", {"id": f"eq.{tenant_id}", "user_id": f"eq.{user['user_id']}"})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants/<tenant_id>/pay", methods=["POST"])
@require_auth
@require_write
def pay_tenant(user, tenant_id):
    try:
        result = sb_update("tenants",
            {"id": f"eq.{tenant_id}", "user_id": f"eq.{user['user_id']}"},
            {"paid": True})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants/reset", methods=["POST"])
@require_auth
@require_write
def reset_tenants(user):
    try:
        sb_update("tenants", {"user_id": f"eq.{user['user_id']}"}, {"paid": False})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 📤 المصروفات
# ============================================================
@app.route("/api/expenses", methods=["GET"])
@require_auth
def get_expenses(user):
    try:
        return jsonify(sb_select("expenses",
            {"user_id": f"eq.{user['user_id']}"},
            order="created_at.desc"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/expenses", methods=["POST"])
@require_auth
@require_write
@rate_limit(max_calls=20, period=60)
def add_expense(user):
    try:
        d = request.json or {}
        if not d.get("description"):
            return jsonify({"error": "الوصف مطلوب"}), 400
        result = sb_insert("expenses", {
            "user_id":     str(user["user_id"]),
            "category":    d.get("category", "أخرى"),
            "description": d.get("description", ""),
            "amount":      d.get("amount", 0),
            "property_id": d.get("property_id") or None,
            "unit_num":    d.get("unit_num") or None
        })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/expenses/<exp_id>", methods=["DELETE"])
@require_auth
@require_write
def delete_expense(user, exp_id):
    try:
        sb_delete("expenses", {"id": f"eq.{exp_id}", "user_id": f"eq.{user['user_id']}"})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 📊 الإحصائيات
# ============================================================
@app.route("/api/stats", methods=["GET"])
@require_auth
def get_stats(user):
    try:
        uid      = user["user_id"]
        props    = sb_select("properties", {"user_id": f"eq.{uid}"})
        tenants  = sb_select("tenants",    {"user_id": f"eq.{uid}"})
        expenses = sb_select("expenses",   {"user_id": f"eq.{uid}"})
        income   = sum(t["rent"] for t in tenants if t.get("paid"))
        inv_exp  = sum(p.get("investor_rent", 0) for p in props if p.get("type") == "مستثمر")
        man_exp  = sum(e.get("amount", 0) for e in expenses)
        total    = inv_exp + man_exp
        return jsonify({
            "props":    len(props),
            "tenants":  len(tenants),
            "income":   income,
            "expenses": total,
            "net":      income - total
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 💳 Subscription Endpoints
# ============================================================
@app.route("/api/subscription/status", methods=["GET"])
@require_auth
def subscription_status(user):
    try:
        sub = get_subscription(user["user_id"])
        if not sub:
            return jsonify({"status": "none", "active": False, "days_left": 0})
        active = sub_is_active(user["user_id"])
        days   = sub_days_left(user["user_id"])
        return jsonify({
            "status":     sub.get("status", "none"),
            "plan":       sub.get("plan", ""),
            "active":     active,
            "expires_at": sub.get("expires_at", ""),
            "days_left":  days,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/test/geidea", methods=["GET"])
def test_geidea():
    """اختبار سريع — افتحه من متصفحك للتحقق من صحة الإعدادات"""
    if not GEIDEA_PUBLIC_KEY or not GEIDEA_API_PASSWORD:
        return jsonify({
            "ok":                 False,
            "error":              "GEIDEA_PUBLIC_KEY أو GEIDEA_API_PASSWORD غير مضبوط",
            "geidea_public_key":  "✅ موجود" if GEIDEA_PUBLIC_KEY  else "❌ غير موجود",
            "geidea_api_password":"✅ موجود" if GEIDEA_API_PASSWORD else "❌ غير موجود",
            "railway_url":        RAILWAY_URL or "❌ غير مضبوط",
            "geidea_base_url":    GEIDEA_BASE_URL,
        }), 400

    if not RAILWAY_URL:
        return jsonify({"ok": False, "error": "RAILWAY_PUBLIC_DOMAIN غير مضبوط"}), 400

    callback_url = f"https://{RAILWAY_URL}/api/subscription/callback"
    return_url   = MINI_APP_URL.rstrip("/") + "/?payment=done"
    merchant_ref = f"test_{int(time.time())}"
    timestamp    = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    signature    = geidea_signature(PLAN_MONTHLY_AMOUNT, "SAR", merchant_ref, timestamp)

    payload = {
        "amount":              PLAN_MONTHLY_AMOUNT,
        "currency":            "SAR",
        "timestamp":           timestamp,
        "merchantReferenceId": merchant_ref,
        "callbackUrl":         callback_url,
        "returnUrl":           return_url,
        "language":            "ar",
        "signature":           signature,
        "customer": {
            "name": "مُلّاك"
        },
        "order": {
            "statementDescriptor": {
                "name":  "ملاك",
                "phone": ""
            }
        }
    }

    url = f"{GEIDEA_BASE_URL}/payment-intent/api/v2/direct/session"

    try:
        resp = requests.post(
            url,
            json=payload,
            auth=geidea_auth(),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=20
        )

        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:1000]}

        checkout_url = extract_checkout_url(body)

        return jsonify({
            "ok":           resp.ok,
            "status_code":  resp.status_code,
            "request_url":  url,
            "response":     body,
            "checkout_url": checkout_url,
            "hpp_base":     GEIDEA_HPP_BASE,
            "config": {
                "geidea_base_url": GEIDEA_BASE_URL,
                "callback_url":    callback_url,
                "return_url":      return_url,
            }
        })

    except requests.exceptions.Timeout:
        return jsonify({"ok": False, "error": "Timeout — تحقق من GEIDEA_BASE_URL"}), 502
    except requests.exceptions.ConnectionError:
        return jsonify({"ok": False, "error": "Connection error — تحقق من GEIDEA_BASE_URL"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/subscription/checkout", methods=["POST"])
@require_auth
@rate_limit(max_calls=5, period=60)
def create_checkout(user):
    """ينشئ Geidea Checkout Session ويرجع رابط صفحة الدفع"""
    if not GEIDEA_PUBLIC_KEY:
        return jsonify({"error": "بوابة الدفع غير مضبوطة — GEIDEA_PUBLIC_KEY"}), 500
    if not GEIDEA_API_PASSWORD:
        return jsonify({"error": "بوابة الدفع غير مضبوطة — GEIDEA_API_PASSWORD"}), 500
    if not RAILWAY_URL:
        return jsonify({"error": "RAILWAY_PUBLIC_DOMAIN غير مضبوط"}), 500

    merchant_ref = f"mullak_{user['user_id']}_{int(time.time())}"
    callback_url = f"https://{RAILWAY_URL}/api/subscription/callback"
    return_url   = MINI_APP_URL.rstrip("/") + "/?payment=done"
    timestamp    = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    signature    = geidea_signature(PLAN_MONTHLY_AMOUNT, "SAR", merchant_ref, timestamp)

    payload = {
        "amount":              PLAN_MONTHLY_AMOUNT,
        "currency":            "SAR",
        "timestamp":           timestamp,
        "merchantReferenceId": merchant_ref,
        "callbackUrl":         callback_url,
        "returnUrl":           return_url,
        "language":            "ar",
        "signature":           signature,
        "customer": {
            "name": "مُلّاك"
        },
        "order": {
            "statementDescriptor": {
                "name":  "ملاك",
                "phone": ""
            }
        }
    }

    url = f"{GEIDEA_BASE_URL}/payment-intent/api/v2/direct/session"
    print(f"📤 Geidea checkout: user={user['user_id']}, ref={merchant_ref}")

    try:
        resp = requests.post(
            url,
            json=payload,
            auth=geidea_auth(),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=20
        )

        try:
            resp_data = resp.json()
        except Exception:
            resp_data = {"raw": resp.text[:1000]}

        print(f"📩 Geidea: status={resp.status_code}, body={json.dumps(resp_data, ensure_ascii=False)[:300]}")

        if not resp.ok:
            error_msg = (
                resp_data.get("responseMessage") or
                resp_data.get("message") or
                f"خطأ {resp.status_code} من بوابة الدفع"
            )
            return jsonify({"error": error_msg, "details": resp_data}), 502

        payment_url = extract_checkout_url(resp_data)
        if not payment_url:
            return jsonify({
                "error":    "لم يُعثر على رابط الدفع في رد Geidea",
                "response": resp_data
            }), 502

        try:
            sb_insert("payment_orders", {
                "user_id":    str(user["user_id"]),
                "order_id":   merchant_ref,
                "amount":     PLAN_MONTHLY_AMOUNT,
                "status":     "pending",
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            print(f"⚠️ payment_orders (non-critical): {e}")

        print(f"✅ payment_url: {payment_url}")
        return jsonify({"payment_url": payment_url, "order_id": merchant_ref})

    except requests.exceptions.Timeout:
        return jsonify({"error": "انتهت مهلة الاتصال ببوابة الدفع"}), 502
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "تعذّر الاتصال ببوابة الدفع"}), 502
    except Exception as e:
        print(f"❌ Checkout error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/subscription/callback", methods=["POST"])
def payment_callback():
    """Geidea تستدعيه تلقائياً بعد إتمام الدفع"""
    try:
        data = request.json or {}
        print(f"📩 Geidea Callback: {json.dumps(data, ensure_ascii=False)[:800]}")

        status = str(
            data.get("status") or
            data.get("responseCode") or
            (data.get("order") or {}).get("status") or ""
        ).lower().strip()

        merchant_ref = str(
            data.get("merchantReferenceId") or
            data.get("merchantRefId") or
            (data.get("order") or {}).get("merchantReferenceId") or ""
        ).strip()

        print(f"    status={status!r}, ref={merchant_ref!r}")

        SUCCESS_CODES = {"success", "000", "paid", "captured", "approved"}
        if status not in SUCCESS_CODES:
            return jsonify({"ok": True, "processed": False, "status": status}), 200

        if not merchant_ref.startswith("mullak_"):
            return jsonify({"ok": True, "processed": False, "reason": "unknown ref"}), 200

        parts   = merchant_ref.split("_")
        user_id = parts[1] if len(parts) >= 3 else ""
        if not user_id:
            return jsonify({"ok": True, "processed": False, "reason": "no user_id"}), 200

        now_utc  = datetime.now(timezone.utc)
        existing = get_subscription(user_id)
        base     = now_utc
        if existing and existing.get("expires_at") and sub_is_active(user_id):
            try:
                base = datetime.fromisoformat(existing["expires_at"].replace("Z", "+00:00"))
            except Exception:
                base = now_utc

        new_expires = (base + timedelta(days=PLAN_MONTHLY_DAYS)).isoformat()

        if existing:
            sb_update("subscriptions", {"user_id": f"eq.{user_id}"}, {
                "plan": "monthly", "status": "active",
                "expires_at": new_expires, "updated_at": now_utc.isoformat()
            })
        else:
            sb_insert("subscriptions", {
                "user_id": user_id, "plan": "monthly", "status": "active",
                "expires_at": new_expires, "created_at": now_utc.isoformat()
            })

        try:
            sb_update("payment_orders", {"order_id": f"eq.{merchant_ref}"},
                      {"status": "paid", "paid_at": now_utc.isoformat()})
        except Exception:
            pass

        try:
            if bot:
                bot.send_message(int(user_id),
                    f"🎉 *تم تفعيل اشتراكك بنجاح!*\n\n"
                    f"✅ الخطة الشهرية — {int(PLAN_MONTHLY_AMOUNT)} ريال\n"
                    f"📅 تنتهي في: {new_expires[:10]}\n\n"
                    f"استمتع بجميع مميزات مُلّاك 🏠",
                    parse_mode="Markdown")
        except Exception as e:
            print(f"⚠️ Telegram notify: {e}")

        print(f"✅ اشتراك مُفعَّل: user={user_id}, expires={new_expires}")
        return jsonify({"ok": True, "processed": True})

    except Exception as e:
        print(f"❌ Callback error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/subscription/verify/<order_id>", methods=["GET"])
@require_auth
def verify_payment(user, order_id):
    try:
        if not GEIDEA_PUBLIC_KEY or not GEIDEA_API_PASSWORD:
            return jsonify({"error": "بوابة الدفع غير مضبوطة"}), 500

        resp = requests.get(
            f"{GEIDEA_BASE_URL}/payment-intent/api/v2/order",
            params={"merchantReferenceId": order_id},
            auth=geidea_auth(),
            headers={"Accept": "application/json"},
            timeout=15
        )

        if not resp.ok:
            return jsonify({"error": f"خطأ {resp.status_code} من Geidea"}), 502

        data         = resp.json()
        order_status = str(
            data.get("status") or
            (data.get("order") or {}).get("status") or ""
        ).lower()

        SUCCESS_CODES = {"success", "000", "paid", "captured", "approved"}
        if order_status in SUCCESS_CODES:
            uid      = user["user_id"]
            now_utc  = datetime.now(timezone.utc)
            existing = get_subscription(uid)
            base     = now_utc
            if existing and existing.get("expires_at") and sub_is_active(uid):
                try:
                    base = datetime.fromisoformat(existing["expires_at"].replace("Z", "+00:00"))
                except Exception:
                    base = now_utc
            new_exp = (base + timedelta(days=PLAN_MONTHLY_DAYS)).isoformat()
            if existing:
                sb_update("subscriptions", {"user_id": f"eq.{uid}"},
                    {"plan": "monthly", "status": "active", "expires_at": new_exp,
                     "updated_at": now_utc.isoformat()})
            else:
                sb_insert("subscriptions", {
                    "user_id": uid, "plan": "monthly", "status": "active",
                    "expires_at": new_exp, "created_at": now_utc.isoformat()
                })
            return jsonify({"paid": True, "expires_at": new_exp})

        return jsonify({"paid": False, "status": order_status})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 📄 تقرير PDF
# ============================================================
@app.route("/api/report/print", methods=["GET"])
@require_auth
def print_report(user):
    try:
        uid      = user["user_id"]
        fname    = user.get("first_name", "")
        props    = sb_select("properties", {"user_id": f"eq.{uid}"})
        tenants  = sb_select("tenants",    {"user_id": f"eq.{uid}"}, select="*,properties(name)")
        expenses = sb_select("expenses",   {"user_id": f"eq.{uid}"}, order="created_at.desc")

        income  = sum(t["rent"] for t in tenants if t.get("paid"))
        pending = sum(t["rent"] for t in tenants if not t.get("paid"))
        total_r = sum(t["rent"] for t in tenants)
        inv_exp = sum(p.get("investor_rent", 0) for p in props if p.get("type") == "مستثمر")
        man_exp = sum(e.get("amount", 0) for e in expenses)
        total_e = inv_exp + man_exp
        net     = income - total_e
        today   = datetime.now().strftime("%Y/%m/%d")
        fmt     = lambda n: f"{int(n or 0):,}"

        tenants_rows = ""
        for t in tenants:
            color  = "#10b981" if t.get("paid") else "#ef4444"
            status = "✅ دفع" if t.get("paid") else "❌ لم يدفع"
            prop   = (t.get("properties") or {})
            tenants_rows += f"""<tr>
              <td>{t['name']}</td><td>{t.get('phone','')}</td>
              <td>{prop.get('name','')}</td><td>وحدة {t.get('unit_num','')}</td>
              <td>{t.get('period_label','')}</td>
              <td>{t.get('start_date','—')}</td><td>{t.get('end_date','—')}</td>
              <td>{fmt(t.get('rent',0))} ريال</td>
              <td style="color:{color};font-weight:700">{status}</td>
            </tr>"""

        expenses_rows = ""
        for e in expenses:
            prop_name = ""
            if e.get("property_id"):
                p = next((x for x in props if x["id"] == e["property_id"]), None)
                if p: prop_name = p["name"]
            expenses_rows += f"<tr><td>{e.get('category','')}</td><td>{e.get('description','')}</td><td>{prop_name}</td><td>{fmt(e.get('amount',0))} ريال</td></tr>"

        props_rows = ""
        for p in props:
            pt = [t for t in tenants if t.get("property_id") == p["id"]]
            pi = sum(t["rent"] for t in pt if t.get("paid"))
            pe = sum(e.get("amount",0) for e in expenses if e.get("property_id") == p["id"])
            if p.get("type") == "مستثمر": pe += p.get("investor_rent", 0)
            props_rows += f"<tr><td>{p['name']}</td><td>{p.get('location','')}</td><td>{p.get('type','')}</td><td>{len(pt)}</td><td>{fmt(pi)} ريال</td><td>{fmt(pe)} ريال</td><td style=\"color:{'#f59e0b' if pi-pe>=0 else '#ef4444'};font-weight:700\">{fmt(pi-pe)} ريال</td></tr>"

        html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="UTF-8">
<title>تقرير مُلّاك — {today}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:#fff;color:#1a1a2e;direction:rtl;font-size:13px}}
.header{{background:linear-gradient(135deg,#1e3a5f,#0a0e1a);color:#fff;padding:28px 32px;display:flex;justify-content:space-between;align-items:center}}
.logo{{font-size:32px;font-weight:900}}.logo span{{color:#10b981}}
.summary{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;padding:20px 32px;background:#f8fafc;border-bottom:2px solid #e2e8f0}}
.sum-card{{background:#fff;border-radius:10px;padding:14px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
.sum-num{{font-size:20px;font-weight:800;margin-bottom:4px}}.sum-label{{font-size:11px;color:#64748b}}
.green{{color:#10b981}}.red{{color:#ef4444}}.gold{{color:#f59e0b}}.teal{{color:#14b8a6}}
.section{{padding:20px 32px}}
.section-title{{font-size:15px;font-weight:800;color:#1e3a5f;margin-bottom:12px;padding-bottom:6px;border-bottom:2px solid #3b82f6}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#1e3a5f;color:#fff;padding:10px 8px;text-align:right;font-weight:700}}
td{{padding:9px 8px;border-bottom:1px solid #e2e8f0}}
tr:nth-child(even) td{{background:#f8fafc}}
.footer{{background:#f1f5f9;padding:16px 32px;text-align:center;font-size:11px;color:#64748b;margin-top:20px}}
@media print{{body{{font-size:11px}}}}
</style></head><body>
<div class="header">
  <div><div class="logo">مُلّ<span>اك</span></div><div style="font-size:13px;margin-top:4px;opacity:.7">نظام إدارة العقارات الذكي</div></div>
  <div style="text-align:left;font-size:12px;opacity:.8">
    <div style="font-size:14px;font-weight:700;margin-bottom:4px">التقرير المالي الشامل</div>
    <div>المستخدم: {fname}</div><div>التاريخ: {today}</div>
    <div>العقارات: {len(props)} | المستأجرون: {len(tenants)}</div>
  </div>
</div>
<div class="summary">
  <div class="sum-card"><div class="sum-num teal">{fmt(total_r)}</div><div class="sum-label">📥 إجمالي الواردات</div></div>
  <div class="sum-card"><div class="sum-num green">{fmt(income)}</div><div class="sum-label">✅ المحصّل</div></div>
  <div class="sum-card"><div class="sum-num red">{fmt(pending)}</div><div class="sum-label">⏳ المعلّق</div></div>
  <div class="sum-card"><div class="sum-num red">{fmt(total_e)}</div><div class="sum-label">📤 المصروفات</div></div>
  <div class="sum-card"><div class="sum-num {'gold' if net>=0 else 'red'}">{fmt(net)}</div><div class="sum-label">💰 صافي الربح</div></div>
</div>
<div class="section"><div class="section-title">🏗️ ملخص العقارات</div>
<table><tr><th>العقار</th><th>الموقع</th><th>النوع</th><th>المستأجرون</th><th>الدخل</th><th>المصروفات</th><th>الصافي</th></tr>
{props_rows or '<tr><td colspan="7" style="text-align:center;color:#64748b">لا يوجد عقارات</td></tr>'}</table></div>
<div class="section"><div class="section-title">🧑‍💼 المستأجرون</div>
<table><tr><th>الاسم</th><th>الهاتف</th><th>العقار</th><th>الوحدة</th><th>المدة</th><th>البداية</th><th>النهاية</th><th>الإيجار</th><th>الحالة</th></tr>
{tenants_rows or '<tr><td colspan="9" style="text-align:center;color:#64748b">لا يوجد مستأجرون</td></tr>'}</table></div>
<div class="section"><div class="section-title">📤 سجل المصروفات</div>
<table><tr><th>التصنيف</th><th>الوصف</th><th>العقار</th><th>المبلغ</th></tr>
{expenses_rows or '<tr><td colspan="4" style="text-align:center;color:#64748b">لا توجد مصروفات</td></tr>'}
<tr style="background:#fef3c7;font-weight:800"><td colspan="3" style="text-align:center">إجمالي المصروفات</td><td style="color:#ef4444">{fmt(total_e)} ريال</td></tr></table></div>
<div class="footer">تم إنشاء هذا التقرير بواسطة نظام مُلّاك — {today}</div>
<script>window.onload=function(){{window.print()}}</script>
</body></html>"""

        return Response(html, mimetype="text/html; charset=utf-8")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 🔔 التذكيرات اليومية
# ============================================================
def send_daily_reminders():
    if not BOT_TOKEN or not SUPABASE_URL:
        return
    print("🔔 تشغيل التذكيرات اليومية...")
    try:
        all_tenants = sb_select("tenants", {"paid": "eq.false"},
            select="user_id,name,unit_num,rent,period_label,properties(name)")
        if not all_tenants:
            return
        users_data = {}
        for t in all_tenants:
            uid = t.get("user_id")
            if uid: users_data.setdefault(uid, []).append(t)
        for user_id, unpaid in users_data.items():
            total = sum(t.get("rent", 0) for t in unpaid)
            lines = []
            for t in unpaid[:10]:
                prop = (t.get("properties") or {}).get("name", "")
                lines.append(f"• *{t['name']}* — {prop} — وحدة {t.get('unit_num','')} — {int(t.get('rent',0)):,} ريال")
            if len(unpaid) > 10:
                lines.append(f"_... و {len(unpaid)-10} آخرين_")
            msg  = f"🔔 *تذكير يومي — مُلّاك*\n\n"
            msg += f"لديك *{len(unpaid)}* مستأجر لم يدفع:\n\n"
            msg += "\n".join(lines)
            msg += f"\n\n💰 *إجمالي المتأخر: {total:,} ريال*"
            msg += "\n\nافتح التطبيق لتسجيل الدفعات 👇"
            try:
                if bot:
                    bot.send_message(int(user_id), msg,
                        parse_mode="Markdown", reply_markup=app_keyboard())
            except Exception as e:
                print(f"❌ {user_id}: {e}")
    except Exception as e:
        print(f"❌ التذكيرات: {e}")

# ============================================================
# 🤖 تيليجرام بوت
# ============================================================
def app_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        text="🏠 فتح تطبيق مُلّاك",
        web_app=WebAppInfo(url=MINI_APP_URL)
    ))
    return markup

if bot:
    @app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
    def webhook():
        if request.headers.get("content-type") == "application/json":
            update = telebot.types.Update.de_json(request.data.decode("utf-8"))
            bot.process_new_updates([update])
        return "", 200

    @bot.message_handler(commands=["start"])
    def start(msg):
        name = msg.from_user.first_name
        bot.send_message(msg.chat.id,
            f"🏠 *أهلاً {name} في مُلّاك!*\n\nنظام إدارة عقاراتك الذكي 🤖\n\nاضغط الزر أدناه لفتح التطبيق 👇",
            parse_mode="Markdown", reply_markup=app_keyboard())

    @bot.message_handler(commands=["stats"])
    def send_stats(msg):
        if str(msg.from_user.id) != str(ADMIN_ID):
            return
        try:
            sessions = sb_select("sessions")
            props    = sb_select("properties")
            tenants  = sb_select("tenants")
            if not sessions:
                bot.send_message(msg.chat.id, "📊 لا توجد بيانات بعد")
                return
            all_users      = set(s["user_id"] for s in sessions)
            total_users    = len(all_users)
            total_sessions = len(sessions)
            returning      = len([u for u in all_users if sum(1 for s in sessions if s["user_id"] == u) > 1])
            pct_ret        = int(returning / total_users * 100) if total_users else 0
            completed = [s for s in sessions if s.get("duration_seconds", 0) > 0]
            avg_sec   = int(sum(s["duration_seconds"] for s in completed) / len(completed)) if completed else 0
            lt1 = len([s for s in completed if s["duration_seconds"] < 60])
            lt2 = len([s for s in completed if 60  <= s["duration_seconds"] < 120])
            lt3 = len([s for s in completed if 120 <= s["duration_seconds"] < 180])
            gt3 = len([s for s in completed if s["duration_seconds"] >= 180])
            tot_c = len(completed) or 1
            pct   = lambda n: int(n / tot_c * 100)
            total_props   = len(props)
            total_tenants = len(tenants)
            total_paid    = len([t for t in tenants if t.get("paid")])
            app_users     = len(set(p["user_id"] for p in props)) if props else 0
            if pct(gt3) >= 30:   rating = "🔥 التطبيق ممتاز — المستخدمون يتفاعلون بعمق"
            elif pct(lt1) >= 60: rating = "⚠️ أغلب المستخدمين يخرجون سريعاً — راجع تجربة المستخدم"
            else:                rating = "✅ التطبيق يعمل بشكل جيد"
            text = (
                f"📊 *إحصائيات مُلّاك*\n━━━━━━━━━━━━━━━━━\n"
                f"👥 المستخدمون: `{total_users}` | 📱 الجلسات: `{total_sessions}`\n"
                f"🔁 الراجعون: `{returning}` ({pct_ret}%)\n"
                f"⏱️ متوسط الاستخدام: `{avg_sec//60}:{avg_sec%60:02d}` دقيقة\n━━━━━━━━━━━━━━━━━\n"
                f"🏗️ مستخدمو التطبيق: `{app_users}`\n"
                f"🏢 العقارات: `{total_props}` | 🧑‍💼 المستأجرون: `{total_tenants}` (مدفوع: `{total_paid}`)\n"
                f"━━━━━━━━━━━━━━━━━\n📌 *التقييم:* {rating}"
            )
            bot.send_message(msg.chat.id, text, parse_mode="Markdown")
        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ خطأ: `{e}`", parse_mode="Markdown")

    @bot.message_handler(func=lambda m: not (m.text or "").startswith("/"))
    def default(msg):
        bot.send_message(msg.chat.id, "👋 اضغط الزر لفتح التطبيق", reply_markup=app_keyboard())

@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    if not RAILWAY_URL:
        return jsonify({"error": "أضف RAILWAY_PUBLIC_DOMAIN في Variables"}), 400
    url = f"https://{RAILWAY_URL}/webhook/{BOT_TOKEN}"
    if bot:
        bot.remove_webhook()
        ok = bot.set_webhook(url=url, drop_pending_updates=True)
        return jsonify({"ok": ok, "webhook": url})
    return jsonify({"error": "BOT_TOKEN غير مضبوط"}), 400

# ============================================================
# 🚀 تشغيل
# ============================================================
if __name__ == "__main__":
    if BOT_TOKEN:
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(send_daily_reminders, "cron", hour=6, minute=0, id="daily")
        scheduler.start()
        print("✅ جدولة التذكيرات اليومية تعمل")

    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 تشغيل على المنفذ {port}")
    print(f"   Geidea Public Key : {'✅' if GEIDEA_PUBLIC_KEY  else '❌ غير مضبوط'}")
    print(f"   Geidea API Pass   : {'✅' if GEIDEA_API_PASSWORD else '❌ غير مضبوط'}")
    print(f"   Geidea Base URL   : {GEIDEA_BASE_URL}")
    print(f"   Geidea HPP Base   : {GEIDEA_HPP_BASE}")
    print(f"   Railway URL       : {RAILWAY_URL or '❌ غير مضبوط'}")
    app.run(host="0.0.0.0", port=port)
