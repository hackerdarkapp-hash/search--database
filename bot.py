import os
import telebot
import sqlite3
from dotenv import load_dotenv
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# تحميل ملف البيئة
load_dotenv()

bot_token = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
api_token = os.getenv("API_TOKEN")

bot = telebot.TeleBot(bot_token)

admins = [OWNER_ID]
moderators = [OWNER_ID]  # يمكن إضافة مشرفين لاحقًا من لوحة التحكم

DEV_BUTTON = InlineKeyboardButton("👨‍💻 المطور", url="https://t.me/ox_u1")

# قاعدة بيانات SQLite
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    search_count INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0
)
""")
conn.commit()

def is_admin(user_id): return user_id in admins
def is_moderator(user_id): return user_id in moderators or is_admin(user_id)

def add_user(user_id, username):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()

def increment_search(user_id):
    cursor.execute("UPDATE users SET search_count = search_count + 1 WHERE user_id=?", (user_id,))
    conn.commit()

def get_search_count(user_id):
    cursor.execute("SELECT search_count FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0

def is_banned(user_id):
    cursor.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result and result[0] == 1

def set_ban(user_id, status):
    cursor.execute("UPDATE users SET banned=? WHERE user_id=?", (status, user_id))
    conn.commit()

# أمر /start
@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    add_user(user_id, username)
    bot.send_message(message.chat.id, "👋 مرحبًا بك في البوت!\nاستخدم /panel لفتح لوحة التحكم.")

# لوحة التحكم الرئيسية
@bot.message_handler(commands=["panel"])
def open_panel(message):
    if not is_moderator(message.from_user.id):
        bot.reply_to(message, "❌ ليس لديك صلاحية")
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📢 رسالة جماعية", callback_data="menu_broadcast"),
        InlineKeyboardButton("🔍 بحث مستخدم", callback_data="menu_search"),
        InlineKeyboardButton("🚫 التشويش", callback_data="menu_ban"),
        InlineKeyboardButton("👥 إدارة المشرفين", callback_data="menu_mods"),
        InlineKeyboardButton("⚙️ الإعدادات", callback_data="menu_settings"),
        InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")
    )
    bot.send_message(message.chat.id, "📋 لوحة التحكم:", reply_markup=markup)

# التعامل مع القوائم الفرعية + الإحصائيات
@bot.callback_query_handler(func=lambda call: True)
def panel_actions(call):
    if not is_moderator(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ لا تملك صلاحية")
        return
    
    if call.data == "show_stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE banned=1")
        banned_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(search_count) FROM users")
        total_searches = cursor.fetchone()[0] or 0
        
        stats_text = (
            f"📊 إحصائيات البوت:\n\n"
            f"👥 عدد المستخدمين: {total_users}\n"
            f"🚫 عدد المشوشين: {banned_users}\n"
            f"🔎 إجمالي الطلبات: {total_searches}"
        )
        bot.edit_message_text(stats_text, call.message.chat.id, call.message.message_id)
    
    elif call.data == "menu_broadcast":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✍️ نص فقط", callback_data="broadcast_text"),
            InlineKeyboardButton("🖼 نص + صورة", callback_data="broadcast_media"),
            InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")
        )
        bot.edit_message_text("📢 خيارات الرسائل الجماعية:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "menu_search":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🔍 بالآيدي", callback_data="search_id"),
            InlineKeyboardButton("🔍 بالمعرف", callback_data="search_username"),
            InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")
        )
        bot.edit_message_text("🔍 خيارات البحث:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "menu_ban":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🚫 تشويش مستخدم", callback_data="ban_user"),
            InlineKeyboardButton("✅ رفع التشويش", callback_data="unban_user"),
            InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")
        )
        bot.edit_message_text("🚫 إدارة التشويش:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "menu_mods":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("➕ إضافة مشرف", callback_data="add_mod"),
            InlineKeyboardButton("➖ إزالة مشرف", callback_data="remove_mod"),
            InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")
        )
        bot.edit_message_text("👥 إدارة المشرفين:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "menu_settings":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("⚠️ تعديل الحد المجاني", callback_data="set_limit"),
            InlineKeyboardButton("🌐 تغيير اللغة", callback_data="set_lang"),
            InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")
        )
        bot.edit_message_text("⚙️ الإعدادات العامة:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "back_main":
        open_panel(call.message)

# مثال على البحث مع نظام الحد المجاني + زر المطور
@bot.message_handler(func=lambda m: True)
def handle_search(message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    add_user(user_id, username)

    if is_banned(user_id):
        bot.send_message(message.chat.id, "🚫 حسابك مشوش، لا يمكنك البحث")
        return
    
    increment_search(user_id)
    count = get_search_count(user_id)
    
    if count > 10:
        bot.send_message(message.chat.id, "⚠️ تجاوزت الحد المجاني (10 مرات)، الإجابات مشوشة")
        return
    
    markup = InlineKeyboardMarkup().add(DEV_BUTTON)
    bot.send_message(message.chat.id, f"🔎 نتيجة البحث: {message.text}", reply_markup=markup)

bot.polling()
