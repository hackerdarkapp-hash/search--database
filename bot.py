import os
  import time
  import threading
  import sqlite3
  import requests
  import telebot
  from http.server import HTTPServer, BaseHTTPRequestHandler
  from dotenv import load_dotenv
  from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

  load_dotenv()

  BOT_TOKEN    = os.getenv('BOT_TOKEN')
  OWNER_ID     = int(os.getenv('OWNER_ID'))
  INTELX_KEY   = os.getenv('INTELX_KEY')
  INTELX_BASE  = 'https://2.intelx.io'
  FREE_LIMIT   = 10

  bot = telebot.TeleBot(BOT_TOKEN)
  admins = [OWNER_ID]

  # ──────────────────────────────────────────────
  #  HTTP keep-alive (for Render / Railway)
  # ──────────────────────────────────────────────
  class _Health(BaseHTTPRequestHandler):
      def do_GET(self):
          self.send_response(200); self.end_headers(); self.wfile.write(b'OK')
      def log_message(self, *a): pass

  threading.Thread(target=lambda: HTTPServer(
      ('0.0.0.0', int(os.getenv('PORT', 8080))), _Health
  ).serve_forever(), daemon=True).start()

  # ──────────────────────────────────────────────
  #  Database
  # ──────────────────────────────────────────────
  db = sqlite3.connect('users.db', check_same_thread=False)
  db.execute('''CREATE TABLE IF NOT EXISTS users (
      id       INTEGER PRIMARY KEY,
      username TEXT,
      searches INTEGER DEFAULT 0,
      banned   INTEGER DEFAULT 0
  )''')
  db.commit()

  def db_add(uid, uname):
      db.execute('INSERT OR IGNORE INTO users (id, username) VALUES (?,?)', (uid, uname)); db.commit()

  def db_searches(uid):
      r = db.execute('SELECT searches FROM users WHERE id=?', (uid,)).fetchone()
      return r[0] if r else 0

  def db_inc(uid):
      db.execute('UPDATE users SET searches = searches+1 WHERE id=?', (uid,)); db.commit()

  def db_banned(uid):
      r = db.execute('SELECT banned FROM users WHERE id=?', (uid,)).fetchone()
      return bool(r and r[0])

  def db_ban(uid, v):
      db.execute('UPDATE users SET banned=? WHERE id=?', (v, uid)); db.commit()

  # ──────────────────────────────────────────────
  #  IntelligenceX API
  # ──────────────────────────────────────────────
  def intelx_search(query: str, max_results: int = 10) -> list:
      if not INTELX_KEY:
          return []
      headers = {'x-key': INTELX_KEY, 'Content-Type': 'application/json'}

      # 1) Start search
      body = {
          'term': query, 'buckets': [], 'lookuplevel': 0,
          'maxresults': max_results, 'timeout': 0,
          'datefrom': '', 'dateto': '', 'sort': 4,
          'media': 0, 'terminate': []
      }
      try:
          r = requests.post(f'{INTELX_BASE}/intelligent/search', json=body, headers=headers, timeout=15)
          r.raise_for_status()
          sid = r.json().get('id')
          if not sid:
              return []
      except Exception:
          return []

      # 2) Wait then fetch results
      time.sleep(3)
      try:
          r2 = requests.get(f'{INTELX_BASE}/intelligent/search/result',
                            params={'id': sid, 'limit': max_results, 'offset': 0},
                            headers=headers, timeout=15)
          r2.raise_for_status()
          return r2.json().get('records', [])
      except Exception:
          return []


  def fmt_results(records: list, query: str) -> str:
      if not records:
          return f'❌ لا توجد نتائج في IntelligenceX للاستعلام:\n<code>{query}</code>'

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

  def panel_kb():
      m = InlineKeyboardMarkup(row_width=2)
      m.add(
          InlineKeyboardButton('📊 إحصائيات', callback_data='stats'),
          InlineKeyboardButton('👥 المستخدمين', callback_data='users'),
          InlineKeyboardButton('🚫 حظر مستخدم', callback_data='ban_prompt'),
          InlineKeyboardButton('✅ رفع الحظر', callback_data='unban_prompt'),
      )
      m.add(InlineKeyboardButton('👨‍💻 تواصل مع المطور', url=DEV_URL))
      return m

  # ──────────────────────────────────────────────
  #  Messages
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
      '💡 <b>أرسل أي نص للبحث عنه الآن!</b>\n'
      f'⚠️ الحد المجاني: {FREE_LIMIT} بحث لكل مستخدم.'
  )

  # ──────────────────────────────────────────────
  #  Handlers
  # ──────────────────────────────────────────────
  @bot.message_handler(commands=['start'])
  def cmd_start(msg):
      db_add(msg.from_user.id, msg.from_user.username or '')
      bot.send_message(msg.chat.id, WELCOME, parse_mode='HTML', reply_markup=main_kb())

  @bot.message_handler(commands=['panel'])
  def cmd_panel(msg):
      if msg.from_user.id not in admins:
          bot.reply_to(msg, '❌ ليس لديك صلاحية.'); return
      bot.send_message(msg.chat.id, '📋 <b>لوحة التحكم</b>', parse_mode='HTML', reply_markup=panel_kb())

  @bot.callback_query_handler(func=lambda c: True)
  def on_callback(call):
      uid = call.from_user.id
      if uid not in admins:
          bot.answer_callback_query(call.id, '❌ لا صلاحية'); return

      if call.data == 'stats':
          total = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
          banned = db.execute('SELECT COUNT(*) FROM users WHERE banned=1').fetchone()[0]
          searches = db.execute('SELECT SUM(searches) FROM users').fetchone()[0] or 0
          bot.edit_message_text(
              f'📊 <b>إحصائيات</b>\n\n'
              f'👥 المستخدمين: <b>{total}</b>\n'
              f'🚫 المحظورين: <b>{banned}</b>\n'
              f'🔎 إجمالي البحث: <b>{searches}</b>',
              call.message.chat.id, call.message.message_id,
              parse_mode='HTML', reply_markup=panel_kb()
          )
      elif call.data == 'users':
          rows = db.execute('SELECT id, username, searches FROM users ORDER BY searches DESC LIMIT 10').fetchall()
          lines = ['👥 <b>أكثر المستخدمين بحثاً:</b>\n']
          for r in rows:
              lines.append(f'• <code>{r[0]}</code> (@{r[1] or "—"}) — {r[2]} بحث')
          bot.edit_message_text('\n'.join(lines), call.message.chat.id, call.message.message_id,
                                parse_mode='HTML', reply_markup=panel_kb())
      elif call.data == 'ban_prompt':
          msg = bot.send_message(call.message.chat.id, '📝 أرسل ID المستخدم لحظره:')
          bot.register_next_step_handler(msg, do_ban)
      elif call.data == 'unban_prompt':
          msg = bot.send_message(call.message.chat.id, '📝 أرسل ID المستخدم لرفع الحظر:')
          bot.register_next_step_handler(msg, do_unban)

      bot.answer_callback_query(call.id)

  def do_ban(msg):
      try:
          target = int(msg.text.strip())
          db_ban(target, 1)
          bot.send_message(msg.chat.id, f'🚫 تم حظر المستخدم <code>{target}</code>', parse_mode='HTML')
      except ValueError:
          bot.send_message(msg.chat.id, '❌ ID غير صالح')

  def do_unban(msg):
      try:
          target = int(msg.text.strip())
          db_ban(target, 0)
          bot.send_message(msg.chat.id, f'✅ تم رفع الحظر عن <code>{target}</code>', parse_mode='HTML')
      except ValueError:
          bot.send_message(msg.chat.id, '❌ ID غير صالح')

  @bot.message_handler(func=lambda m: True)
  def handle_search(msg):
      uid  = msg.from_user.id
      uname = msg.from_user.username or ''
      db_add(uid, uname)

      if db_banned(uid):
          bot.send_message(msg.chat.id, '🚫 حسابك محظور.', reply_markup=main_kb()); return

      count = db_searches(uid)
      if uid not in admins and count >= FREE_LIMIT:
          bot.send_message(msg.chat.id,
              f'⚠️ وصلت للحد المجاني ({FREE_LIMIT} بحث).\n'
              'تواصل مع المطور للترقية.', reply_markup=main_kb()); return

      db_inc(uid)
      query = msg.text.strip()
      wait = bot.send_message(msg.chat.id, '⏳ جارٍ البحث في IntelligenceX...')
      records = intelx_search(query)
      result  = fmt_results(records, query)
      bot.edit_message_text(result, msg.chat.id, wait.message_id,
                            parse_mode='HTML', reply_markup=main_kb())

  # ──────────────────────────────────────────────
  bot.polling(none_stop=True, interval=0, timeout=20)
  