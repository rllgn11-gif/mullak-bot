import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

app = Flask(__name__)
CORS(app, resources={r"/api/*": {
    "origins": "*",
    "methods": ["GET", "POST", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "X-User-Id", "Authorization"]
}})

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-User-Id, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return response

@app.route("/api/<path:path>", methods=["OPTIONS"])
def options_handler(path):
    return "", 200

# ===== المفاتيح =====
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
MINI_APP_URL = os.environ.get("MINI_APP_URL", "https://rllgn11-gif.github.io/mullak-bot/")
RAILWAY_URL  = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
# ====================

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = telebot.TeleBot(BOT_TOKEN)

# ===== مساعد =====
def uid(req):
    return req.headers.get("X-User-Id", "anonymous")

# ===== Webhook تيليجرام =====
@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        update = telebot.types.Update.de_json(request.data.decode("utf-8"))
        bot.process_new_updates([update])
    return "", 200

# ===== Health Check =====
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "app": "مُلّاك"})

# ===== ضبط الـ Webhook (افتحها مرة واحدة فقط) =====
@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    if not RAILWAY_URL:
        return jsonify({"error": "أضف RAILWAY_PUBLIC_DOMAIN في Variables"}), 400
    webhook_url = f"https://{RAILWAY_URL}/webhook/{BOT_TOKEN}"
    bot.remove_webhook()
    result = bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    return jsonify({"ok": result, "webhook": webhook_url})

# ===== العقارات =====
@app.route("/api/properties", methods=["GET"])
def get_properties():
    try:
        res = supabase.table("properties").select("*").eq("user_id", uid(request)).execute()
        return jsonify(res.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/properties", methods=["POST"])
def add_property():
    try:
        data = request.json
        data["user_id"] = uid(request)
        res = supabase.table("properties").insert(data).execute()
        return jsonify(res.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/properties/<id>", methods=["DELETE"])
def delete_property(id):
    try:
        supabase.table("properties").delete().eq("id", id).eq("user_id", uid(request)).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== الوحدات =====
@app.route("/api/units", methods=["GET"])
def get_units():
    try:
        prop_id = request.args.get("property_id")
        q = supabase.table("units").select("*").eq("user_id", uid(request))
        if prop_id:
            q = q.eq("property_id", prop_id)
        return jsonify(q.execute().data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/units", methods=["POST"])
def add_unit():
    try:
        data = request.json
        data["user_id"] = uid(request)
        res = supabase.table("units").insert(data).execute()
        return jsonify(res.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== المستأجرون =====
@app.route("/api/tenants", methods=["GET"])
def get_tenants():
    try:
        res = supabase.table("tenants").select("*, properties(name, type)").eq("user_id", uid(request)).execute()
        return jsonify(res.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants", methods=["POST"])
def add_tenant():
    try:
        data = request.json
        data["user_id"] = uid(request)
        res = supabase.table("tenants").insert(data).execute()
        supabase.table("units").update({"tenant_name": data["name"]}).eq("property_id", data["property_id"]).eq("unit_num", data["unit_num"]).execute()
        return jsonify(res.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants/<id>/pay", methods=["POST"])
def pay_tenant(id):
    try:
        res = supabase.table("tenants").update({"paid": True}).eq("id", id).eq("user_id", uid(request)).execute()
        return jsonify(res.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tenants/reset", methods=["POST"])
def reset_tenants():
    try:
        supabase.table("tenants").update({"paid": False}).eq("user_id", uid(request)).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== المصروفات =====
@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    try:
        res = supabase.table("expenses").select("*").eq("user_id", uid(request)).order("created_at", desc=True).execute()
        return jsonify(res.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/expenses", methods=["POST"])
def add_expense():
    try:
        data = request.json
        data["user_id"] = uid(request)
        res = supabase.table("expenses").insert(data).execute()
        return jsonify(res.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/expenses/<id>", methods=["DELETE"])
def delete_expense(id):
    try:
        supabase.table("expenses").delete().eq("id", id).eq("user_id", uid(request)).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== الإحصائيات =====
@app.route("/api/stats", methods=["GET"])
def get_stats():
    try:
        u = uid(request)
        props    = supabase.table("properties").select("*").eq("user_id", u).execute()
        tenants  = supabase.table("tenants").select("*").eq("user_id", u).execute()
        expenses = supabase.table("expenses").select("*").eq("user_id", u).execute()
        paid_income = sum(t["rent"] for t in tenants.data if t.get("paid"))
        inv_expense = sum(p.get("investor_rent", 0) for p in props.data if p.get("type") == "مستثمر")
        man_expense = sum(e.get("amount", 0) for e in expenses.data)
        total_exp   = inv_expense + man_expense
        return jsonify({
            "props":    len(props.data),
            "tenants":  len(tenants.data),
            "income":   paid_income,
            "expenses": total_exp,
            "net":      paid_income - total_exp
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== تيليجرام بوت =====
def app_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="🏠 فتح تطبيق مُلّاك", web_app=WebAppInfo(url=MINI_APP_URL)))
    return markup

@bot.message_handler(commands=["start"])
def start(msg):
    name = msg.from_user.first_name
    bot.send_message(msg.chat.id,
        f"🏠 *أهلاً {name} في مُلّاك!*\n\nاضغط الزر أدناه لفتح التطبيق 👇",
        parse_mode="Markdown", reply_markup=app_keyboard())

@bot.message_handler(func=lambda m: True)
def default(msg):
    bot.send_message(msg.chat.id, "👋 اضغط الزر لفتح التطبيق", reply_markup=app_keyboard())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
