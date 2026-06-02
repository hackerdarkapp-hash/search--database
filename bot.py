import os
import requests
import tempfile
import threading
import html as html_lib
from random import randint
from datetime import datetime

try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
except ModuleNotFoundError:
    import subprocess
    subprocess.run(["pip", "install", "pyTelegramBotAPI"], check=True)
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

url = "https://leakosintapi.com/"
bot_token = os.environ.get("BOT_TOKEN", "")
api_token = os.environ.get("API_TOKEN", "")
lang = "ru"
limit = 9999        # أقصى عدد ممكن من النتائج — لا يُحذف شيء

DEVELOPER_TEXT = "👨‍💻 المطور"
DEVELOPER_URL = "https://t.me/OX_U1"
PAGE_SIZE = 3000
API_TIMEOUT = 90    # ثانية — وقت كافٍ للاستجابات الكبيرة
DB_BTNS_PER_PAGE = 9   # 3 صفوف × 3 أزرار — أزرار قواعد البيانات الظاهرة في كل مرة

def user_access_test(user_id):
    return True

# cash_data[str(query_id)] = {
#   "db_names": [name1, name2, ...],
#   "db_pages": { name1: [page_text, ...], name2: [...], ... },
#   "raw": { name1: {...}, name2: {...} },
#   "query": str
# }
cash_data = {}

# ─── helpers ──────────────────────────────────────────────────────────────────

def build_db_text(database_name, db_data):
    lines = [f"<b>📂 {database_name}</b>"]
    info = db_data.get("InfoLeak", "")
    if info:
        lines.append(info)
    lines.append("")
    if database_name != "No results found":
        for record in db_data.get("Data", []):
            for col, val in record.items():
                lines.append(f"<b>{col}</b>: {val}")
            lines.append("")
    return "\n".join(lines).strip()

def split_into_pages(text, page_size=PAGE_SIZE):
    if len(text) <= page_size:
        return [text]
    pages, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > page_size:
            if current:
                pages.append(current.strip())
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        pages.append(current.strip())
    return pages

