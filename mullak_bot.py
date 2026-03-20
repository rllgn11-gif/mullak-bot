import telebot
import requests

# ===== ضع مفاتيحك هنا =====
BOT_TOKEN ="8706700811:AAGVwfXU_B5HSPyCVvyVPWmJoxZ8_yCdTio"
GEMINI_KEY = "AIzaSyDJkpZE9HQEc8_CDsRvnAgZgZ2A24LZbyc"
# ===========================

bot = telebot.TeleBot(BOT_TOKEN)

# قاعدة البيانات
data = {"عقارات": {}, "مستأجرون": {}}

# ===== Gemini AI =====
def gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, json=body, timeout=15)
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        return "عذراً، حدث خطأ في الذكاء الاصطناعي"

# ===== START =====
@bot.message_handler(commands=["start"])
def start(msg):
    name = msg.from_user.first_name
    bot.send_message(msg.chat.id, f"""
🏠 أهلاً {name} في بوت مُلّاك!

أنا مساعدك الذكي لإدارة عقاراتك 🤖

📋 الأوامر:
/add_property - إضافة عقار جديد
/add_tenant - إضافة مستأجر
/paid - تسجيل دفعة إيجار
/report - التقرير الشهري
/reminders - إرسال تذكيرات
/reset - إعادة تعيين الدفعات
/ask - اسأل الذكاء الاصطناعي
""")

# ===== إضافة عقار =====
@bot.message_handler(commands=["add_property"])
def add_property(msg):
    bot.send_message(msg.chat.id,
        "🏠 أرسل بيانات العقار:\n\n"
        "الاسم - الموقع - الإيجار\n\n"
        "مثال:\nشقة 1 - الرياض - 2000"
    )
    bot.register_next_step_handler(msg, save_property)

def save_property(msg):
    try:
        parts = msg.text.split("-")
        name = parts[0].strip()
        location = parts[1].strip()
        rent = parts[2].strip()
        data["عقارات"][name] = {
            "موقع": location,
            "إيجار": rent,
            "مستأجر": "فارغ"
        }
        bot.send_message(msg.chat.id,
            f"✅ تم إضافة العقار!\n\n"
            f"🏠 {name}\n"
            f"📍 {location}\n"
            f"💰 {rent} ريال/شهر"
        )
    except:
        bot.send_message(msg.chat.id, "❌ خطأ! حاول مرة ثانية\n/add_property")

# ===== إضافة مستأجر =====
@bot.message_handler(commands=["add_tenant"])
def add_tenant(msg):
    if not data["عقارات"]:
        bot.send_message(msg.chat.id, "❌ أضف عقاراً أولاً!\n/add_property")
        return
    props = "\n".join([f"• {p}" for p in data["عقارات"].keys()])
    bot.send_message(msg.chat.id,
        f"👤 أرسل بيانات المستأجر:\n\n"
        f"الاسم - الهاتف - اسم العقار\n\n"
        f"العقارات:\n{props}\n\n"
        f"مثال:\nمحمد - 0501234567 - شقة 1"
    )
    bot.register_next_step_handler(msg, save_tenant)

def save_tenant(msg):
    try:
        parts = msg.text.split("-")
        name = parts[0].strip()
        phone = parts[1].strip()
        prop = parts[2].strip()
        data["مستأجرون"][name] = {
            "هاتف": phone,
            "عقار": prop,
            "حالة": "لم يدفع ❌"
        }
        if prop in data["عقارات"]:
            data["عقارات"][prop]["مستأجر"] = name
        bot.send_message(msg.chat.id,
            f"✅ تم إضافة المستأجر!\n\n"
            f"👤 {name}\n"
            f"📱 {phone}\n"
            f"🏠 {prop}"
        )
    except:
        bot.send_message(msg.chat.id, "❌ خطأ! حاول مرة ثانية\n/add_tenant")

