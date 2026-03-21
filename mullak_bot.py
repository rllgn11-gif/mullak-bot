import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ===== المفاتيح من متغيرات البيئة =====
BOT_TOKEN   = os.environ.get("BOT_TOKEN", "")
MINI_APP_URL = os.environ.get("MINI_APP_URL", "")
# ========================================

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN غير موجود! أضفه في متغيرات Railway")

bot = telebot.TeleBot(BOT_TOKEN)

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
        f"🏠 *أهلاً {name} في مُلّاك!*\n\n"
        f"نظام إدارة العقارات الذكي 🤖\n\n"
        f"اضغط الزر أدناه لفتح التطبيق 👇",
        parse_mode="Markdown",
        reply_markup=app_keyboard()
    )

@bot.message_handler(func=lambda m: True)
def default(msg):
    bot.send_message(
        msg.chat.id,
        "👋 اضغط الزر لفتح التطبيق",
        reply_markup=app_keyboard()
    )

print("✅ بوت مُلّاك يعمل...")
bot.polling(none_stop=True)
