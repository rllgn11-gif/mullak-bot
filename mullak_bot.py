import telebot
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== ضع مفاتيحك هنا =====
BOT_TOKEN = "8706700811:AAGVwfXU_B5HSPyCVvyVPWmJoxZ8_yCdTio"
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

# ===== القائمة الرئيسية =====
def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🏠 إضافة عقار", callback_data="add_property"),
        InlineKeyboardButton("👤 إضافة مستأجر", callback_data="add_tenant"),
        InlineKeyboardButton("💰 تسجيل دفعة", callback_data="paid"),
        InlineKeyboardButton("📊 التقرير الشهري", callback_data="report"),
        InlineKeyboardButton("🔔 إرسال تذكيرات", callback_data="reminders"),
        InlineKeyboardButton("🔄 شهر جديد", callback_data="reset"),
        InlineKeyboardButton("🏘️ عرض العقارات", callback_data="list_properties"),
        InlineKeyboardButton("👥 عرض المستأجرين", callback_data="list_tenants"),
    )
    markup.add(InlineKeyboardButton("🤖 اسأل الذكاء الاصطناعي", callback_data="ask"))
    return markup

def back_button():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
    return markup

# ===== START =====
@bot.message_handler(commands=["start"])
def start(msg):
    name = msg.from_user.first_name
    bot.send_message(msg.chat.id,
        f"🏠 *أهلاً {name} في بوت مُلّاك!*\n\n"
        f"مساعدك الذكي لإدارة العقارات 🤖\n\n"
        f"اختر من القائمة 👇",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ===== معالج الأزرار =====
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if call.data == "main_menu":
        bot.edit_message_text(
            "🏠 *القائمة الرئيسية*\n\nاختر من القائمة 👇",
            chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    elif call.data == "add_property":
        bot.edit_message_text(
            "🏠 *إضافة عقار جديد*\n\n"
            "أرسل البيانات:\n\n"
            "`الاسم - الموقع - الإيجار`\n\n"
            "مثال:\n`شقة 1 - الرياض - 2000`",
            chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=back_button()
        )
        bot.register_next_step_handler(call.message, save_property)

    elif call.data == "add_tenant":
        if not data["عقارات"]:
            bot.edit_message_text(
                "❌ *لا يوجد عقارات!*\n\nأضف عقاراً أولاً",
                chat_id, msg_id,
                parse_mode="Markdown",
                reply_markup=back_button()
            )
            return
        props = "\n".join([f"• `{p}`" for p in data["عقارات"].keys()])
        bot.edit_message_text(
            f"👤 *إضافة مستأجر جديد*\n\n"
            f"أرسل البيانات:\n\n"
            f"`الاسم - الهاتف - اسم العقار`\n\n"
            f"العقارات:\n{props}\n\n"
            f"مثال:\n`محمد - 0501234567 - شقة 1`",
            chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=back_button()
        )
        bot.register_next_step_handler(call.message, save_tenant)

    elif call.data == "paid":
        if not data["مستأجرون"]:
            bot.edit_message_text(
                "❌ *لا يوجد مستأجرون!*",
                chat_id, msg_id,
                parse_mode="Markdown",
                reply_markup=back_button()
            )
            return
        markup = InlineKeyboardMarkup(row_width=2)
        for tenant in data["مستأجرون"]:
            status = "✅" if "✅" in data["مستأجرون"][tenant]["حالة"] else "❌"
            markup.add(InlineKeyboardButton(
                f"{status} {tenant}",
                callback_data=f"pay_{tenant}"
            ))
        markup.add(InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
        bot.edit_message_text(
            "💰 *تسجيل دفعة إيجار*\n\nاختر المستأجر الذي دفع:",
            chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    elif call.data.startswith("pay_"):
        tenant_name = call.data.replace("pay_", "")
        if tenant_name in data["مستأجرون"]:
            data["مستأجرون"][tenant_name]["حالة"] = "دفع ✅"
            prop = data["مستأجرون"][tenant_name]["عقار"]
            rent = data["عقارات"][prop]["إيجار"]
            bot.edit_message_text(
                f"✅ *تم تسجيل الدفعة!*\n\n"
                f"👤 {tenant_name}\n"
                f"🏠 {prop}\n"
                f"💰 {rent} ريال",
                chat_id, msg_id,
                parse_mode="Markdown",
                reply_markup=back_button()
            )

    elif call.data == "report":
        if not data["مستأجرون"]:
            bot.edit_message_text(
                "❌ *لا يوجد بيانات بعد!*",
                chat_id, msg_id,
                parse_mode="Markdown",
                reply_markup=back_button()
            )
            return
        text = "📊 *التقرير الشهري*\n━━━━━━━━━━━━━━━\n\n"
        total = 0
        collected = 0
        for tenant, info in data["مستأجرون"].items():
            prop = info["عقار"]
            rent = int(data["عقارات"][prop]["إيجار"])
            text += f"👤 *{tenant}*\n🏠 {prop}\n💰 {rent} ريال — {info['حالة']}\n\n"
            total += rent
            if "✅" in info["حالة"]:
                collected += rent
        text += "━━━━━━━━━━━━━━━\n"
        text += f"💵 الإجمالي: *{total} ريال*\n"
        text += f"✅ المحصّل: *{collected} ريال*\n"
        text += f"❌ المتبقي: *{total - collected} ريال*"
        bot.edit_message_text(text, chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=back_button()
        )

    elif call.data == "reminders":
        if not data["مستأجرون"]:
            bot.edit_message_text("❌ *لا يوجد مستأجرون!*", chat_id, msg_id,
                parse_mode="Markdown", reply_markup=back_button())
            return
        count = 0
        for tenant, info in data["مستأجرون"].items():
            if "✅" not in info["حالة"]:
                prop = info["عقار"]
                rent = data["عقارات"][prop]["إيجار"]
                bot.send_message(chat_id,
                    f"🔔 *تذكير إيجار*\n\n"
                    f"👤 {tenant}\n📱 {info['هاتف']}\n🏠 {prop}\n💰 {rent} ريال لم يُدفع",
                    parse_mode="Markdown"
                )
                count += 1
        msg_text = "✅ *جميع المستأجرين دفعوا!*" if count == 0 else f"🔔 *تم إرسال {count} تذكير*"
        bot.edit_message_text(msg_text, chat_id, msg_id,
            parse_mode="Markdown", reply_markup=back_button())

    elif call.data == "reset":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ تأكيد", callback_data="confirm_reset"),
            InlineKeyboardButton("❌ إلغاء", callback_data="main_menu")
        )
        bot.edit_message_text(
            "⚠️ *هل تريد بدء شهر جديد؟*\n\nسيتم إعادة تعيين جميع الدفعات",
            chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    elif call.data == "confirm_reset":
        for tenant in data["مستأجرون"]:
            data["مستأجرون"][tenant]["حالة"] = "لم يدفع ❌"
        bot.edit_message_text("✅ *تم بدء الشهر الجديد!*", chat_id, msg_id,
            parse_mode="Markdown", reply_markup=back_button())

    elif call.data == "list_properties":
        if not data["عقارات"]:
            bot.edit_message_text("❌ *لا يوجد عقارات بعد!*", chat_id, msg_id,
                parse_mode="Markdown", reply_markup=back_button())
            return
        text = "🏘️ *قائمة العقارات*\n━━━━━━━━━━━━━━━\n\n"
        for prop, info in data["عقارات"].items():
            text += f"🏠 *{prop}*\n📍 {info['موقع']}\n💰 {info['إيجار']} ريال\n👤 {info['مستأجر']}\n\n"
        bot.edit_message_text(text, chat_id, msg_id,
            parse_mode="Markdown", reply_markup=back_button())

    elif call.data == "list_tenants":
        if not data["مستأجرون"]:
            bot.edit_message_text("❌ *لا يوجد مستأجرون بعد!*", chat_id, msg_id,
                parse_mode="Markdown", reply_markup=back_button())
            return
        text = "👥 *قائمة المستأجرين*\n━━━━━━━━━━━━━━━\n\n"
        for tenant, info in data["مستأجرون"].items():
            text += f"👤 *{tenant}*\n📱 {info['هاتف']}\n🏠 {info['عقار']}\n💳 {info['حالة']}\n\n"
        bot.edit_message_text(text, chat_id, msg_id,
            parse_mode="Markdown", reply_markup=back_button())

    elif call.data == "ask":
        bot.edit_message_text(
            "🤖 *اسألني أي شيء عن العقارات*\n\nأرسل سؤالك الآن...",
            chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=back_button()
        )
        bot.register_next_step_handler(call.message, answer_ai)

    bot.answer_callback_query(call.id)

def save_property(msg):
    try:
        parts = msg.text.split("-")
        name = parts[0].strip()
        location = parts[1].strip()
        rent = parts[2].strip()
        data["عقارات"][name] = {"موقع": location, "إيجار": rent, "مستأجر": "فارغ"}
        bot.send_message(msg.chat.id,
            f"✅ *تم إضافة العقار!*\n\n🏠 {name}\n📍 {location}\n💰 {rent} ريال/شهر",
            parse_mode="Markdown", reply_markup=main_menu())
    except:
        bot.send_message(msg.chat.id,
            "❌ *خطأ!* تأكد من الشكل:\n`الاسم - الموقع - الإيجار`",
            parse_mode="Markdown", reply_markup=main_menu())

def save_tenant(msg):
    try:
        parts = msg.text.split("-")
        name = parts[0].strip()
        phone = parts[1].strip()
        prop = parts[2].strip()
        data["مستأجرون"][name] = {"هاتف": phone, "عقار": prop, "حالة": "لم يدفع ❌"}
        if prop in data["عقارات"]:
            data["عقارات"][prop]["مستأجر"] = name
        bot.send_message(msg.chat.id,
            f"✅ *تم إضافة المستأجر!*\n\n👤 {name}\n📱 {phone}\n🏠 {prop}",
            parse_mode="Markdown", reply_markup=main_menu())
    except:
        bot.send_message(msg.chat.id,
            "❌ *خطأ!* تأكد من الشكل:\n`الاسم - الهاتف - العقار`",
            parse_mode="Markdown", reply_markup=main_menu())

def answer_ai(msg):
    bot.send_message(msg.chat.id, "⏳ جاري التفكير...")
    prompt = f"أنت مساعد عقاري خبير. أجب بالعربية بشكل مختصر: {msg.text}"
    answer = gemini(prompt)
    bot.send_message(msg.chat.id,
        f"🤖 *الذكاء الاصطناعي:*\n\n{answer}",
        parse_mode="Markdown", reply_markup=main_menu())

@bot.message_handler(func=lambda m: True)
def default(msg):
    bot.send_message(msg.chat.id, "👋 اضغط /start لفتح القائمة",
        reply_markup=main_menu())

print("✅ بوت مُلّاك يعمل...")
bot.polling(none_stop=True)
