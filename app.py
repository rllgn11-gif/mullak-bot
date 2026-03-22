import os
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

app = Flask(__name__)
CORS(app)

# ===== المفاتيح =====
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
MINI_APP_URL = os.environ.get("MINI_APP_URL", "https://rllgn11-gif.github.io/mullak-bot/")
# ====================

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = telebot.TeleBot(BOT_TOKEN)

# ===== مساعد =====
def uid(req):
    return req.headers.get("X-User-Id", "anonymous")

# ===== العقارات =====
@app.route("/api/properties", methods=["GET"])
def get_properties():
    res = supabase.table("properties").select("*").eq("user_id", uid(request)).execute()
    return jsonify(res.data)

@app.route("/api/properties", methods=["POST"])
def add_property():
    data = request.json
    data["user_id"] = uid(request)
    res = supabase.table("properties").insert(data).execute()
    return jsonify(res.data[0])

@app.route("/api/properties/<id>", methods=["DELETE"])
def delete_property(id):
    supabase.table("properties").delete().eq("id", id).eq("user_id", uid(request)).execute()
    return jsonify({"ok": True})

# ===== الوحدات =====
@app.route("/api/units", methods=["GET"])
def get_units():
    prop_id = request.args.get("property_id")
    q = supabase.table("units").select("*").eq("user_id", uid(request))
    if prop_id:
        q = q.eq("property_id", prop_id)
    return jsonify(q.execute().data)

@app.route("/api/units", methods=["POST"])
def add_unit():
    data = request.json
    data["user_id"] = uid(request)
    res = supabase.table("units").insert(data).execute()
    return jsonify(res.data[0])

# ===== المستأجرون =====
@app.route("/api/tenants", methods=["GET"])
def get_tenants():
    res = supabase.table("tenants").select("*, properties(name, type)").eq("user_id", uid(request)).execute()
    return jsonify(res.data)

@app.route("/api/tenants", methods=["POST"])
def add_tenant():
    data = request.json
    data["user_id"] = uid(request)
    res = supabase.table("tenants").insert(data).execute()
    supabase.table("units").update({"tenant_name": data["name"]}).eq("property_id", data["property_id"]).eq("unit_num", data["unit_num"]).execute()
    return jsonify(res.data[0])

@app.route("/api/tenants/<id>/pay", methods=["POST"])
def pay_tenant(id):
    res = supabase.table("tenants").update({"paid": True}).eq("id", id).eq("user_id", uid(request)).execute()
    return jsonify(res.data[0])

@app.route("/api/tenants/reset", methods=["POST"])
def reset_tenants():
    supabase.table("tenants").update({"paid": False}).eq("user_id", uid(request)).execute()
    return jsonify({"ok": True})

# ===== المصروفات =====
@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    res = supabase.table("expenses").select("*").eq("user_id", uid(request)).order("created_at", desc=True).execute()
    return jsonify(res.data)

@app.route("/api/expenses", methods=["POST"])
def add_expense():
    data = request.json
    data["user_id"] = uid(request)
    res = supabase.table("expenses").insert(data).execute()
    return jsonify(res.data[0])

@app.route("/api/expenses/<id>", methods=["DELETE"])
def delete_expense(id):
    supabase.table("expenses").delete().eq("id", id).eq("user_id", uid(request)).execute()
    return jsonify({"ok": True})

# ===== الإحصائيات =====
@app.route("/api/stats", methods=["GET"])
def get_stats():
    u = uid(request)
    props    = supabase.table("properties").select("*").eq("user_id", u).execute()
    tenants  = supabase.table("tenants").select("*").eq("user_id", u).execute()
    expenses = supabase.table("expenses").select("*").eq("user_id", u).execute()
    paid_income = sum(t["rent"] for t in tenants.data if t["paid"])
    inv_expense = sum(p["investor_rent"] for p in props.data if p["type"] == "مستثمر")
    man_expense = sum(e["amount"] for e in expenses.data)
    total_exp   = inv_expense + man_expense
    return jsonify({
        "props":    len(props.data),
        "tenants":  len(tenants.data),
        "income":   paid_income,
        "expenses": total_exp,
        "net":      paid_income - total_exp
    })

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

def run_bot():
    print("✅ بوت مُلّاك يعمل...")
    bot.polling(none_stop=True)

# ===== تشغيل البوت في Thread منفصل =====
if BOT_TOKEN:
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
