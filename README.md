# OSINT Search Bot

  بوت تيليغرام للبحث في قواعد البيانات المفتوحة عبر IntelligenceX.

  ## المتطلبات
  ```
  pip install -r requirements.txt
  ```

  ## إعداد المتغيرات
  انسخ `.env.example` إلى `.env` واملأ القيم:
  - `BOT_TOKEN` — توكن البوت من @BotFather
  - `OWNER_ID` — ID حسابك في تيليغرام
  - `INTELX_KEY` — مفتاح API من intelx.io

  ## التشغيل
  ```
  python bot.py
  ```

  ## الأوامر
  - `/start` — بدء البوت
  - `/panel` — لوحة التحكم (للمشرفين فقط)
  - أي نص آخر → بحث في IntelligenceX
  