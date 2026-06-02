import os
import sqlite3
import requests
import tempfile
import threading
import html as html_lib
import string
import random
from datetime import datetime, timedelta
from random import randint

try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
except ModuleNotFoundError:
    import subprocess
    subprocess.run(["pip", "install", "pyTelegramBotAPI"], check=True)
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ─── إعدادات ────────────────────────────────────────────────────────────────

url          = "https://leakosintapi.com/"
bot_token    = os.environ.get("BOT_TOKEN", "")
api_token    = os.environ.get("API_TOKEN", "")
lang         = "ru"
limit        = 9999
DEVELOPER_TEXT = "👨‍💻 المطور"
DEVELOPER_URL  = "https://t.me/OX_U1"
PAGE_SIZE      = 3000
API_TIMEOUT    = 90
DB_BTNS_PER_PAGE = 9
DB_PATH        = "/home/runner/workspace/bot_data.db"

# تكاليف الاشتراك (بالدولار)
SUB_PLANS = [
    ("1h",  "🕐 1 ساعة",    0.3,  timedelta(hours=1)),
    ("1d",  "📅 يوم واحد",  1.0,  timedelta(days=1)),
    ("1w",  "🍺 1 أسبوع",   3.0,  timedelta(weeks=1)),
    ("1m",  "🌙 1 شهر",     5.0,  timedelta(days=30)),
    ("1y",  "🎄 1 سنة",     30.0, timedelta(days=365)),
    ("inf", "🔥 للأبد",     100.0, None),
]

# تكاليف التحسينات (بالدولار)
UPGRADES = [
    ("depth",   "🚧 عمق البحث +100",         4.0),
    ("tokens",  "🪙 الحد الأقصى للرموز +10,000", 1.0),
    ("renewal", "❤ تجديد الرمز +0.1/ث",      1.0),
]

