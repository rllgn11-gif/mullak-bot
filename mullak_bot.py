import telebot
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== المفاتيح =====
BOT_TOKEN = "8706700811:AAGVwfXU_B5HSPyCVvyVPWmJoxZ8_yCdTio"
GEMINI_KEY = "AIzaSyDJkpZE9HQEc8_CDsRvnAgZgZ2A24LZbyc"
# ====================

bot = telebot.TeleBot(BOT_TOKEN)

# قاعدة البيانات
data = {"عقارات": {}, "مستأجرون": {}}

# مؤقت لحفظ البيانات أثناء الإدخال
temp = {}

# ===== Gemini =====
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
        InlineKeyboardButton("🏢 إضافة وحدات", callback_data="add_units"),
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

    # ===== القائمة الرئيسية =====
    if call.data == "main_menu":
        bot.edit_message_text(
            "🏠 *القائمة الرئيسية*\n\nاختر من القائمة 👇",
            chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    # ===== إضافة عقار - الخطوة 1: اسم العقار =====
    elif call.data == "add_property":
        bot.edit_message_text(
            "🏠 *إضافة عقار جديد*\n\n"
            "*الخطوة 1 من 2*\n\n"
            "✏️ أرسل *اسم العقار*:\n\n"
            "مثال: `برج النخيل`",
            chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=back_button()
        )
        bot.register_next_step_handler(call.message, get_property_name)

    # ===== إضافة وحدات - اختيار العقار =====
    elif call.data == "add_units":
        if not data["عقارات"]:
            bot.edit_message_text(
                "❌ *لا يوجد عقارات!*\n\nأضف عقاراً أولاً",
                chat_id, msg_id,
                parse_mode="Markdown",
                reply_markup=back_button()
            )
            return
        markup = InlineKeyboardMarkup(row_width=1)
        for prop in data["عقارات"]:
            markup.add(InlineKeyboardButton(
                f"🏠 {prop}",
                callback_data=f"select_prop_{prop}"
            ))
        markup.add(InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))
        bot.edit_message_text(
            "🏢 *إضافة وحدات*\n\n"
            "اختر العقار المراد إضافة وحدة له:",
            chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    # ===== اختيار نوع الوحدة =====
    elif call.data.startswith("select_prop_"):
        prop_name = call.data.replace("select_prop_", "")
        temp[chat_id] = {"عقار": prop_name}
        markup = InlineKeyboardMarkup(row_width=2)
        unit_types = [
            ("🏢 شقة", "unit_شقة"),
            ("🏠 استديو", "unit_استديو"),
            ("🛏️ غرفة", "unit_غرفة"),
            ("🌴 استراحة", "unit_استراحة"),
            ("🏖️ شاليه", "unit_شاليه"),
            ("🏡 فله", "unit_فله"),
        ]
        for label, cb in unit_types:
            markup.add(InlineKeyboardButton(label, callback_data=cb))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="add_units"))
        bot.edit_message_text(
            f"🏢 *إضافة وحدة في {prop_name}*\n\n"
            f"اختر نوع الوحدة:",
            chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    # ===== تأكيد نوع الوحدة =====
    elif call.data.startswith("unit_"):
        unit_type = call.data.replace("unit_", "")
        prop_name = temp.get(chat_id, {}).get("عقار", "")
        temp[chat_id]["نوع"] = unit_type

        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✅ تأكيد", callback_data="confirm_unit"),
            InlineKeyboardButton("🔙 رجوع", callback_data=f"select_prop_{prop_name}")
        )
        bot.edit_message_text(
            f"🏢 *تأكيد إضافة الوحدة*\n\n"
            f"🏠 العقار: *{prop_name}*\n"
            f"📋 النوع: *{unit_type}*\n\n"
            f"هل تريد تأكيد الإضافة؟",
            chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    # ===== حفظ الوحدة =====
    elif call.data == "confirm_unit":
        prop_name = temp.get(chat_id, {}).get("عقار", "")
        unit_type = temp.get(chat_id, {}).get("نوع", "")
        if prop_name and unit_type:
            if "وحدات" not in data["عقارات"][prop_name]:
                data["عقارات"][prop_name]["وحدات"] = []
            unit_num = len(data["عقارات"][prop_name]["وحدات"]) + 1
            data["عقارات"][prop_name]["وحدات"].append({
                "رقم": unit_num,
                "نوع": unit_type,
                "حالة": "فارغة"
            })
            bot.edit_message_text(
                f"✅ *تم إضافة الوحدة!*\n\n"
                f"🏠 العقار: *{prop_name}*\n"
                f"📋 النوع: *{unit_type}*\n"
                f"🔢 رقم الوحدة: *{unit_num}*",
                chat_id, msg_id,
                parse_mode="Markdown",
                reply_markup=back_button()
            )

    # ===== إضافة مستأجر =====
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

    # ===== تسجيل دفعة =====
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
                f"👤 {tenant_name}\n🏠 {prop}\n💰 {rent} ريال",
                chat_id, msg_id,
                parse_mode="Markdown",
                reply_markup=back_button()
            )

    # ===== التقرير =====
    elif call.data == "report":
        if not data["مستأجرون"]:
            bot.edit_message_text("❌ *لا يوجد بيانات بعد!*", chat_id, msg_id,
                parse_mode="Markdown", reply_markup=back_button())
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
            parse_mode="Markdown", reply_markup=back_button())

    # ===== التذكيرات =====
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
                    parse_mode="Markdown")
                count += 1
        msg_text = "✅ *جميع المستأجرين دفعوا!*" if count == 0 else f"🔔 *تم إرسال {count} تذكير*"
        bot.edit_message_text(msg_text, chat_id, msg_id,
            parse_mode="Markdown", reply_markup=back_button())

    # ===== إعادة تعيين =====
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

    # ===== عرض العقارات =====
    elif call.data == "list_properties":
        if not data["عقارات"]:
            bot.edit_message_text("❌ *لا يوجد عقارات بعد!*", chat_id, msg_id,
                parse_mode="Markdown", reply_markup=back_button())
            return
        text = "🏘️ *قائمة العقارات*\n━━━━━━━━━━━━━━━\n\n"
        for prop, info in data["عقارات"].items():
            text += f"🏠 *{prop}*\n📍 {info['موقع']}\n💰 {info['إيجار']} ريال\n👤 {info['مستأجر']}\n"
            if "وحدات" in info and info["وحدات"]:
                text += f"🏢 الوحدات: {len(info['وحدات'])}\n"
            text += "\n"
        bot.edit_message_text(text, chat_id, msg_id,
            parse_mode="Markdown", reply_markup=back_button())

    # ===== عرض المستأجرين =====
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

    # ===== الذكاء الاصطناعي =====
    elif call.data == "ask":
        bot.edit_message_text(
            "🤖 *اسألني أي شيء عن العقارات*\n\nأرسل سؤالك الآن...",
            chat_id, msg_id,
            parse_mode="Markdown",
            reply_markup=back_button()
        )
        bot.register_next_step_handler(call.message, answer_ai)

    bot.answer_callback_query(call.id)