def generate_html(query, raw_data):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_results = sum(len(db.get("Data", [])) for db in raw_data.values())
    rows = ""
    for db_name, db_data in raw_data.items():
        info = html_lib.escape(db_data.get("InfoLeak", ""))
        num  = db_data.get("NumOfResults", len(db_data.get("Data", [])))
        rows += f"""
        <tr class="db-header"><td colspan="2">📂 {html_lib.escape(db_name)} <span class="badge">{num} نتيجة</span></td></tr>
        <tr class="db-info"><td colspan="2">{info}</td></tr>
        """
        for record in db_data.get("Data", []):
            for col, val in record.items():
                rows += f"""
        <tr>
            <td class="col-name">{html_lib.escape(str(col))}</td>
            <td class="col-val">{html_lib.escape(str(val))}</td>
        </tr>"""
            rows += '<tr class="spacer"><td colspan="2"></td></tr>'

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>نتائج البحث: {html_lib.escape(query)}</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:'Segoe UI',Arial,sans-serif;background:#0f0f0f;color:#e0e0e0;margin:0;padding:0}}
  .top-banner{{background:linear-gradient(135deg,#0d2233,#1a3a4a);border-bottom:2px solid #00d4ff;padding:18px 24px;text-align:center}}
  .top-banner p{{margin:6px 0;font-size:.95rem;color:#cce8ff}}
  .top-banner a{{color:#00d4ff;font-weight:bold;text-decoration:none}}
  .top-banner a:hover{{text-decoration:underline}}
  .container{{padding:20px}}
  h1{{color:#00d4ff;text-align:center;font-size:1.4rem;margin-bottom:4px}}
  .meta{{text-align:center;color:#888;font-size:.85rem;margin-bottom:20px}}
  table{{width:100%;border-collapse:collapse}}
  tr.db-header td{{background:#1a3a4a;color:#00d4ff;font-weight:bold;padding:10px 14px;font-size:1rem;border-top:2px solid #00d4ff}}
  .badge{{background:#00d4ff;color:#000;font-size:.7rem;padding:2px 7px;border-radius:10px;margin-right:8px;float:left}}
  tr.db-info td{{background:#111;color:#aaa;font-size:.8rem;padding:4px 14px 8px;font-style:italic}}
  tr:not(.db-header):not(.db-info):not(.spacer) td{{padding:6px 14px;border-bottom:1px solid #222}}
  td.col-name{{color:#7ecfff;font-weight:600;width:35%}}
  td.col-val{{color:#e0e0e0;word-break:break-all}}
  tr.spacer td{{height:10px}}
  tr:hover:not(.db-header):not(.db-info):not(.spacer){{background:#1a1a1a}}
</style>
</head>
<body>
<div class="top-banner">
  <p>🤖 هذا الملف صادر من بوت البحث في قواعد البيانات</p>
  <p>👨‍💻 مطور البوت يستقبل استفساراتكم وطلباتكم عبر تيليغرام:
    <a href="{DEVELOPER_URL}" target="_blank">{DEVELOPER_URL}</a>
  </p>
</div>
<div class="container">
<h1>🕵️ نتائج البحث</h1>
<div class="meta">الطلب: <b>{html_lib.escape(query)}</b> — {now} — إجمالي النتائج: <b>{total_results}</b></div>
<table>{rows}</table>
</div>
</body></html>"""

# ─── report generator ─────────────────────────────────────────────────────────

def generate_report(query, query_id):
    global cash_data
    try:
        data = {"token": api_token, "request": query.split("\n")[0], "limit": limit, "lang": lang}
        response = requests.post(url, json=data, timeout=API_TIMEOUT).json()
        print(response)

        if not isinstance(response, dict):
            return None
        if "Error code" in response:
            print("خطأ: " + str(response["Error code"]))
            return None
        if "List" not in response or not response["List"]:
            cash_data[str(query_id)] = {
                "db_names": ["no_results"],
                "db_pages": {"no_results": ["🔍 لم يتم العثور على نتائج لهذا الطلب."]},
                "raw": {},
                "query": query
            }
            return True

        raw = response["List"]
        db_names = list(raw.keys())
        db_pages = {}
        for db_name in db_names:
            text = build_db_text(db_name, raw[db_name])
            db_pages[db_name] = split_into_pages(text)

        cash_data[str(query_id)] = {
            "db_names": db_names,
            "db_pages": db_pages,
            "raw": raw,
            "query": query
        }
        return True

    except requests.exceptions.Timeout:
        print(f"انتهت مهلة الاتصال بـ API بعد {API_TIMEOUT} ثانية")
        return None
    except Exception as e:
        print(f"خطأ في generate_report: {e}")
        return None

# ─── keyboards ────────────────────────────────────────────────────────────────

def create_result_keyboard(query_id, db_idx, inner_page, db_names, db_pages, btn_page=0):
    """
    db_idx     — رقم قاعدة البيانات الحالية
    inner_page — رقم الصفحة الداخلية لتلك القاعدة
    btn_page   — رقم صفحة أزرار القفز (عند كثرتها)
    """
    markup = InlineKeyboardMarkup()
    total_dbs = len(db_names)

    # --- أزرار قواعد البيانات مع ترقيم صفحاتها ---
    if total_dbs > 1:
        total_btn_pages = (total_dbs + DB_BTNS_PER_PAGE - 1) // DB_BTNS_PER_PAGE
        btn_page = max(0, min(btn_page, total_btn_pages - 1))

        start = btn_page * DB_BTNS_PER_PAGE
        end   = min(start + DB_BTNS_PER_PAGE, total_dbs)
        slice_btns = []
        for i in range(start, end):
            name  = db_names[i]
            short = name[:18] + "…" if len(name) > 18 else name
            if i == db_idx:
                short = f"• {short} •"
            slice_btns.append(
                InlineKeyboardButton(
                    text=short,
                    callback_data=f"/db {query_id} {i} 0 {btn_page}"
                )
            )
        for i in range(0, len(slice_btns), 3):
            markup.row(*slice_btns[i:i+3])

        # تنقل بين صفحات الأزرار (يظهر فقط إذا كانت الأزرار أكثر من صفحة)
        if total_btn_pages > 1:
            prev_bp = (btn_page - 1) % total_btn_pages
            next_bp = (btn_page + 1) % total_btn_pages
            markup.row(
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=f"/db {query_id} {db_idx} {inner_page} {prev_bp}"
                ),
                InlineKeyboardButton(
                    text=f"📋 {btn_page + 1} / {total_btn_pages}",
                    callback_data="noop"
                ),
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=f"/db {query_id} {db_idx} {inner_page} {next_bp}"
                )
            )

    # --- تنقل داخلي لصفحات قاعدة البيانات الحالية ---
    current_db_name = db_names[db_idx]
    total_inner = len(db_pages.get(current_db_name, []))
    if total_inner > 1:
        markup.row(
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"/db {query_id} {db_idx} {(inner_page - 1) % total_inner} {btn_page}"
            ),
            InlineKeyboardButton(
                text=f"📄 {inner_page + 1} / {total_inner}",
                callback_data="noop"
            ),
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"/db {query_id} {db_idx} {(inner_page + 1) % total_inner} {btn_page}"
            )
        )

    # --- تحميل النتائج كاملة ---
    markup.row(
        InlineKeyboardButton(text="📥 تحميل النتائج كاملة", callback_data=f"/download {query_id}")
    )

    # --- زر المطور ---
    markup.row(
        InlineKeyboardButton(text=DEVELOPER_TEXT, url=DEVELOPER_URL)
    )
    return markup

def create_main_menu():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(text="⚙️API", callback_data="menu_api"),
        InlineKeyboardButton(text="📝البحث الجماعي", callback_data="menu_bulk_search")
    )
    markup.row(
        InlineKeyboardButton(text="📋قائمة القواعد", callback_data="menu_db_list"),
        InlineKeyboardButton(text="جابات على الأسئلة المتكررة", callback_data="menu_faq")
    )
    markup.row(
        InlineKeyboardButton(text="💵سحب الأموال", callback_data="menu_withdraw"),
        InlineKeyboardButton(text="💰تجديد التوازن", callback_data="menu_topup")
    )
    markup.row(
        InlineKeyboardButton(text="💎إنشاء مرآة", callback_data="menu_mirror"),
        InlineKeyboardButton(text="👥نظام المرتد", callback_data="menu_referral")
    )
    markup.row(
        InlineKeyboardButton(text="🎁إعطاء اشتراك", callback_data="menu_gift"),
        InlineKeyboardButton(text="🚫حذف نفسك", callback_data="menu_delete")
    )
    markup.row(InlineKeyboardButton(text="🛠الدعم الفني", callback_data="menu_support"))
    markup.row(InlineKeyboardButton(text="↩️خلف", callback_data="menu_back"))
    return markup

# ─── send helpers ─────────────────────────────────────────────────────────────

def send_db_page(chat_id, query_id, db_idx, inner_page, btn_page=0, edit_msg_id=None):
    entry = cash_data.get(str(query_id))
    if not entry:
        bot.send_message(chat_id, "⏰ انتهت صلاحية النتائج، أرسل طلبك مجدداً.")
        return

    db_names = entry["db_names"]
    db_pages = entry["db_pages"]

    db_idx = max(0, min(db_idx, len(db_names) - 1))
    current_db = db_names[db_idx]
    pages = db_pages.get(current_db, [""])
    inner_page = inner_page % len(pages)
    text = pages[inner_page]

    # إذا كان btn_page لا يحتوي الزر النشط، انتقل تلقائياً لصفحته
    total_btn_pages = max(1, (len(db_names) + DB_BTNS_PER_PAGE - 1) // DB_BTNS_PER_PAGE)
    correct_btn_page = db_idx // DB_BTNS_PER_PAGE
    # إذا طلب المستخدم صفحة أزرار محددة نستخدمها، وإلا نعرض صفحة الزر النشط
    btn_page = max(0, min(btn_page, total_btn_pages - 1))

    markup = create_result_keyboard(query_id, db_idx, inner_page, db_names, db_pages, btn_page)

    def _safe_text(t):
        return t.replace("<b>", "").replace("</b>", "")

    if edit_msg_id:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=edit_msg_id,
                                  text=text, parse_mode="html", reply_markup=markup)
        except telebot.apihelper.ApiTelegramException:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=edit_msg_id,
                                      text=_safe_text(text), reply_markup=markup)
            except Exception:
                pass
    else:
        try:
            bot.send_message(chat_id, text, parse_mode="html", reply_markup=markup)
        except telebot.apihelper.ApiTelegramException:
            bot.send_message(chat_id, _safe_text(text), reply_markup=markup)

# ─── bot handlers ─────────────────────────────────────────────────────────────

bot = telebot.TeleBot(bot_token)

@bot.message_handler(commands=["start"])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "🕵️ يمكنني البحث عن كل شيء تقريباً. فقط أرسل لي طلبك.",
        reply_markup=create_main_menu()
    )

@bot.message_handler(func=lambda message: message.text and not message.text.startswith("/"))
def echo_message(message):
    if not user_access_test(message.from_user.id):
        bot.send_message(message.chat.id, "ليس لديك حق الوصول إلى الروبوت")
        return

    waiting_msg = bot.send_message(message.chat.id, "🔍 جاري البحث العميق في قواعد البيانات... قد يستغرق بضع ثوانٍ.")
    query_id = randint(0, 9999999)
    ok = generate_report(message.text, query_id)

    try:
        bot.delete_message(message.chat.id, waiting_msg.message_id)
    except Exception:
        pass

    if not ok:
        bot.reply_to(message, "⚠️ حدث خطأ أثناء البحث. تحقق من صحة الطلب أو حاول لاحقاً.")
        return

    send_db_page(message.chat.id, query_id, db_idx=0, inner_page=0)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call: CallbackQuery):

    # /db {query_id} {db_idx} {inner_page} [{btn_page}]
    if call.data.startswith("/db "):
        parts = call.data.split(" ")
        query_id  = parts[1]
        db_idx    = int(parts[2])
        inner_page= int(parts[3])
        btn_page  = int(parts[4]) if len(parts) > 4 else 0
        entry = cash_data.get(str(query_id))
        if not entry:
            bot.answer_callback_query(call.id, "انتهت صلاحية النتائج")
            bot.edit_message_text(chat_id=call.message.chat.id,
                                  message_id=call.message.message_id,
                                  text="⏰ انتهت صلاحية النتائج، أرسل طلبك مجدداً.")
            return
        bot.answer_callback_query(call.id)
        send_db_page(call.message.chat.id, query_id, db_idx, inner_page,
                     btn_page=btn_page, edit_msg_id=call.message.message_id)

    # /download {query_id}
    elif call.data.startswith("/download "):
        query_id = call.data.split(" ")[1]
        entry = cash_data.get(str(query_id))
        if not entry or not entry.get("raw"):
            bot.answer_callback_query(call.id, "لا توجد بيانات للتحميل")
            return
        bot.answer_callback_query(call.id, "⏳ جاري إنشاء الملف، سيصلك قريباً...")
        chat_id   = call.message.chat.id
        q_entry   = entry
        q_id_str  = query_id

        def _send_html():
            tmp_path = None
            try:
                html_content = generate_html(q_entry["query"], q_entry["raw"])
                with tempfile.NamedTemporaryFile(suffix=".html", delete=False,
                                                 mode="w", encoding="utf-8") as f:
                    f.write(html_content)
                    tmp_path = f.name
                with open(tmp_path, "rb") as f:
                    bot.send_document(
                        chat_id, f,
                        caption=f"📥 نتائج البحث: <b>{html_lib.escape(q_entry['query'])}</b>",
                        parse_mode="html",
                        visible_file_name=f"results_{q_id_str}.html",
                        timeout=300          # 5 دقائق للملفات الكبيرة
                    )
            except Exception as e:
                print(f"خطأ في إنشاء HTML: {e}")
                try:
                    bot.send_message(chat_id, "⚠️ حدث خطأ أثناء إرسال الملف، حاول مجدداً.")
                except Exception:
                    pass
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        threading.Thread(target=_send_html, daemon=True).start()

    elif call.data == "noop":
        bot.answer_callback_query(call.id)

    elif call.data == "menu_support":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"🛠 للدعم الفني تواصل مع: {DEVELOPER_URL}")

    elif call.data == "menu_back":
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="🕵️ يمكنني البحث عن كل شيء تقريباً. فقط أرسل لي طلبك.",
                reply_markup=create_main_menu()
            )
        except Exception:
            bot.send_message(
                call.message.chat.id,
                "🕵️ يمكنني البحث عن كل شيء تقريباً. فقط أرسل لي طلبك.",
                reply_markup=create_main_menu()
            )

    elif call.data.startswith("menu_"):
        bot.answer_callback_query(call.id, "🔧 هذه الميزة قيد التطوير")

# ─── run ──────────────────────────────────────────────────────────────────────

while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"خطأ: {e}")
