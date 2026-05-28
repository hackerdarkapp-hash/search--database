import os
import threading
import sqlite3
import telebot
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

bot_token = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID'))
api_token = os.getenv('API_TOKEN')

bot = telebot.TeleBot(bot_token)

admins = [OWNER_ID]
moderators = [OWNER_ID]

DEV_BUTTON = InlineKeyboardButton('👨‍💻 المطور', url='https://t.me/OX_U1')

def dev_markup(extra_buttons=None):
    markup = InlineKeyboardMarkup()
    if extra_buttons:
        for btn in extra_buttons:
            markup.add(btn)
    markup.add(DEV_BUTTON)
    return markup

# HTTP keep-alive server for Render
class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, *a): pass

def _run_http():
    port = int(os.getenv('PORT', 8080))
    HTTPServer(('0.0.0.0', port), _Health).serve_forever()

threading.Thread(target=_run_http, daemon=True).start()

conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    search_count INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0
)''')
conn.commit()

def is_admin(user_id): return user_id in admins
def is_moderator(user_id): return user_id in moderators or is_admin(user_id)

def add_user(user_id, username):
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', (user_id, username))
    conn.commit()

def increment_search(user_id):
    cursor.execute('UPDATE users SET search_count = search_count + 1 WHERE user_id=?', (user_id,))
    conn.commit()

def get_search_count(user_id):
    cursor.execute('SELECT search_count FROM users WHERE user_id=?', (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0

def is_banned(user_id):
    cursor.execute('SELECT banned FROM users WHERE user_id=?', (user_id,))
    result = cursor.fetchone()
    return result and result[0] == 1

def set_ban(user_id, status):
    cursor.execute('UPDATE users SET banned=? WHERE user_id=?', (status, user_id))
    conn.commit()

WELCOME_MSG = (
    '📕 هذا هو OSINT. يتم أخذ جميع القواعد فيه فقط من مصادر مفتوحة.\n'
    '🔎 بالمعنى القانوني، هذه الخدمة هي ببساطة محرك بحث، مثل Google أو Yandex.\n'
    '🌐 كل نتيجة توفرها متوفرة على الإنترنت.\n'
    '📋 يقوم الروبوت ببساطة بمعالجة المعلومات ويشكل تقريرًا منظمًا.\n\n'
    '🔎 البيانات التالية متاحة للبحث:\n'
    '📩 بريد إلكتروني:      27,246,956,626\n'
    '👤 الاسم الكامل:       14,309,721,736\n'
    '🔑 كلمة المرور:        13,407,751,390\n'
    '📞 الهاتف:             12,976,487,697\n'
    '👤 نيك:                 10,931,636,063\n'
    '🃏 رقم الوثيقة:         5,047,406,184\n'
    '🔗 وصلة:               2,499,158,371\n'
    '🆔 VK ID:              1,829,380,060\n'
    '🎯 IP:                  983,070,616\n'
    '🏢 اسم الشركة:          811,342,458\n'
    'ⓕ Facebook ID:        723,518,650\n'
    '🔢 SSN:                651,660,040\n'
    '🚘 رقم السيارة:         524,204,448\n'
    '👨 اسم الأب:            421,013,300\n'
    '✎️ برقية:              157,453,748\n'
    '👾 تطبيق:              143,795,450\n'
    '🌐 اختصاص:             84,443,741\n'
    '📷 معرف حساب التواصل الاجتماعي\n\n'
    '💡 أرسل أي بيانات للبحث عنها!'
)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or 'NoUsername'
    add_user(user_id, username)
    bot.send_message(message.chat.id, WELCOME_MSG, reply_markup=dev_markup())

@bot.message_handler(commands=['panel'])
def open_panel(message):
    if not is_moderator(message.from_user.id):
        bot.reply_to(message, '❌ ليس لديك صلاحية', reply_markup=dev_markup())
        return
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton('📢 رسالة جماعية', callback_data='menu_broadcast'),
        InlineKeyboardButton('🔍 بحث مستخدم', callback_data='menu_search'),
        InlineKeyboardButton('🚫 التشويش', callback_data='menu_ban'),
        InlineKeyboardButton('👥 إدارة المشرفين', callback_data='menu_mods'),
        InlineKeyboardButton('⚙️ الإعدادات', callback_data='menu_settings'),
        InlineKeyboardButton('📊 الإحصائيات', callback_data='show_stats')
    )
    markup.add(DEV_BUTTON)
    bot.send_message(message.chat.id, '📋 لوحة التحكم:', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def panel_actions(call):
    if not is_moderator(call.from_user.id):
        bot.answer_callback_query(call.id, '❌ لا تملك صلاحية')
        return
    if call.data == 'show_stats':
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM users WHERE banned=1')
        banned_users = cursor.fetchone()[0]
        cursor.execute('SELECT SUM(search_count) FROM users')
        total_searches = cursor.fetchone()[0] or 0
        stats_text = (
            f'📊 إحصائيات البوت:\n\n'
            f'👥 عدد المستخدمين: {total_users}\n'
            f'🚫 عدد المشوشين: {banned_users}\n'
            f'🔎 إجمالي الطلبات: {total_searches}'
        )
        markup = InlineKeyboardMarkup()
        markup.add(DEV_BUTTON)
        bot.edit_message_text(stats_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif call.data == 'back_main':
        open_panel(call.message)

@bot.message_handler(func=lambda m: True)
def handle_search(message):
    user_id = message.from_user.id
    username = message.from_user.username or 'NoUsername'
    add_user(user_id, username)
    if is_banned(user_id):
        bot.send_message(message.chat.id, '🚫 حسابك مشوش، لا يمكنك البحث', reply_markup=dev_markup())
        return
    increment_search(user_id)
    count = get_search_count(user_id)
    if count > 10:
        bot.send_message(message.chat.id, '⚠️ تجاوزت الحد المجاني (10 مرات)', reply_markup=dev_markup())
        return
    bot.send_message(message.chat.id, f'🔎 نتيجة البحث: {message.text}', reply_markup=dev_markup())

bot.polling(none_stop=True, interval=0, timeout=20)