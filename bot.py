import os
import time
import threading
import requests
import telebot
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

BOT_TOKEN   = os.getenv('BOT_TOKEN')
OWNER_ID    = int(os.getenv('OWNER_ID'))
INTELX_KEY  = os.getenv('INTELX_KEY')
INTELX_BASE = 'https://2.intelx.io'

bot    = telebot.TeleBot(BOT_TOKEN)
admins = [OWNER_ID]

# ──────────────────────────────────────────────
#  HTTP keep-alive
# ──────────────────────────────────────────────
class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'OK')
    def log_message(self, *a): pass

def _start_health():
    port = int(os.getenv('PORT', 8080))
    for p in [port, 8081, 8082, 8083]:
        try:
            HTTPServer(('0.0.0.0', p), _Health).serve_forever()
            break
        except OSError:
            continue

threading.Thread(target=_start_health, daemon=True).start()

# ──────────────────────────────────────────────
#  IntelligenceX API
# ──────────────────────────────────────────────
def intelx_search(query: str, max_results: int = 10):
    """Returns (records, error_msg). On success error_msg is None."""
    if not INTELX_KEY:
        return [], '⚠️ مفتاح INTELX_KEY غير موجود في الإعدادات.'

    headers = {'x-key': INTELX_KEY, 'Content-Type': 'application/json'}
    body = {
        'term': query, 'buckets': [], 'lookuplevel': 0,
        'maxresults': max_results, 'timeout': 0,
        'datefrom': '', 'dateto': '', 'sort': 4,
        'media': 0, 'terminate': []
    }
    try:
        r = requests.post(f'{INTELX_BASE}/intelligent/search',
                          json=body, headers=headers, timeout=15)
        if r.status_code == 401:
            return [], '🔑 مفتاح INTELX_KEY غير صالح أو منتهي الصلاحية.\nتحقق من مفتاحك على intelx.io'
        if r.status_code == 402:
            return [], '💳 رصيد IntelligenceX منتهٍ. يرجى تجديد الاشتراك.'
        r.raise_for_status()
        sid = r.json().get('id')
        if not sid:
            return [], '❌ لم يبدأ البحث — لم يُرجع IntelligenceX معرّف جلسة.'
    except requests.exceptions.Timeout:
        return [], '⏱ انتهت مهلة الاتصال بـ IntelligenceX. حاول مجدداً.'
    except requests.exceptions.ConnectionError:
        return [], '🌐 تعذّر الاتصال بـ IntelligenceX. تحقق من الإنترنت.'
    except Exception as e:
        return [], f'❌ خطأ غير متوقع: {e}'

    time.sleep(3)
    try:
        r2 = requests.get(f'{INTELX_BASE}/intelligent/search/result',
                          params={'id': sid, 'limit': max_results, 'offset': 0},
                          headers=headers, timeout=15)
        r2.raise_for_status()
        records = r2.json().get('records', [])
        return records, None
    except Exception as e:
        return [], f'❌ خطأ عند جلب النتائج: {e}'


def fmt_results(records: list, query: str) -> str:
    if not records:
        return f'❌ لا توجد نتائج للاستعلام:\n<code>{query}</code>'

    lines = [f'🔍 <b>IntelligenceX</b> — {len(records)} نتيجة\n'
             f'🔎 الاستعلام: <code>{query}</code>\n']
    for i, rec in enumerate(records[:10], 1):
        name   = rec.get('name', 'غير معروف')
        bucket = rec.get('bucket', '—')
        date   = (rec.get('date') or '')[:10]
        size   = rec.get('size', 0)
        lines.append(
            f'<b>{i}.</b> 📄 <code>{name}</code>\n'
            f'   🗂 {bucket}  |  📅 {date}  |  📦 {size} B'
        )
    return '\n'.join(lines)

# ──────────────────────────────────────────────
#  Keyboards
# ──────────────────────────────────────────────
DEV_URL = 'https://t.me/OX_U1'

def main_kb():
    m = InlineKeyboardMarkup()
    m.add(InlineKeyboardButton('👨‍💻 تواصل مع المطور', url=DEV_URL))
    return m

# ──────────────────────────────────────────────
#  Welcome message
# ──────────────────────────────────────────────
WELCOME = (
    '🔎 <b>بوت OSINT — مدعوم بـ IntelligenceX</b>\n\n'
    'يبحث هذا البوت في قواعد بيانات مفتوحة المصدر عبر محرك '
    '<b>IntelligenceX</b>.\n\n'
    '📌 <b>ما يمكنك البحث عنه:</b>\n'
    '• 📧 بريد إلكتروني\n'
    '• 📞 رقم هاتف\n'
    '• 👤 اسم مستخدم\n'
    '• 🌐 نطاق / IP\n'
    '• 🪪 أي معرّف آخر\n\n'
    '💡 <b>أرسل أي نص للبحث عنه الآن!</b>'
)

# ──────────────────────────────────────────────
#  Handlers
# ──────────────────────────────────────────────
@bot.message_handler(commands=['start'])
def cmd_start(msg):
    bot.send_message(msg.chat.id, WELCOME, parse_mode='HTML', reply_markup=main_kb())

@bot.message_handler(func=lambda m: True)
def handle_search(msg):
    query = msg.text.strip()
    wait  = bot.send_message(msg.chat.id, '⏳ جارٍ البحث في IntelligenceX...')
    records, err = intelx_search(query)
    if err:
        result = err
    else:
        result = fmt_results(records, query)
    bot.edit_message_text(result, msg.chat.id, wait.message_id,
                          parse_mode='HTML', reply_markup=main_kb())

# ──────────────────────────────────────────────
bot.polling(none_stop=True, interval=0, timeout=20)