# ===== تسجيل دفعة =====
@bot.message_handler(commands=["paid"])
def paid(msg):
    if not data["مستأجرون"]:
        bot.send_message(msg.chat.id, "❌ لا يوجد مستأجرون!")
        return
    tenants = "\n".join([
        f"• {t} - {i['حالة']}"
        for t, i in data["مستأجرون"].items()
    ])
    bot.send_message(msg.chat.id,
        f"💰 من دفع الإيجار؟\n\n{tenants}\n\nأرسل اسم المستأجر:"
    )
    bot.register_next_step_handler(msg, save_payment)

def save_payment(msg):
    name = msg.text.strip()
    if name in data["مستأجرون"]:
        data["مستأجرون"][name]["حالة"] = "دفع ✅"
        prop = data["مستأجرون"][name]["عقار"]
        rent = data["عقارات"][prop]["إيجار"]
        bot.send_message(msg.chat.id,
            f"✅ تم تسجيل دفعة {name}\n"
            f"💰 المبلغ: {rent} ريال"
        )
    else:
        bot.send_message(msg.chat.id, "❌ الاسم غير موجود! تأكد من الاسم بالضبط")

# ===== التقرير =====
@bot.message_handler(commands=["report"])
def report(msg):
    if not data["مستأجرون"]:
        bot.send_message(msg.chat.id, "❌ لا يوجد بيانات بعد!")
        return
    text = "📊 التقرير الشهري\n"
    text += "─" * 20 + "\n\n"
    total = 0
    collected = 0
    for tenant, info in data["مستأجرون"].items():
        prop = info["عقار"]
        rent = int(data["عقارات"][prop]["إيجار"])
        text += f"👤 {tenant}\n🏠 {prop}\n💰 {rent} ريال - {info['حالة']}\n\n"
        total += rent
        if "✅" in info["حالة"]:
            collected += rent
    text += "─" * 20 + "\n"
    text += f"💵 الإجمالي: {total} ريال\n"
    text += f"✅ المحصّل: {collected} ريال\n"
    text += f"❌ المتبقي: {total - collected} ريال"
    bot.send_message(msg.chat.id, text)

# ===== التذكيرات =====
@bot.message_handler(commands=["reminders"])
def reminders(msg):
    if not data["مستأجرون"]:
        bot.send_message(msg.chat.id, "❌ لا يوجد مستأجرون!")
        return
    count = 0
    for tenant, info in data["مستأجرون"].items():
        if "✅" not in info["حالة"]:
            prop = info["عقار"]
            rent = data["عقارات"][prop]["إيجار"]
            bot.send_message(msg.chat.id,
                f"🔔 تذكير!\n\n"
                f"👤 {tenant}\n"
                f"📱 {info['هاتف']}\n"
                f"🏠 {prop}\n"
                f"💰 {rent} ريال لم يُدفع بعد"
            )
            count += 1
    if count == 0:
        bot.send_message(msg.chat.id, "✅ جميع المستأجرين دفعوا!")
    else:
        bot.send_message(msg.chat.id, f"🔔 تم إرسال {count} تذكير")

# ===== إعادة تعيين الدفعات =====
@bot.message_handler(commands=["reset"])
def reset(msg):
    for tenant in data["مستأجرون"]:
        data["مستأجرون"][tenant]["حالة"] = "لم يدفع ❌"
    bot.send_message(msg.chat.id, "✅ تم إعادة تعيين جميع الدفعات للشهر الجديد!")

# ===== الذكاء الاصطناعي =====
@bot.message_handler(commands=["ask"])
def ask(msg):
    bot.send_message(msg.chat.id, "🤖 اسألني أي شيء عن العقارات والإيجارات...")
    bot.register_next_step_handler(msg, answer_ai)

def answer_ai(msg):
    bot.send_message(msg.chat.id, "⏳ جاري التفكير...")
    prompt = f"""أنت مساعد عقاري خبير في السوق العربي.
أجب بالعربية بشكل مختصر ومفيد على هذا السؤال:
{msg.text}"""
    answer = gemini(prompt)
    bot.send_message(msg.chat.id, f"🤖 {answer}")

# ===== أي رسالة أخرى =====
@bot.message_handler(func=lambda m: True)
def default(msg):
    bot.send_message(msg.chat.id, "اكتب /start لرؤية الأوامر 😊")

print("✅ بوت مُلّاك يعمل...")
bot.polling(none_stop=True)
