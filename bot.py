import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

ADMIN_ID = 7089231271
DB_FILE = "users.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "banned": []}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def register_user(user):
    db = load_db()
    db["users"][str(user.id)] = {
        "id": user.id,
        "username": user.username,
        "name": user.first_name
    }
    save_db(db)

def is_banned(user_id):
    db = load_db()
    return user_id in db["banned"]

@bot.message_handler(commands=['start'])
def start(message):
    register_user(message.from_user)

    if is_banned(message.from_user.id):
        return bot.send_message(message.chat.id, "🚫 انت محظور")

    bot.send_message(message.chat.id, "اهلا بك في البوت")

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔍 بحث", callback_data="search"))
    markup.add(InlineKeyboardButton("🚫 حظر", callback_data="ban"))
    markup.add(InlineKeyboardButton("✅ فك الحظر", callback_data="unban"))
    markup.add(InlineKeyboardButton("📊 المستخدمين", callback_data="stats"))

    bot.send_message(message.chat.id, "لوحة التحكم:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.from_user.id != ADMIN_ID:
        return

    if call.data == "search":
        msg = bot.send_message(call.message.chat.id, "ارسل ID او Username:")
        bot.register_next_step_handler(msg, search_user)

    elif call.data == "ban":
        msg = bot.send_message(call.message.chat.id, "ارسل ID:")
        bot.register_next_step_handler(msg, ban_user)

    elif call.data == "unban":
        msg = bot.send_message(call.message.chat.id, "ارسل ID:")
        bot.register_next_step_handler(msg, unban_user)

    elif call.data == "stats":
        db = load_db()
        bot.send_message(call.message.chat.id, f"عدد المستخدمين: {len(db['users'])}")

def search_user(message):
    db = load_db()
    text = message.text.strip()

    for user in db["users"].values():
        if str(user["id"]) == text or (user["username"] and user["username"] == text.replace("@", "")):
            return bot.send_message(
                message.chat.id,
                f"👤 {user['name']}\n🆔 {user['id']}\n📛 @{user['username']}"
            )

    bot.send_message(message.chat.id, "❌ غير موجود")

def ban_user(message):
    db = load_db()
    user_id = int(message.text)

    if user_id not in db["banned"]:
        db["banned"].append(user_id)
        save_db(db)
        bot.send_message(message.chat.id, "✅ تم الحظر")
    else:
        bot.send_message(message.chat.id, "⚠️ محظور مسبقا")

def unban_user(message):
    db = load_db()
    user_id = int(message.text)

    if user_id in db["banned"]:
        db["banned"].remove(user_id)
        save_db(db)
        bot.send_message(message.chat.id, "✅ تم فك الحظر")
    else:
        bot.send_message(message.chat.id, "❌ غير محظور")

bot.infinity_polling()
