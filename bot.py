import os
import requests
from random import randint

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
limit = 300

DEVELOPER_TEXT = "👨‍💻 المطور"
DEVELOPER_URL = "https://t.me/OX_U1"

def user_access_test(user_id):
    return True

cash_reports = {}

def generate_report(query, query_id):
    global cash_reports, url, bot_token, api_token, limit, lang
    data = {"token": api_token, "request": query.split("\n")[0], "limit": limit, "lang": lang}
    response = requests.post(url, json=data).json()
    print(response)
    if "Error code" in response:
        print("خطأ:" + response["Error code"])
        return None
    cash_reports[str(query_id)] = []
    for database_name in response["List"].keys():
        text = [f"<b>{database_name}</b>", ""]
        text.append(response["List"][database_name]["InfoLeak"] + "\n")
        if database_name != "No results found":
            for report_data in response["List"][database_name]["Data"]:
                for column_name in report_data.keys():
                    text.append(f"<b>{column_name}</b>:  {report_data[column_name]}")
                text.append("")
        text = "\n".join(text)
        if len(text) > 3500:
            text = text[:3500] + text[3500:].split("\n")[0] + "\n\nبعض البيانات لا تتناسب مع هذه الرسالة"
        cash_reports[str(query_id)].append(text)
    return cash_reports[str(query_id)]

def create_inline_keyboard(query_id, page_id, count_page):
    markup = InlineKeyboardMarkup()
    markup.row_width = 3

    if page_id < 0:
        page_id = count_page
    elif page_id > count_page - 1:
        page_id = page_id % count_page

    if count_page > 1:
        markup.add(
            InlineKeyboardButton(text="<<", callback_data=f"/page {query_id} {page_id - 1}"),
            InlineKeyboardButton(text=f"{page_id + 1}/{count_page}", callback_data="page_list"),
            InlineKeyboardButton(text=">>", callback_data=f"/page {query_id} {page_id + 1}")
        )

    markup.add(
        InlineKeyboardButton(text=DEVELOPER_TEXT, url=DEVELOPER_URL)
    )

    return markup

bot = telebot.TeleBot(bot_token)

@bot.message_handler(commands=["start"])
def send_welcome(message):
    bot.reply_to(message, "مرحبًا! أنا بوت يمكنه البحث في قواعد البيانات.", parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def echo_message(message):
    user_id = message.from_user.id
    if not user_access_test(user_id):
        bot.send_message(message.chat.id, "ليس لديك حق الوصول إلى الروبوت")
        return
    if message.content_type == "text":
        query_id = randint(0, 9999999)
        report = generate_report(message.text, query_id)
        if report is None:
            bot.reply_to(message, "الروبوت لا يعمل في الوقت الحالي.", parse_mode="Markdown")
            return
        markup = create_inline_keyboard(query_id, 0, len(report))
        try:
            bot.send_message(message.chat.id, report[0], parse_mode="html", reply_markup=markup)
        except telebot.apihelper.ApiTelegramException:
            bot.send_message(message.chat.id, text=report[0].replace("<b>", "").replace("</b>", ""), reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call: CallbackQuery):
    global cash_reports
    if call.data.startswith("/page "):
        query_id, page_id = call.data.split(" ")[1:]
        if query_id not in cash_reports:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="تم بالفعل حذف نتائج الطلب"
            )
        else:
            report = cash_reports[query_id]
            markup = create_inline_keyboard(query_id, int(page_id), len(report))
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=report[int(page_id)],
                    parse_mode="html",
                    reply_markup=markup
                )
            except telebot.apihelper.ApiTelegramException:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=report[int(page_id)].replace("<b>", "").replace("</b>", ""),
                    reply_markup=markup
                )

while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"خطأ: {e}")
