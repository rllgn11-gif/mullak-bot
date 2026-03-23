import os
import hmac
import hashlib
import json
import time
import jwt
import requests
from urllib.parse import unquote
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

app = Flask(__name__)
CORS(app)

# ============================================================
# 🔑 المفاتيح — كلها من Railway Variables
# ============================================================
BOT_TOKEN            = os.environ.get("BOT_TOKEN", "")
JWT_SECRET           = os.environ.get("JWT_SECRET", "CHANGE_THIS_SECRET")
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_KEY", "")   # service_role
MINI_APP_URL         = os.environ.get("MINI_APP_URL", "https://rllgn11-gif.github.io/mullak-bot/")
RAILWAY_URL          = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
# ============================================================

bot = telebot.TeleBot(BOT_TOKEN)

# ============================================================
# 🛠️ مساعد Supabase (كل الطلبات تمر من هنا)
# ============================================================
SB_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def sb_select(table, filters=None, select="*", order=None):
    params = {"select": select}
    if filters:
        params.update(filters)
    if order:
        params["order"] = order
    res = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=SB_HEADERS, params=params)
    res.raise_for_status()
    return res.json()

def sb_insert(table, data):
    res = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=SB_HEADERS, json=data)
    res.raise_for_status()
    result = res.json()
    return result[0] if isinstance(result, list) else result

def sb_update(table, filters, data):
    res = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}", headers=SB_HEADERS, params=filters, json=data)
    res.raise_for_status()
    result = res.json()
    return result[0] if isinstance(result, list) and result else {"ok": True}

def sb_delete(table, filters):
    res = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}", headers=SB_HEADERS, params=filters)
    res.raise_for_status()
    return {"ok": True}

# ============================================================
# 🔐 تحقق Telegram الرسمي (HMAC SHA256)
# ============================================================
def verify_telegram_init_data(init_data: str):
    """
    التحقق الرسمي من تيليجرام
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    try:
        # فك الترميز
        decoded = unquote(init_data)
        parts = decoded.split("&")

        data_dict = {}
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                data_dict[k] = v

        # استخراج الـ hash
        hash_received = data_dict.pop("hash", None)
        if not hash_received:
            return None

        # بناء data_check_string (مرتب أبجدياً)
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data_dict.items())
        )

        # المفتاح السري
        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        # حساب الـ hash
        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        # المقارنة الآمنة
        if not hmac.compare_digest(expected_hash, hash_received):
            return None

        # استخراج بيانات المستخدم
        user_json = data_dict.get("user", "{}")
        user = json.loads(user_json)
        return user

    except Exception as e:
        print(f"❌ Telegram verification error: {e}")
        return None

# ============================================================
# 🎫 JWT — إنشاء وتحقق
# ============================================================
def create_jwt(user_id: str, first_name: str) -> str:
    payload = {
        "user_id": str(user_id),
        "first_name": first_name,
        "iat": int(time.time()),
        "exp": int(time.time()) + (60 * 60 * 24 * 7)  # 7 أيام
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verify_jwt_token(token: str):
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return decoded
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_user_from_request():
    """استخراج المستخدم من الـ Authorization header"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    return verify_jwt_token(token)