# ─── قاعدة البيانات ──────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY,
            username      TEXT,
            first_name    TEXT,
            referral_code TEXT UNIQUE,
            referred_by   INTEGER,
            joined_at     TEXT,
            has_searched  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS balances (
            user_id      INTEGER PRIMARY KEY,
            withdrawable REAL DEFAULT 0.0,
            bonus        REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id    INTEGER PRIMARY KEY,
            expires_at TEXT
        );

        CREATE TABLE IF NOT EXISTS upgrades (
            user_id      INTEGER PRIMARY KEY,
            search_depth INTEGER DEFAULT 100,
            max_tokens   INTEGER DEFAULT 10000,
            token_renewal REAL DEFAULT 0.1
        );

        CREATE TABLE IF NOT EXISTS tokens (
            user_id      INTEGER PRIMARY KEY,
            current      REAL DEFAULT 10000.0,
            last_update  TEXT
        );

        CREATE TABLE IF NOT EXISTS earnings_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            from_id     INTEGER,
            amount      REAL,
            type        TEXT,
            created_at  TEXT
        );
    """)
    conn.commit()
    conn.close()

def gen_referral_code():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=7))

def register_user(user_id, username, first_name, referral_code_used=None):
    conn = get_conn()
    c = conn.cursor()
    existing = c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
    if existing:
        conn.close()
        return False  # مسجل مسبقاً

    # توليد كود فريد
    while True:
        code = gen_referral_code()
        if not c.execute("SELECT 1 FROM users WHERE referral_code=?", (code,)).fetchone():
            break

    referred_by = None
    if referral_code_used:
        row = c.execute("SELECT user_id FROM users WHERE referral_code=?", (referral_code_used,)).fetchone()
        if row and row["user_id"] != user_id:
            referred_by = row["user_id"]

    now = datetime.now().isoformat()
    c.execute("INSERT INTO users VALUES (?,?,?,?,?,?,0)",
              (user_id, username, first_name, code, referred_by, now))
    c.execute("INSERT INTO balances VALUES (?,0.0,0.0)", (user_id,))
    c.execute("INSERT INTO subscriptions VALUES (?,NULL)", (user_id,))
    c.execute("INSERT INTO upgrades VALUES (?,100,10000,0.1)", (user_id,))
    c.execute("INSERT INTO tokens VALUES (?,10000.0,?)", (user_id, now))
    conn.commit()
    conn.close()
    return True  # مستخدم جديد

def get_user(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_balance(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM balances WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else {"withdrawable": 0.0, "bonus": 0.0}

def get_subscription(user_id):
    conn = get_conn()
    row = conn.execute("SELECT expires_at FROM subscriptions WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if not row or not row["expires_at"]:
        return None
    exp = datetime.fromisoformat(row["expires_at"])
    if exp < datetime.now():
        return None
    return exp

def get_upgrades(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM upgrades WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else {"search_depth": 100, "max_tokens": 10000, "token_renewal": 0.1}

def get_tokens(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM tokens WHERE user_id=?", (user_id,)).fetchone()
    upg = conn.execute("SELECT max_tokens, token_renewal FROM upgrades WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return 10000.0, 10000
    max_t  = upg["max_tokens"] if upg else 10000
    rate   = upg["token_renewal"] if upg else 0.1
    elapsed = (datetime.now() - datetime.fromisoformat(row["last_update"])).total_seconds()
    current = min(max_t, row["current"] + elapsed * rate)
    return current, max_t

def consume_tokens(user_id, amount=100):
    conn = get_conn()
    row = conn.execute("SELECT * FROM tokens WHERE user_id=?", (user_id,)).fetchone()
    upg = conn.execute("SELECT max_tokens, token_renewal FROM upgrades WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        conn.close()
        return True
    max_t  = upg["max_tokens"] if upg else 10000
    rate   = upg["token_renewal"] if upg else 0.1
    elapsed = (datetime.now() - datetime.fromisoformat(row["last_update"])).total_seconds()
    current = min(max_t, row["current"] + elapsed * rate)
    if current < amount:
        conn.close()
        return False
    new_val = current - amount
    conn.execute("UPDATE tokens SET current=?, last_update=? WHERE user_id=?",
                 (new_val, datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()
    return True

def refresh_tokens_ts(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM tokens WHERE user_id=?", (user_id,)).fetchone()
    upg = conn.execute("SELECT max_tokens, token_renewal FROM upgrades WHERE user_id=?", (user_id,)).fetchone()
    if row:
        max_t = upg["max_tokens"] if upg else 10000
        rate  = upg["token_renewal"] if upg else 0.1
        elapsed = (datetime.now() - datetime.fromisoformat(row["last_update"])).total_seconds()
        current = min(max_t, row["current"] + elapsed * rate)
        conn.execute("UPDATE tokens SET current=?, last_update=? WHERE user_id=?",
                     (current, datetime.now().isoformat(), user_id))
        conn.commit()
    conn.close()

def get_referral_stats(user_id):
    conn = get_conn()
    total_refs = conn.execute(
        "SELECT COUNT(*) as cnt FROM users WHERE referred_by=?", (user_id,)
    ).fetchone()["cnt"]
    searched_refs = conn.execute(
        "SELECT COUNT(*) as cnt FROM users WHERE referred_by=? AND has_searched=1", (user_id,)
    ).fetchone()["cnt"]
    conn.close()
    return total_refs, searched_refs

def credit_referrer(user_id, amount, type_name, from_id):
    """تحويل مبلغ للمُحيل (قابل للسحب)."""
    conn = get_conn()
    conn.execute("UPDATE balances SET withdrawable=withdrawable+? WHERE user_id=?", (amount, user_id))
    conn.execute("INSERT INTO earnings_log (referrer_id, from_id, amount, type, created_at) VALUES (?,?,?,?,?)",
                 (user_id, from_id, amount, type_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def mark_first_search(user_id):
    """عند أول بحث — أعطِ المُحيل 0.1$ بونص."""
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user or user["has_searched"]:
        conn.close()
        return None
    conn.execute("UPDATE users SET has_searched=1 WHERE user_id=?", (user_id,))
    referrer_id = user["referred_by"]
    if referrer_id:
        conn.execute("UPDATE balances SET bonus=bonus+0.1 WHERE user_id=?", (referrer_id,))
        conn.execute("INSERT INTO earnings_log (referrer_id, from_id, amount, type, created_at) VALUES (?,?,?,?,?)",
                     (referrer_id, user_id, 0.1, "first_search_bonus", datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return referrer_id

def deduct_balance(user_id, amount, prefer="bonus"):
    """اقتطع من الرصيد. prefer='bonus' أولاً أو 'withdrawable' أولاً."""
    bal = get_balance(user_id)
    total = bal["withdrawable"] + bal["bonus"]
    if total < amount:
        return False
    conn = get_conn()
    remaining = amount
    if prefer == "bonus":
        use_bonus = min(bal["bonus"], remaining)
        remaining -= use_bonus
        use_wd = remaining
    else:
        use_wd = min(bal["withdrawable"], remaining)
        remaining -= use_wd
        use_bonus = remaining
    conn.execute("UPDATE balances SET withdrawable=withdrawable-?, bonus=bonus-? WHERE user_id=?",
                 (use_wd, use_bonus, user_id))
    conn.commit()
    conn.close()
    return True

def apply_subscription(user_id, plan_key):
    for key, label, price, delta in SUB_PLANS:
        if key == plan_key:
            bal = get_balance(user_id)
            total = bal["withdrawable"] + bal["bonus"]
            if total < price:
                return False, price - total
            deduct_balance(user_id, price, prefer="bonus")
            conn = get_conn()
            row = conn.execute("SELECT expires_at FROM subscriptions WHERE user_id=?", (user_id,)).fetchone()
            now = datetime.now()
            if key == "inf":
                new_exp = datetime(9999, 12, 31)
            else:
                current_exp = now
                if row and row["expires_at"]:
                    stored = datetime.fromisoformat(row["expires_at"])
                    if stored > now:
                        current_exp = stored
                new_exp = current_exp + delta
            conn.execute("UPDATE subscriptions SET expires_at=? WHERE user_id=?",
                         (new_exp.isoformat(), user_id))
            conn.commit()
            conn.close()
            return True, new_exp
    return False, 0

def apply_upgrade(user_id, upg_key):
    for key, label, price in UPGRADES:
        if key == upg_key:
            bal = get_balance(user_id)
            total = bal["withdrawable"] + bal["bonus"]
            if total < price:
                return False, price - total
            deduct_balance(user_id, price, prefer="bonus")
            conn = get_conn()
            if key == "depth":
                conn.execute("UPDATE upgrades SET search_depth=search_depth+100 WHERE user_id=?", (user_id,))
            elif key == "tokens":
                conn.execute("UPDATE upgrades SET max_tokens=max_tokens+10000 WHERE user_id=?", (user_id,))
                conn.execute("UPDATE tokens SET current=MIN(current+10000, max_tokens+10000) WHERE user_id=?", (user_id,))
            elif key == "renewal":
                conn.execute("UPDATE upgrades SET token_renewal=token_renewal+0.1 WHERE user_id=?", (user_id,))
            conn.commit()
            conn.close()
            return True, None
    return False, 0

# ─── ذاكرة مؤقتة للبحث ──────────────────────────────────────────────────────

cash_data = {}

# ─── helpers ─────────────────────────────────────────────────────────────────

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

# ─── البحث ───────────────────────────────────────────────────────────────────

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

# ─── لوحات المفاتيح ──────────────────────────────────────────────────────────

def create_result_keyboard(query_id, db_idx, inner_page, db_names, db_pages, btn_page=0):
    markup = InlineKeyboardMarkup()
    total_dbs = len(db_names)

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
                InlineKeyboardButton(text=short, callback_data=f"/db {query_id} {i} 0 {btn_page}")
            )
        for i in range(0, len(slice_btns), 3):
            markup.row(*slice_btns[i:i+3])

        if total_btn_pages > 1:
            prev_bp = (btn_page - 1) % total_btn_pages
            next_bp = (btn_page + 1) % total_btn_pages
            markup.row(
                InlineKeyboardButton(text="⬅️", callback_data=f"/db {query_id} {db_idx} {inner_page} {prev_bp}"),
                InlineKeyboardButton(text=f"📋 {btn_page + 1} / {total_btn_pages}", callback_data="noop"),
                InlineKeyboardButton(text="➡️", callback_data=f"/db {query_id} {db_idx} {inner_page} {next_bp}")
            )

    current_db_name = db_names[db_idx]
    total_inner = len(db_pages.get(current_db_name, []))
    if total_inner > 1:
        markup.row(
            InlineKeyboardButton(text="◀️", callback_data=f"/db {query_id} {db_idx} {(inner_page-1)%total_inner} {btn_page}"),
            InlineKeyboardButton(text=f"📄 {inner_page+1} / {total_inner}", callback_data="noop"),
            InlineKeyboardButton(text="▶️", callback_data=f"/db {query_id} {db_idx} {(inner_page+1)%total_inner} {btn_page}")
        )

    markup.row(InlineKeyboardButton(text="📥 تحميل النتائج كاملة", callback_data=f"/download {query_id}"))
    markup.row(InlineKeyboardButton(text=DEVELOPER_TEXT, url=DEVELOPER_URL))
    return markup

def create_main_menu():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(text="⚙️ API",             callback_data="menu_api"),
        InlineKeyboardButton(text="📝 البحث الجماعي",   callback_data="menu_bulk_search")
    )
    markup.row(
        InlineKeyboardButton(text="📋 قائمة القواعد",   callback_data="menu_db_list"),
        InlineKeyboardButton(text="❓ الأسئلة الشائعة", callback_data="menu_faq")
    )
    markup.row(
        InlineKeyboardButton(text="💰 رصيدي",           callback_data="menu_balance"),
        InlineKeyboardButton(text="💎 الاشتراك",        callback_data="menu_subscription")
    )
    markup.row(
        InlineKeyboardButton(text="👥 نظام الإحالة",    callback_data="menu_referral"),
        InlineKeyboardButton(text="⬆️ تحسينات",         callback_data="menu_upgrades")
    )
    markup.row(
        InlineKeyboardButton(text="💳 سحب الأموال",     callback_data="menu_withdraw"),
        InlineKeyboardButton(text="🎁 إعطاء اشتراك",   callback_data="menu_gift")
    )
    markup.row(InlineKeyboardButton(text="🛠 الدعم الفني", callback_data="menu_support"))
    return markup

def sub_plans_keyboard():
    markup = InlineKeyboardMarkup()
    for key, label, price, _ in SUB_PLANS:
        markup.row(InlineKeyboardButton(
            text=f"{label}  —  {price}$",
            callback_data=f"buy_sub_{key}"
        ))
    markup.row(InlineKeyboardButton(text="↩️ رجوع", callback_data="menu_back"))
    return markup

def upgrades_keyboard():
    markup = InlineKeyboardMarkup()
    for key, label, price in UPGRADES:
        markup.row(InlineKeyboardButton(
            text=f"{label}  —  {price}$",
            callback_data=f"buy_upg_{key}"
        ))
    markup.row(InlineKeyboardButton(text="↩️ رجوع", callback_data="menu_back"))
    return markup

def withdraw_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(text="₿ كريبتو",         callback_data="withdraw_crypto"),
        InlineKeyboardButton(text="💳 بطاقة بنكية",    callback_data="withdraw_card")
    )
    markup.row(InlineKeyboardButton(text="↩️ رجوع", callback_data="menu_back"))
    return markup

# ─── إرسال الصفحات ───────────────────────────────────────────────────────────

def send_db_page(chat_id, query_id, db_idx, inner_page, btn_page=0, edit_msg_id=None):
    entry = cash_data.get(str(query_id))
    if not entry:
        bot.send_message(chat_id, "⏰ انتهت صلاحية النتائج، أرسل طلبك مجدداً.")
        return

    db_names = entry["db_names"]
    db_pages = entry["db_pages"]
    db_idx   = max(0, min(db_idx, len(db_names) - 1))
    current_db = db_names[db_idx]
    pages = db_pages.get(current_db, [""])
    inner_page = inner_page % len(pages)
    text = pages[inner_page]

    total_btn_pages = max(1, (len(db_names) + DB_BTNS_PER_PAGE - 1) // DB_BTNS_PER_PAGE)
    btn_page = max(0, min(btn_page, total_btn_pages - 1))
    markup = create_result_keyboard(query_id, db_idx, inner_page, db_names, db_pages, btn_page)

    def _safe(t):
        return t.replace("<b>", "").replace("</b>", "")

    if edit_msg_id:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=edit_msg_id,
                                  text=text, parse_mode="html", reply_markup=markup)
        except telebot.apihelper.ApiTelegramException:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=edit_msg_id,
                                      text=_safe(text), reply_markup=markup)
            except Exception:
                pass
    else:
        try:
            bot.send_message(chat_id, text, parse_mode="html", reply_markup=markup)
        except telebot.apihelper.ApiTelegramException:
            bot.send_message(chat_id, _safe(text), reply_markup=markup)

# ─── البوت ───────────────────────────────────────────────────────────────────

bot = telebot.TeleBot(bot_token)

# ─── /start ──────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def send_welcome(message):
    args = message.text.split()
    ref_code = args[1] if len(args) > 1 else None
    uid      = message.from_user.id
    uname    = message.from_user.username or ""
    fname    = message.from_user.first_name or ""

    is_new = register_user(uid, uname, fname, ref_code)

    if is_new and ref_code:
        # إشعار المُحيل
        user_data = get_user(uid)
        referrer_id = user_data.get("referred_by") if user_data else None
        if referrer_id:
            bal = get_balance(referrer_id)
            refs_total, refs_searched = get_referral_stats(referrer_id)
            try:
                bot.send_message(
                    referrer_id,
                    f"🪞 <b>إحالتك لديها مستخدم جديد!</b>\n"
                    f"🆔 {str(uid)[:4]}{'█'*6}\n\n"
                    f"💠 إجمالي مستخدمي الإحالة: {refs_total}\n"
                    f"💲 رصيد البونص: {bal['bonus']:.2f}$\n"
                    f"💳 رصيد قابل للسحب: {bal['withdrawable']:.2f}$",
                    parse_mode="html"
                )
            except Exception:
                pass

    bot.send_message(
        message.chat.id,
        "🕵️ يمكنني البحث عن كل شيء تقريباً. فقط أرسل لي طلبك.",
        reply_markup=create_main_menu()
    )

# ─── رسائل البحث ─────────────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"))
def echo_message(message):
    uid = message.from_user.id

    # تسجيل تلقائي عند الحاجة
    register_user(uid, message.from_user.username or "", message.from_user.first_name or "")

    # التحقق من الرموز
    current_tokens, max_tokens = get_tokens(uid)
    if current_tokens < 100:
        upg = get_upgrades(uid)
        bot.reply_to(
            message,
            f"⚠️ رصيد الرموز غير كافٍ!\n"
            f"🪙 رصيدك الحالي: {int(current_tokens)} / {max_tokens}\n"
            f"❤ معدل التجديد: {upg['token_renewal']:.1f}/ث\n\n"
            f"يمكنك شراء رموز إضافية من قائمة التحسينات أو انتظر تجدد الرصيد.",
            reply_markup=create_main_menu()
        )
        return

    waiting_msg = bot.send_message(message.chat.id,
                                   "🔍 جاري البحث العميق في قواعد البيانات... قد يستغرق بضع ثوانٍ.")
    query_id = randint(0, 9999999)
    ok = generate_report(message.text, query_id)

    try:
        bot.delete_message(message.chat.id, waiting_msg.message_id)
    except Exception:
        pass

    if not ok:
        bot.reply_to(message, "⚠️ حدث خطأ أثناء البحث. تحقق من صحة الطلب أو حاول لاحقاً.")
        return

    # اقتطع الرموز وسجّل أول بحث
    consume_tokens(uid, 100)
    referrer_id = mark_first_search(uid)

    # إشعار المُحيل عند أول بحث (0.1$ بونص)
    if referrer_id:
        bal = get_balance(referrer_id)
        try:
            bot.send_message(
                referrer_id,
                f"🏧 <b>إحالتك أجرت أول بحث!</b>\n"
                f"💎 لقد تلقيت <b>0.1$</b> بونص.\n"
                f"💲 رصيد البونص الآن: {bal['bonus']:.2f}$",
                parse_mode="html"
            )
        except Exception:
            pass

    send_db_page(message.chat.id, query_id, db_idx=0, inner_page=0)

# ─── معالج الأزرار ───────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call: CallbackQuery):
    uid = call.from_user.id
    register_user(uid, call.from_user.username or "", call.from_user.first_name or "")
    data = call.data

    # /db
    if data.startswith("/db "):
        parts = data.split(" ")
        query_id   = parts[1]
        db_idx     = int(parts[2])
        inner_page = int(parts[3])
        btn_page   = int(parts[4]) if len(parts) > 4 else 0
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

    # /download
    elif data.startswith("/download "):
        query_id = data.split(" ")[1]
        entry = cash_data.get(str(query_id))
        if not entry or not entry.get("raw"):
            bot.answer_callback_query(call.id, "لا توجد بيانات للتحميل")
            return
        bot.answer_callback_query(call.id, "⏳ جاري إنشاء الملف، سيصلك قريباً...")
        chat_id  = call.message.chat.id
        q_entry  = entry
        q_id_str = query_id

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
                        timeout=300
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

    elif data == "noop":
        bot.answer_callback_query(call.id)

    # ─── القائمة الرئيسية ───────────────────────────────────────────────────

    elif data == "menu_back":
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="🕵️ يمكنني البحث عن كل شيء تقريباً. فقط أرسل لي طلبك.",
                reply_markup=create_main_menu()
            )
        except Exception:
            bot.send_message(call.message.chat.id,
                             "🕵️ يمكنني البحث عن كل شيء تقريباً. فقط أرسل لي طلبك.",
                             reply_markup=create_main_menu())

    elif data == "menu_support":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id,
                         f"🛠 للدعم الفني تواصل مع: {DEVELOPER_URL}")

    # ─── الرصيد ─────────────────────────────────────────────────────────────

    elif data == "menu_balance":
        bot.answer_callback_query(call.id)
        bal  = get_balance(uid)
        upg  = get_upgrades(uid)
        sub  = get_subscription(uid)
        cur_t, max_t = get_tokens(uid)
        refresh_tokens_ts(uid)

        if sub is None:
            sub_text = "❌ لا يوجد اشتراك نشط"
        elif sub.year == 9999:
            sub_text = "🔥 للأبد"
        else:
            diff = sub - datetime.now()
            days = diff.days
            hours = diff.seconds // 3600
            sub_text = f"✅ {days} يوم و{hours} ساعة متبقية"

        mk = InlineKeyboardMarkup()
        mk.row(InlineKeyboardButton(text="💎 شراء اشتراك", callback_data="menu_subscription"))
        mk.row(InlineKeyboardButton(text="⬆️ تحسينات", callback_data="menu_upgrades"))
        mk.row(InlineKeyboardButton(text="↩️ رجوع", callback_data="menu_back"))

        bot.send_message(
            call.message.chat.id,
            f"👛 <b>رصيدك</b>\n\n"
            f"💲 قابل للسحب: <b>{bal['withdrawable']:.2f}$</b>\n"
            f"💎 بونص (للاشتراكات): <b>{bal['bonus']:.2f}$</b>\n\n"
            f"💎 وقت الاشتراك: {sub_text}\n"
            f"🚧 عمق البحث: <b>{upg['search_depth']}</b>\n"
            f"🪙 الرموز: <b>{int(cur_t):,} / {max_t:,}</b>\n"
            f"❤ تجديد الرموز: <b>{upg['token_renewal']:.1f}/ث</b>",
            parse_mode="html",
            reply_markup=mk
        )

    # ─── الاشتراكات ──────────────────────────────────────────────────────────

    elif data == "menu_subscription":
        bot.answer_callback_query(call.id)
        bal = get_balance(uid)
        total = bal["withdrawable"] + bal["bonus"]
        sub = get_subscription(uid)

        if sub and sub.year == 9999:
            sub_text = "🔥 للأبد"
        elif sub:
            diff = sub - datetime.now()
            sub_text = f"{diff.days} يوم و{diff.seconds//3600} ساعة"
        else:
            sub_text = "لا يوجد"

        bot.send_message(
            call.message.chat.id,
            f"💎 <b>الاشتراك</b>\n\n"
            f"⏱ المتبقي: {sub_text}\n"
            f"💰 رصيدك المتاح: <b>{total:.2f}$</b>\n\n"
            f"اختر خطة الاشتراك:\n"
            f"<i>(يُضاف إلى وقتك الحالي)</i>",
            parse_mode="html",
            reply_markup=sub_plans_keyboard()
        )

    elif data.startswith("buy_sub_"):
        plan_key = data.replace("buy_sub_", "")
        bot.answer_callback_query(call.id)
        success, result = apply_subscription(uid, plan_key)
        if success:
            if hasattr(result, 'year') and result.year == 9999:
                exp_text = "للأبد 🔥"
            else:
                diff = result - datetime.now()
                exp_text = f"{diff.days} يوم و{diff.seconds//3600} ساعة"
            bot.send_message(
                call.message.chat.id,
                f"✅ <b>تم تفعيل الاشتراك!</b>\n"
                f"⏱ إجمالي الوقت المتبقي: {exp_text}",
                parse_mode="html",
                reply_markup=create_main_menu()
            )
        else:
            needed = result
            bot.send_message(
                call.message.chat.id,
                f"❌ رصيدك غير كافٍ.\n"
                f"تحتاج إلى <b>{needed:.2f}$</b> إضافية.\n\n"
                f"شارك رابط إحالتك لتجميع الرصيد!",
                parse_mode="html",
                reply_markup=create_main_menu()
            )

    # ─── التحسينات ───────────────────────────────────────────────────────────

    elif data == "menu_upgrades":
        bot.answer_callback_query(call.id)
        bal = get_balance(uid)
        upg = get_upgrades(uid)
        total = bal["withdrawable"] + bal["bonus"]
        bot.send_message(
            call.message.chat.id,
            f"⬆️ <b>التحسينات الدائمة</b>\n\n"
            f"🚧 عمق البحث الحالي: <b>{upg['search_depth']}</b>\n"
            f"🪙 الحد الأقصى للرموز: <b>{upg['max_tokens']:,}</b>\n"
            f"❤ معدل التجديد: <b>{upg['token_renewal']:.1f}/ث</b>\n\n"
            f"💰 رصيدك المتاح: <b>{total:.2f}$</b>\n\n"
            f"اختر تحسيناً دائماً:",
            parse_mode="html",
            reply_markup=upgrades_keyboard()
        )

    elif data.startswith("buy_upg_"):
        upg_key = data.replace("buy_upg_", "")
        bot.answer_callback_query(call.id)
        success, result = apply_upgrade(uid, upg_key)
        upg = get_upgrades(uid)
        if success:
            bot.send_message(
                call.message.chat.id,
                f"✅ <b>تم تطبيق التحسين!</b>\n\n"
                f"🚧 عمق البحث: {upg['search_depth']}\n"
                f"🪙 الحد الأقصى للرموز: {upg['max_tokens']:,}\n"
                f"❤ تجديد الرموز: {upg['token_renewal']:.1f}/ث",
                parse_mode="html",
                reply_markup=create_main_menu()
            )
        else:
            bot.send_message(
                call.message.chat.id,
                f"❌ رصيدك غير كافٍ. تحتاج <b>{result:.2f}$</b> إضافية.",
                parse_mode="html",
                reply_markup=create_main_menu()
            )

    # ─── الإحالة ──────────────────────────────────────────────────────────────

    elif data == "menu_referral":
        bot.answer_callback_query(call.id)
        user_data = get_user(uid)
        if not user_data:
            register_user(uid, "", "")
            user_data = get_user(uid)
        ref_code  = user_data["referral_code"]
        bot_info  = bot.get_me()
        ref_link  = f"https://t.me/{bot_info.username}?start={ref_code}"
        bal       = get_balance(uid)
        total_refs, searched_refs = get_referral_stats(uid)

        mk = InlineKeyboardMarkup()
        mk.row(InlineKeyboardButton(text="📋 نسخ الرابط", switch_inline_query=ref_link))
        mk.row(InlineKeyboardButton(text="↩️ رجوع", callback_data="menu_back"))

        bot.send_message(
            call.message.chat.id,
            f"👥 <b>نظام الإحالة</b>\n\n"
            f"✉ رابط الإحالة الخاص بك:\n"
            f"<code>{ref_link}</code>\n\n"
            f"🧍 أي شخص يدخل البوت لأول مرة عبر رابطك يصبح إحالتك إلى الأبد.\n\n"
            f"💰 ستتلقى <b>20%</b> من جميع مدفوعات إحالاتك.\n"
            f"💸 ستتلقى <b>5%</b> من مدفوعات إحالات إحالاتك.\n"
            f"💵 <b>0.1$</b> بونص عن كل مستخدم يجري أول بحث.\n\n"
            f"─────────────────\n"
            f"💠 إجمالي الإحالات: <b>{total_refs}</b>\n"
            f"✅ بحثوا بالفعل: <b>{searched_refs}</b>\n"
            f"💲 رصيد البونص: <b>{bal['bonus']:.2f}$</b>\n"
            f"💳 قابل للسحب: <b>{bal['withdrawable']:.2f}$</b>",
            parse_mode="html",
            reply_markup=mk
        )

    # ─── السحب ───────────────────────────────────────────────────────────────

    elif data == "menu_withdraw":
        bot.answer_callback_query(call.id)
        bal = get_balance(uid)
        bot.send_message(
            call.message.chat.id,
            f"💳 <b>سحب الأموال</b>\n\n"
            f"💲 رصيدك القابل للسحب: <b>{bal['withdrawable']:.2f}$</b>\n\n"
            f"📌 الحد الأدنى للسحب: <b>1$</b>\n"
            f"<i>ملاحظة: البونص (0.1$/مستخدم) لا يمكن سحبه، يُستخدم فقط للاشتراكات.</i>\n\n"
            f"اختر طريقة السحب:",
            parse_mode="html",
            reply_markup=withdraw_keyboard()
        )

    elif data in ("withdraw_crypto", "withdraw_card"):
        bot.answer_callback_query(call.id)
        bal = get_balance(uid)
        if bal["withdrawable"] < 1.0:
            bot.send_message(
                call.message.chat.id,
                f"❌ رصيدك القابل للسحب ({bal['withdrawable']:.2f}$) أقل من الحد الأدنى (1$).\n"
                f"شارك رابط إحالتك لتجميع المزيد!",
                reply_markup=create_main_menu()
            )
        else:
            method = "عملة مشفرة (كريبتو)" if data == "withdraw_crypto" else "بطاقة بنكية"
            bot.send_message(
                call.message.chat.id,
                f"💳 طلب سحب عبر <b>{method}</b>\n"
                f"المبلغ: <b>{bal['withdrawable']:.2f}$</b>\n\n"
                f"📩 أرسل تفاصيل حسابك للدعم الفني:\n{DEVELOPER_URL}",
                parse_mode="html",
                reply_markup=create_main_menu()
            )

    elif data in ("menu_api", "menu_bulk_search", "menu_db_list", "menu_faq", "menu_gift"):
        bot.answer_callback_query(call.id, "🔧 هذه الميزة قيد التطوير")

    else:
        bot.answer_callback_query(call.id)

# ─── تشغيل ───────────────────────────────────────────────────────────────────

init_db()
print("✅ قاعدة البيانات جاهزة")

while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"خطأ: {e}")