# ===== إضافة عقار - الخطوة 1: حفظ الاسم =====
def get_property_name(msg):
    chat_id = msg.chat.id
    name = msg.text.strip()
    temp[chat_id] = {"اسم": name}

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))

    bot.send_message(chat_id,
        f"✅ *اسم العقار:* {name}\n\n"
        f"*الخطوة 2 من 2*\n\n"
        f"📍 أرسل *موقع العقار*:\n\n"
        f"مثال: `الرياض - حي النزهة`",
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, get_property_location)

# ===== إضافة عقار - الخطوة 2: حفظ الموقع =====
def get_property_location(msg):
    chat_id = msg.chat.id
    location = msg.text.strip()
    name = temp.get(chat_id, {}).get("اسم", "")

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"))

    bot.send_message(chat_id,
        f"✅ *الموقع:* {location}\n\n"
        f"💰 أرسل *الإيجار الشهري* بالرقم فقط:\n\n"
        f"مثال: `2500`",
        parse_mode="Markdown",
        reply_markup=markup
    )
    temp[chat_id]["موقع"] = location
    bot.register_next_step_handler(msg, get_property_rent)

# ===== إضافة عقار - الخطوة 3: حفظ الإيجار =====
def get_property_rent(msg):
    chat_id = msg.chat.id
    try:
        rent = msg.text.strip()
        int(rent)  # للتأكد أنه رقم
        name = temp[chat_id]["اسم"]
        location = temp[chat_id]["موقع"]

        data["عقارات"][name] = {
            "موقع": location,
            "إيجار": rent,
            "مستأجر": "فارغ",
            "وحدات": []
        }

        bot.send_message(chat_id,
            f"✅ *تم إضافة العقار بنجاح!*\n\n"
            f"🏠 الاسم: *{name}*\n"
            f"📍 الموقع: *{location}*\n"
            f"💰 الإيجار: *{rent} ريال/شهر*",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        del temp[chat_id]
    except:
        bot.send_message(chat_id,
            "❌ *يرجى إرسال رقم فقط!*\n\nمثال: `2500`",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, get_property_rent)

# ===== حفظ المستأجر =====
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

# ===== الذكاء الاصطناعي =====
def answer_ai(msg):
    bot.send_message(msg.chat.id, "⏳ جاري التفكير...")
    prompt = f"أنت مساعد عقاري خبير. أجب بالعربية بشكل مختصر: {msg.text}"
    answer = gemini(prompt)
    bot.send_message(msg.chat.id,
        f"🤖 *الذكاء الاصطناعي:*\n\n{answer}",
        parse_mode="Markdown", reply_markup=main_menu())

# ===== أي رسالة أخرى =====
@bot.message_handler(func=lambda m: True)
def default(msg):
    bot.send_message(msg.chat.id, "👋 اضغط /start لفتح القائمة",
        reply_markup=main_menu())

print("✅ بوت مُلّاك يعمل...")
bot.polling(none_stop=True)