def require_auth(f):
    """Decorator للتحقق من الجلسة"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_user_from_request()
        if not user:
            return jsonify({"error": "غير مصرح — أعد فتح التطبيق"}), 401
        return f(user, *args, **kwargs)
    return decorated

# ============================================================
# 🌐 CORS للـ Telegram WebApp
# ============================================================
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return response

@app.route("/<path:path>", methods=["OPTIONS"])
def options(path):
    return "", 200

# ============================================================
# 🔐 AUTH — تسجيل الدخول
# ============================================================
@app.route("/auth", methods=["POST"])
def auth():
    """
    يستقبل initData من تيليجرام
    يتحقق منها ويعطي JWT
    """
    data = request.json or {}
    init_data = data.get("initData", "")

    if not init_data:
        return jsonify({"error": "initData مطلوب"}), 400

    user = verify_telegram_init_data(init_data)

    if not user:
        return jsonify({"error": "فشل التحقق من تيليجرام"}), 401

    token = create_jwt(user["id"], user.get("first_name", ""))

    return jsonify({
        "token": token,
        "user_id": str(user["id"]),
        "first_name": user.get("first_name", ""),
        "username": user.get("username", "")
    })

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "app": "مُلّاك 🏠"})

# ============================================================
# 🏗️ العقارات
# ============================================================
@app.route("/api/properties", methods=["GET"])
@require_auth
def get_properties(user):
    try:
        data = sb_select("properties", {"user_id": f"eq.{user['user_id']}"})
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/properties", methods=["POST"])
@require_auth
def add_property(user):
    try:
        d = request.json
        row = {
            "user_id":       str(user["user_id"]),
            "name":          d.get("name", ""),
            "location":      d.get("location", ""),
            "type":          d.get("type", "مالك"),
            "investor_rent": d.get("investor_rent", 0),
            "contract_desc": d.get("contract_desc", "")
        }
        result = sb_insert("properties", row)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/properties/<prop_id>", methods=["DELETE"])
@require_auth
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
        if prop_id:
            filters["property_id"] = f"eq.{prop_id}"
        data = sb_select("units", filters)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/units", methods=["POST"])
@require_auth
def add_unit(user):
    try:
        d = request.json
        row = {
            "user_id":     str(user["user_id"]),
            "property_id": d.get("property_id"),
            "unit_num":    d.get("unit_num"),
            "unit_type":   d.get("unit_type", "شقة")
        }
        result = sb_insert("units", row)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 🧑‍💼 المستأجرون
# ============================================================
@app.route("/api/tenants", methods=["GET"])
@require_auth
def get_tenants(user):
    try:
        data = sb_select(
            "tenants",
            {"user_id": f"eq.{user['user_id']}"},
            select="*,properties(name,type)"
        )
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants", methods=["POST"])
@require_auth
def add_tenant(user):
    try:
        d = request.json
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
        result = sb_insert("tenants", row)
        # تحديث اسم المستأجر في الوحدة
        sb_update("units",
            {"property_id": f"eq.{d['property_id']}", "unit_num": f"eq.{d['unit_num']}", "user_id": f"eq.{user['user_id']}"},
            {"tenant_name": d["name"]}
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants/<tenant_id>/pay", methods=["POST"])
@require_auth
def pay_tenant(user, tenant_id):
    try:
        result = sb_update(
            "tenants",
            {"id": f"eq.{tenant_id}", "user_id": f"eq.{user['user_id']}"},
            {"paid": True}
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants/reset", methods=["POST"])
@require_auth
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
        data = sb_select("expenses", {"user_id": f"eq.{user['user_id']}"}, order="created_at.desc")
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/expenses", methods=["POST"])
@require_auth
def add_expense(user):
    try:
        d = request.json
        row = {
            "user_id":     str(user["user_id"]),
            "category":    d.get("category", "أخرى"),
            "description": d.get("description", ""),
            "amount":      d.get("amount", 0),
            "property_id": d.get("property_id") or None,
            "unit_num":    d.get("unit_num") or None
        }
        result = sb_insert("expenses", row)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/expenses/<exp_id>", methods=["DELETE"])
@require_auth
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
        uid = user["user_id"]
        props    = sb_select("properties", {"user_id": f"eq.{uid}"})
        tenants  = sb_select("tenants",    {"user_id": f"eq.{uid}"})
        expenses = sb_select("expenses",   {"user_id": f"eq.{uid}"})

        income     = sum(t["rent"] for t in tenants if t.get("paid"))
        inv_exp    = sum(p.get("investor_rent", 0) for p in props if p.get("type") == "مستثمر")
        manual_exp = sum(e.get("amount", 0) for e in expenses)
        total_exp  = inv_exp + manual_exp

        return jsonify({
            "props":    len(props),
            "tenants":  len(tenants),
            "income":   income,
            "expenses": total_exp,
            "net":      income - total_exp
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 🤖 تيليجرام بوت
# ============================================================
@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        update = telebot.types.Update.de_json(request.data.decode("utf-8"))
        bot.process_new_updates([update])
    return "", 200

@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    if not RAILWAY_URL:
        return jsonify({"error": "أضف RAILWAY_PUBLIC_DOMAIN في Variables"}), 400
    url = f"https://{RAILWAY_URL}/webhook/{BOT_TOKEN}"
    bot.remove_webhook()
    ok = bot.set_webhook(url=url, drop_pending_updates=True)
    return jsonify({"ok": ok, "webhook": url})

def app_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        text="🏠 فتح تطبيق مُلّاك",
        web_app=WebAppInfo(url=MINI_APP_URL)
    ))
    return markup

@bot.message_handler(commands=["start"])
def start(msg):
    name = msg.from_user.first_name
    bot.send_message(
        msg.chat.id,
        f"🏠 *أهلاً {name} في مُلّاك!*\n\nنظام إدارة عقاراتك الذكي 🤖\n\nاضغط الزر أدناه لفتح التطبيق 👇",
        parse_mode="Markdown",
        reply_markup=app_keyboard()
    )

@bot.message_handler(func=lambda m: True)
def default(msg):
    bot.send_message(msg.chat.id, "👋 اضغط الزر لفتح التطبيق", reply_markup=app_keyboard())

# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
