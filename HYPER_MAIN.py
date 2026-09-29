import telebot
import os
import sqlite3
import time
import random
import re
import math
import threading
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

token = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(token)
CHATS = [-1003724538567, 7163427034, -1004373444431, -1004243458835]
LOCKS={}

class Filter(telebot.SimpleCustomFilter):
    key = "imc"
    def check(self, obj):
        if hasattr(obj, 'chat'):
            return obj.chat.id in CHATS
        if hasattr(obj, 'message'):
            return obj.message.chat.id in CHATS
        return False
bot.add_custom_filter(Filter())

os.makedirs("data", exist_ok=True)
DB_PATH = "data/absolute_db.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
		CREATE TABLE IF NOT EXISTS Users (
			bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
			real_id INTEGER NOT NULL,
			coins INTEGER DEFAULT 0,
			loks INTEGER DEFAULT 0,
			time_kd INTEGER DEFAULT 0,
			time_loks INTEGER DEFAULT 0,
			wins INTEGER DEFAULT 0,
			losses INTEGER DEFAULT 0
		)
		""")
        cursor.execute("""
		CREATE TABLE IF NOT EXISTS SystemSettings (
			key TEXT PRIMARY KEY,
			value INTEGER DEFAULT 0
		)
		""")
        cursor.execute("INSERT OR IGNORE INTO SystemSettings (key, value) VALUES ('fee', 5)")
        conn.commit()



def get_fee():
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT value FROM SystemSettings WHERE key = 'fee'").fetchone()
        return res[0] if res else 5



def get_total_loks():
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT SUM(loks) FROM Users").fetchone()
        return int(res[0]) if res[0] else 0



def get_loks_price(total_loks=None):
    if total_loks is None:
        total_loks = get_total_loks()
    return 100 + total_loks



def calc_buy_cost(current_total, amount):
    cost = 0
    for i in range(amount):
        cost += 100 + (current_total + i)
    return cost



def calc_sell_return(current_total, amount):
    revenue = 0
    for i in range(amount):
        revenue += 100 + (current_total - 1 - i)
    fee_pct = get_fee()
    net = revenue * (100 - fee_pct) / 100.0
    return int(round(net))



def get_max_buy_loks(current_total, coins):
    amt = 0
    cost = 0
    while True:
        next_price = 100 + current_total + amt
        if cost + next_price <= coins:
            cost += next_price
            amt += 1
        else:
            break
    return amt



@bot.message_handler(imc=True, func=lambda m: m.text and m.from_user.id in CHATS and m.text.lower().startswith('+комиссия '))
def admin_set_fee(message):
    args = message.text.split()
    try:
        val = int(args[1])
        if val < 0 or val > 100: raise ValueError
    except (IndexError, ValueError):
        return bot.reply_to(message, "Используйте: +комиссия [от 0 до 100]")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE SystemSettings SET value = ? WHERE key = 'fee'", (val,))
    bot.reply_to(message, f"Комиссия на продажу успешно установлена: {val}%")



@bot.message_handler(imc=True, func=lambda m: m.text and m.text.lower().startswith('кл'))
def buy_loks_request(message):
    uid = message.from_user.id
    check(uid)
    args = message.text.split()
    if len(args) == 1:
        return bot.reply_to(message, "Укажите сумму: кл [сумма]")
    try:
        if len(args) != 2 or not args[1].isdigit():
            return bot.reply_to(message, "Неправильная команда")
        amount = int(args[1])
        if amount <= 0: raise ValueError
    except ValueError:
        return bot.reply_to(message, "Неправильная команда")
    
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return
    try:
        u = get_user("real_id", uid)
        total_loks = get_total_loks()
        cost = calc_buy_cost(total_loks, amount)
        if int(u["coins"]) < cost:
            max_loks = get_max_buy_loks(total_loks, int(u["coins"]))
            return bot.reply_to(message, f"Недостаточно средств.\nМаксимум вашей покупки: {max_loks}Л")
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("✅Подтвердить", callback_data=f"blok_{u['bot_id']}_{amount}", style="success"))
        bot.reply_to(message, f"Вы уверены что хотите преобресить {amount}Л за {cost}Ж?\nНа момент подтверждения курс может измениться", reply_markup=markup)
    finally: LOCKS[uid].release()



@bot.callback_query_handler(func=lambda c: c.data.startswith("blok_"))
def buy_loks_confirm(call):
    _, s_bid, amt_str = call.data.split("_")
    s_bid, amount = int(s_bid), int(amt_str)
    u = get_user("bot_id", s_bid)
    if not u or call.from_user.id != u["real_id"]: return bot.answer_callback_query(call.id)
    uid = u["real_id"]
    
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return bot.answer_callback_query(call.id)
    
    bot.answer_callback_query(call.id)
    try:
        total_loks = get_total_loks()
        cost = calc_buy_cost(total_loks, amount)
        u_fresh = get_user("real_id", uid)
        if int(u_fresh["coins"]) < cost:
            max_loks = get_max_buy_loks(total_loks, int(u_fresh["coins"]))
            try: bot.edit_message_text(f"Недостаточно средств.\nМаксимум вашей покупки: {max_loks}Л", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception: pass
            return
        now = int(time.time())
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE Users SET coins = coins - ?, loks = loks + ?, time_loks = ? WHERE real_id = ?", (cost, amount, now, uid))
        mention = f'<a href="tg://user?id={uid}">#{s_bid}</a>'
        try: bot.edit_message_text(f"{mention} преобрёл {amount}Л за {cost}Ж", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
        except Exception: pass
    finally: LOCKS[uid].release()



@bot.message_handler(imc=True, func=lambda m: m.text and m.text.lower().startswith('пл'))
def sell_loks_request(message):
    uid = message.from_user.id
    check(uid)
    args = message.text.split()
    if len(args) == 1:
        return bot.reply_to(message, "Укажите сумму: пл [сумма]")
    try:
        if len(args) != 2 or not args[1].isdigit():
            return bot.reply_to(message, "Неправильная команда")
        amount = int(args[1])
        if amount <= 0: raise ValueError
    except ValueError:
        return bot.reply_to(message, "Неправильная команда")
        
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return
    try:
        u = get_user("real_id", uid)
        now = int(time.time())
        if now - int(u["time_loks"]) < 86400:
            rem = 86400 - (now - int(u["time_loks"]))
            return bot.reply_to(message, f"К сожалению, продажа доступна только через 24 часа после последней покупки/продажи. Подождите ещё:\n{rem//3600} ч. {(rem%3600)//60} мин. {rem%60} сек.")
        if int(u["loks"]) < amount:
            return bot.reply_to(message, "Недостаточно локсов для продажи")
        total_loks = get_total_loks()
        revenue = calc_sell_return(total_loks, amount)
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("✅Подтвердить", callback_data=f"slok_{u['bot_id']}_{amount}", style="success"))
        bot.reply_to(message, f"Вы уверены что хотите продать {amount}Л за {revenue}Ж?\nНа момент подтверждения курс может измениться", reply_markup=markup)
    finally: LOCKS[uid].release()



@bot.callback_query_handler(func=lambda c: c.data.startswith("slok_"))
def sell_loks_confirm(call):
    _, s_bid, amt_str = call.data.split("_")
    s_bid, amount = int(s_bid), int(amt_str)
    u = get_user("bot_id", s_bid)
    if not u or call.from_user.id != u["real_id"]: return bot.answer_callback_query(call.id)
    uid = u["real_id"]
    
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return bot.answer_callback_query(call.id)
    
    bot.answer_callback_query(call.id)
    try:
        u_fresh = get_user("real_id", uid)
        now = int(time.time())
        if now - int(u_fresh["time_loks"]) < 86400:
            rem = 86400 - (now - int(u_fresh["time_loks"]))
            try: bot.edit_message_text(f"К сожалению, продажа доступна только через 24 часа. Подождите ещё:\n{rem//3600} ч. {rem%3600//60} мин. {rem%60} сек.", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception: pass
            return
        if int(u_fresh["loks"]) < amount:
            try: bot.edit_message_text("Недостаточно локсов для продажи", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception: pass
            return
        total_loks = get_total_loks()
        revenue = calc_sell_return(total_loks, amount)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE Users SET coins = coins + ?, loks = loks - ?, time_loks = ? WHERE real_id = ?", (revenue, amount, now, uid))
        mention = f'<a href="tg://user?id={uid}">#{s_bid}</a>'
        try: bot.edit_message_text(f"{mention} продал {amount}Л за {revenue}Ж", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
        except Exception: pass
    finally: LOCKS[uid].release()



@bot.message_handler(imc=True, func=lambda m: m.text and (m.text.lower() in ['л'] or m.text.lower().startswith('л ')))
def get_loks_balance(message):
    t_id, is_bot = message.from_user.id, False
    if message.reply_to_message:
        t_id = message.reply_to_message.from_user.id
    else:
        args = message.text.split(maxsplit=1)
        if len(args) > 1 and args[1].isdigit():
            t_id, is_bot = int(args[1]), True
    if not is_bot and t_id == message.from_user.id:
        check(t_id)
    u = get_user("bot_id" if is_bot else "real_id", t_id)
    if not u:
        return bot.reply_to(message, "Пользователь не найден")
    total_loks = get_total_loks()
    estimated_coins = calc_sell_return(total_loks, int(u["loks"]))
    txt = (
        f'👤<a href="tg://user?id={u["real_id"]}">#{u["bot_id"]}</a>\n'
        f'Баланс в Л: {int(u["loks"])}Л\n'
        f'Баланс в Ж: {estimated_coins}Ж'
    )
    bot.reply_to(message, txt, parse_mode="HTML")



@bot.message_handler(imc=True, func=lambda m: m.text and m.from_user.id in CHATS and m.text.lower().startswith('вл '))
def admin_give_loks(message):
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "Используйте: вл [сумма] [айди]")
    try:
        amt = int(args[1])
    except ValueError:
        return bot.reply_to(message, "Сумма должна быть целым числом")
    trg = None
    if len(args) > 2:
        t_id = args[2].replace('#', '')
        if t_id.isdigit():
            trg = get_user("bot_id", int(t_id))
    elif message.reply_to_message:
        check(message.reply_to_message.from_user.id)
        trg = get_user("real_id", message.reply_to_message.from_user.id)
    else:
        check(message.from_user.id)
        trg = get_user("real_id", message.from_user.id)
    if not trg:
        return bot.reply_to(message, "Пользователь не найден")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE Users SET loks = loks + ? WHERE real_id = ?", (amt, trg["real_id"]))
    bot.reply_to(message, f"Выдано {amt}Л на <a href=\"tg://user?id={trg['real_id']}\">#{trg['bot_id']}</a>", parse_mode="HTML")



@bot.message_handler(imc=True, func=lambda m: m.text and m.text.lower() == 'курс')
def show_loks_rate(message):
    total_loks = get_total_loks()
    price = get_loks_price(total_loks)
    fee_pct = get_fee()
    fee_val = int(round(price * fee_pct / 100.0))
    txt = (
        f"<b>🏦Курс локса</b>\n\n"
        f"Капитал — {total_loks}Л\n"
        f"Цена за 1Л — {price}Ж\n"
        f"Комиссия — {fee_val}Ж\n\n"
        f"<b>Команды:</b>\n"
        f"- Л — посмотреть локс-баланс\n"
        f"- Кл [сумма] — купить Л\n"
        f"- Пл [сумма] — продать Л\n\n"
        f"Учитывайте, что передавать локсы нельзя, а продавать можно только через 24 часа после последней покупки/продажи"
    )
    bot.reply_to(message, txt, parse_mode="HTML")



@bot.message_handler(imc=True, func=lambda m: m.text and m.from_user.id in CHATS and (m.text.lower() == '-кдл' or m.text.lower().startswith('-кдл ')))
def admin_reset_loks_cooldown(message):
    args = message.text.split()
    trg = None
    if len(args) > 1:
        t_id = args[1].replace('#', '')
        if t_id.isdigit():
            trg = get_user("bot_id", int(t_id))
    elif message.reply_to_message:
        check(message.reply_to_message.from_user.id)
        trg = get_user("real_id", message.reply_to_message.from_user.id)
    else:
        check(message.from_user.id)
        trg = get_user("real_id", message.from_user.id)
    if not trg:
        return bot.reply_to(message, "Пользователь не найден")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE Users SET time_loks = 0 WHERE real_id = ?", (trg["real_id"],))
    bot.reply_to(message, f"КД на продажу Л для <a href=\"tg://user?id={trg['real_id']}\">#{trg['bot_id']}</a> успешно обнулен", parse_mode="HTML")



def get_user(field, val):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        res = conn.execute(f"SELECT * FROM Users WHERE {field} = ?", (val,)).fetchone()
        return dict(res) if res else None

def check(id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM Users WHERE real_id = ?", (id,))
        user = cursor.fetchone()
        if user is None:
            cursor.execute("INSERT INTO Users (real_id) VALUES (?)", (id,))
            conn.commit()



@bot.message_handler(imc=True, func=lambda m: m.text and (m.text.lower() in ['б'] or m.text.lower().startswith('б ')))
def get_balance(message):
    t_id, is_bot = message.from_user.id, False
    if message.reply_to_message:
        t_id = message.reply_to_message.from_user.id
    else:
        args = message.text.split(maxsplit=1)
        if len(args) > 1 and args[1].isdigit():
            t_id, is_bot = int(args[1]), True
    if not is_bot and t_id == message.from_user.id:
        check(t_id)
    u = get_user("bot_id" if is_bot else "real_id", t_id)
    if not u:
        return bot.reply_to(message, "Пользователь не найден")
    txt = (
        f'👤<a href="tg://user?id={u["real_id"]}">#{u["bot_id"]}</a>\n'
        f'Жетонов: {int(u["coins"])}Ж\n'
        f'Локсов: {int(u["loks"])}Л\n'
        f'Побед: {int(u["wins"])}\n'
        f'Проигрышей: {int(u["losses"])}'
    )
    bot.reply_to(message, txt, parse_mode="HTML")



@bot.message_handler(func=lambda m: m.text and m.text.lower() == "бонус", imc=True)
def get_bonus(message):
    uid = message.from_user.id
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return
    try:
        check(uid)
        u = get_user("real_id", uid)
        now = int(time.time())
        if u["time_kd"] != -1 and now - u["time_kd"] < 10800:
            rem = 10800 - (now - u["time_kd"])
            bot.reply_to(message, f"⏳Не так быстро! Подожди ещё:\n{rem//3600} ч. {(rem%3600)//60} мин. {rem%60} сек.")
            return
        amt = random.randint(100, 400)
        nkd = -1 if u["time_kd"] == -1 else now
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE Users SET coins = coins + ?, time_kd = ? WHERE real_id = ?", (amt, nkd, uid))
        bot.reply_to(message, f"📦Вы получили {amt}Ж. Возвращайтесь позже")
    finally: LOCKS[uid].release()



@bot.message_handler(func=lambda m: m.text and m.text.lower() == "-кд", imc=True)
def reset_cooldown(message):
    if message.from_user.id not in CHATS: return
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE Users SET time_kd = 0 WHERE real_id = ?", (message.from_user.id,))
    bot.reply_to(message, "Ваш личный КД на бонус был успешно обнулен")



@bot.message_handler(func=lambda m: m.text and m.text.lower() == "+кд", imc=True)
def toggle_cooldown(message):
    if message.from_user.id not in CHATS: return
    check(message.from_user.id)
    u = get_user("real_id", message.from_user.id)
    nkd, txt = (0, "КД включен") if u["time_kd"] == -1 else (-1, "КД выключен")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE Users SET time_kd = ? WHERE real_id = ?", (nkd, message.from_user.id))
    bot.reply_to(message, txt)



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().startswith('дать'))
def request_transfer(message):
    uid = message.from_user.id
    check(uid)
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "Используйте:\nдать [сумма] [айди]")
    try:
        amt = int(args[1])
        if amt <= 0:
            return bot.reply_to(message, "Минимальная сумма - 1Ж")
    except ValueError:
        return bot.reply_to(message, "Используйте:\nдать [сумма] [айди]")
    snd = get_user("real_id", uid)
    if not snd or int(snd["coins"]) < amt:
        return bot.reply_to(message, "Недостаточно средств")
    trg = None
    if len(args) > 2:
        t_id = args[2].replace('#', '')
        if t_id.isdigit(): trg = get_user("bot_id", int(t_id))
    elif message.reply_to_message:
        check(message.reply_to_message.from_user.id)
        trg = get_user("real_id", message.reply_to_message.from_user.id)
    if not trg or snd["bot_id"] == trg["bot_id"]:
        return bot.reply_to(message, "Пользователь не найден")
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("✅Подтвердить", callback_data=f"p_{snd['bot_id']}_{trg['bot_id']}_{amt}", style="success"))
    bot.reply_to(message, f'Вы уверены, что хотите перевести {amt}Ж на <a href="tg://user?id={trg["real_id"]}">#{trg["bot_id"]}</a>?', parse_mode="HTML", reply_markup=markup)



@bot.callback_query_handler(func=lambda c: c.data.startswith("p_"))
def confirm_transfer(call):
    _, s_bid, t_bid, amt_str = call.data.split("_")
    s_bid, t_bid, amt = int(s_bid), int(t_bid), int(amt_str)
    snd = get_user("bot_id", s_bid)
    if not snd or call.from_user.id != snd["real_id"]: return bot.answer_callback_query(call.id)
    bot.answer_callback_query(call.id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if int(cursor.execute("SELECT coins FROM Users WHERE bot_id = ?", (s_bid,)).fetchone()[0]) < amt:
            try: bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception: pass
            return
        conn.execute("UPDATE Users SET coins = coins - ? WHERE bot_id = ?", (amt, s_bid))
        conn.execute("UPDATE Users SET coins = coins + ? WHERE bot_id = ?", (amt, t_bid))
        conn.commit()
    trg = get_user("bot_id", t_bid)
    txt = f'💸<a href="tg://user?id={snd["real_id"]}">#{s_bid}</a> перевёл {amt}Ж на <a href="tg://user?id={trg["real_id"]}">#{t_bid}</a>'
    try: bot.edit_message_text(txt, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
    except Exception: pass



@bot.message_handler(imc=True, func=lambda m: m.text and m.text.lower().split() in [['лидер'], ['лидеры']])
def show_leaderboard(message):
    with sqlite3.connect(DB_PATH) as conn:
        leaders = conn.execute("SELECT bot_id, real_id, coins FROM Users WHERE coins > 0 ORDER BY coins DESC LIMIT 15").fetchall()
    txt = "<b>👑Топ-15 богачей</b>\n\n"
    if not leaders:
        txt += "Таблица пуста"
    else:
        for idx, row in enumerate(leaders, 1):
            txt += f"{idx}. <a href=\"tg://user?id={row[1]}\">#{row[0]}</a> — {row[2]:.2f}Ж\n"
    bot.reply_to(message, txt, parse_mode="HTML")



@bot.message_handler(imc=True, func=lambda m: m.text and m.from_user.id in CHATS and (m.text.lower().startswith('вж ') or m.text.lower().startswith('вл ')))
def admin_give_currency(message):
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "Используйте: вж/вл [сумма] [айди]")
    try:
        amt = int(args[1])
    except ValueError:
        return bot.reply_to(message, "Сумма должна быть целым числом")
    cmd = args[0].lower()
    field = "coins" if cmd == "вж" else "loks"
    lbl = "Ж" if cmd == "вж" else "Л"
    trg = None
    if len(args) > 2:
        t_id = args[2].replace('#', '')
        if t_id.isdigit():
            trg = get_user("bot_id", int(t_id))
    elif message.reply_to_message:
        check(message.reply_to_message.from_user.id)
        trg = get_user("real_id", message.reply_to_message.from_user.id)
    else:
        check(message.from_user.id)
        trg = get_user("real_id", message.from_user.id)
    if not trg:
        return bot.reply_to(message, "Пользователь не найден")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"UPDATE Users SET {field} = {field} + ? WHERE real_id = ?", (amt, trg["real_id"]))
    bot.reply_to(message, f"Выдано {amt}{lbl} игроку <a href=\"tg://user?id={trg['real_id']}\">#{trg['bot_id']}</a>", parse_mode="HTML")



@bot.message_handler(imc=True, func=lambda m: m.text and m.text.lower() in ['инфо', 'инфа', '/info', '/info@shittycircusbot'])
def send_info(message):
    bot.reply_to(message, "<b>ℹ️Информация о боте</b>\n\nОсновная валюта бота — жетоны (Ж). Их можно получать в бонусах и побеждая в играх.\nВторостепенная валюта — локсы (Л). В отличие от жетонов, с локсами почти ничего нельзя делать, и они служат активами.\n\n<b>Основные команды:</b>\n- Б — просмотр баланса\n- Бет [ставка] — игра на жетоны\n- Дать [сумма] — передача жетонов\n- Бонус — бесплатные жетоны\n- Лидер — топ-15 богачей\n- Курс — информация о локсах\n\nВ некоторых командах можно в конце указывать айди профиля, либо отвечать на сообщение нужного пользователя. Все элементы бота математически упрощены для простоты и комфорта. По любым вопросам — @yamexa", parse_mode="HTML")



# КОМАНДЫ КОМАНДЫ КОМАНДЫ
# КОМАНДЫ КОМАНДЫ КОМАНДЫ
# КОМАНДЫ КОМАНДЫ КОМАНДЫ
# КОМАНДЫ КОМАНДЫ КОМАНДЫ
# КОМАНДЫ КОМАНДЫ КОМАНДЫ



def get_bet_keyboard(g_type, bid, bet, orig_id):
    markup = InlineKeyboardMarkup()
    games = [("🎲", "dice"), ("🎳", "bowl"), ("⚽", "foot"), ("🏀", "bask"), ("🎯", "dart"), ("🎰", "slot")]
    markup.row(*[InlineKeyboardButton(icon, callback_data=f"gm_{g_id}_{bid}_{bet}_{orig_id}", style="primary" if g_id == g_type else "default") for icon, g_id in games])
    if g_type == "dice":
        markup.row(InlineKeyboardButton("Чётное х2", callback_data=f"betg_dice_even_{bid}_{bet}_{orig_id}"), InlineKeyboardButton("Нечётное х2", callback_data=f"betg_dice_odd_{bid}_{bet}_{orig_id}"))
        markup.row(InlineKeyboardButton("Больше х2", callback_data=f"betg_dice_big_{bid}_{bet}_{orig_id}"), InlineKeyboardButton("Меньше х2", callback_data=f"betg_dice_small_{bid}_{bet}_{orig_id}"))
        markup.row(*[InlineKeyboardButton(f"{i} х6", callback_data=f"betg_dice_n{i}_{bid}_{bet}_{orig_id}") for i in range(1, 4)])
        markup.row(*[InlineKeyboardButton(f"{i} х6", callback_data=f"betg_dice_n{i}_{bid}_{bet}_{orig_id}") for i in range(4, 7)])
    elif g_type == "dart":
        markup.row(InlineKeyboardButton("Промах х6", callback_data=f"betg_dart_miss_{bid}_{bet}_{orig_id}"), InlineKeyboardButton("Яблочко х6", callback_data=f"betg_dart_bull_{bid}_{bet}_{orig_id}"))
        markup.row(InlineKeyboardButton("Ординал х1.65", callback_data=f"betg_dart_ord_{bid}_{bet}_{orig_id}"))
    elif g_type == "bowl":
        markup.row(InlineKeyboardButton("Промах х6", callback_data=f"betg_bowl_miss_{bid}_{bet}_{orig_id}"), InlineKeyboardButton("Страйк х6", callback_data=f"betg_bowl_strike_{bid}_{bet}_{orig_id}"))
        markup.row(InlineKeyboardButton("Попадание х1.65", callback_data=f"betg_bowl_hit_{bid}_{bet}_{orig_id}"))
    elif g_type == "foot":
        markup.row(InlineKeyboardButton("Провал х1.6", callback_data=f"betg_foot_fail_{bid}_{bet}_{orig_id}"), InlineKeyboardButton("Гол х1.4", callback_data=f"betg_foot_goal_{bid}_{bet}_{orig_id}"))
    elif g_type == "bask":
        markup.row(InlineKeyboardButton("Непопадание х1.6", callback_data=f"betg_bask_fail_{bid}_{bet}_{orig_id}"), InlineKeyboardButton("Попадание х1.4", callback_data=f"betg_bask_hit_{bid}_{bet}_{orig_id}"))
    elif g_type == "slot":
        markup.row(InlineKeyboardButton("777 х16", callback_data=f"betg_slot_777_{bid}_{bet}_{orig_id}"), InlineKeyboardButton("3xBAR х16", callback_data=f"betg_slot_bar_{bid}_{bet}_{orig_id}"))
        markup.row(InlineKeyboardButton("🍇🍇🍇 х16", callback_data=f"betg_slot_grape_{bid}_{bet}_{orig_id}"), InlineKeyboardButton("🍋🍋🍋 х16", callback_data=f"betg_slot_lemon_{bid}_{bet}_{orig_id}"))
    return markup

@bot.message_handler(imc=True, func=lambda m: m.text and (m.text.lower().startswith('бет ') or m.text.lower().startswith('бэт ')))
def start_bet_game(message):
    uid = message.from_user.id
    check(uid)
    args = message.text.split()
    try:
        bet = int(args[1])
    except (IndexError, ValueError, TypeError): return
    if bet < 100:
        return bot.reply_to(message, "Минимальная ставка — 100Ж")
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return
    try:
        u = get_user("real_id", uid)
        if int(u["coins"]) < bet: return bot.reply_to(message, "Недостаточно средств")
        bot.reply_to(message, f"👤<a href=\"tg://user?id={uid}\">#{u['bot_id']}</a>\nСтавка: {bet}Ж", parse_mode="HTML", reply_markup=get_bet_keyboard("dice", u["bot_id"], bet, message.message_id))
    finally: LOCKS[uid].release()

@bot.callback_query_handler(func=lambda c: c.data.startswith("gm_"))
def change_game_menu(call):
    _, g_type, s_bid, bet_str, orig_id = call.data.split("_")
    s_bid, bet, orig_id = int(s_bid), int(bet_str), int(orig_id)
    u = get_user("bot_id", s_bid)
    if not u or call.from_user.id != u["real_id"]: return bot.answer_callback_query(call.id)
    bot.answer_callback_query(call.id)
    try: bot.edit_message_text(f"👤<a href=\"tg://user?id={u['real_id']}\">#{s_bid}</a>\nСтавка: {bet}Ж", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_bet_keyboard(g_type, s_bid, bet, orig_id))
    except Exception: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("betg_"))
def process_bet_game(call):
    _, g_type, mode, s_bid, bet_str, orig_id = call.data.split("_")
    s_bid, bet, orig_id = int(s_bid), int(bet_str), int(orig_id)
    u = get_user("bot_id", s_bid)
    if not u or call.from_user.id != u["real_id"]: return bot.answer_callback_query(call.id)
    uid = u["real_id"]
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return bot.answer_callback_query(call.id)
    bot.answer_callback_query(call.id)
    try:
        u_fresh = get_user("real_id", uid)
        if int(u_fresh["coins"]) < bet:
            try: bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception: pass
            return
        try: bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception: pass
        emoji_map = {"dice": "🎲", "bowl": "🎳", "foot": "⚽", "bask": "🏀", "dart": "🎯", "slot": "🎰"}
        try: msg = bot.send_dice(chat_id=call.message.chat.id, emoji=emoji_map[g_type], reply_to_message_id=orig_id)
        except Exception: msg = bot.send_dice(chat_id=call.message.chat.id, emoji=emoji_map[g_type])
        val = msg.dice.value
        time.sleep(3.5 if g_type in ["slot", "bowl", "foot", "bask"] else 2.0)
        win, mult, mode_lbl = False, 0.0, ""
        if g_type == "dice":
            mode_labels = {"even": "Чётное", "odd": "Нечётное", "big": "Больше", "small": "Меньше", "n1":"1", "n2":"2", "n3":"3", "n4":"4", "n5":"5", "n6":"6"}
            mode_lbl = mode_labels.get(mode, mode)
            if mode == "even" and val % 2 == 0: win, mult = True, 2.0
            elif mode == "odd" and val % 2 != 0: win, mult = True, 2.0
            elif mode == "big" and val > 3: win, mult = True, 2.0
            elif mode == "small" and val <= 3: win, mult = True, 2.0
            elif mode.startswith("n") and val == int(mode[1:]): win, mult = True, 6.0
        elif g_type == "dart":
            mode_labels = {"miss": "Промах", "bull": "Яблочко", "ord": "Ординал"}
            mode_lbl = mode_labels.get(mode, mode)
            if mode == "miss" and val == 1: win, mult = True, 6.0
            elif mode == "bull" and val == 6: win, mult = True, 6.0
            elif mode == "ord" and val in (2, 3, 4, 5): win, mult = True, 1.65
        elif g_type == "bowl":
            mode_labels = {"miss": "Промах", "strike": "Страйк", "hit": "Попадание"}
            mode_lbl = mode_labels.get(mode, mode)
            if mode == "miss" and val == 1: win, mult = True, 6.0
            elif mode == "strike" and val == 6: win, mult = True, 6.0
            elif mode == "hit" and val in (2, 3, 4, 5): win, mult = True, 1.65
        elif g_type == "foot":
            mode_labels = {"fail": "Провал", "goal": "Гол"}
            mode_lbl = mode_labels.get(mode, mode)
            if mode == "fail" and val in (1, 2, 3): win, mult = True, 1.6
            elif mode == "goal" and val in (4, 5): win, mult = True, 1.4
        elif g_type == "bask":
            mode_labels = {"fail": "Непопадание", "hit": "Попадание"}
            mode_lbl = mode_labels.get(mode, mode)
            if mode == "fail" and val in (1, 2, 3): win, mult = True, 1.6
            elif mode == "hit" and val in (4, 5): win, mult = True, 1.4
        elif g_type == "slot":
            mode_labels = {"777": "777", "bar": "3xBAR", "grape": "🍇🍇🍇", "lemon": "🍋🍋🍋"}
            mode_lbl = mode_labels.get(mode, mode)
            if mode == "777" and val == 64: win, mult = True, 16.0
            elif mode == "bar" and val == 1: win, mult = True, 16.0
            elif mode == "grape" and val == 22: win, mult = True, 16.0
            elif mode == "lemon" and val == 43: win, mult = True, 16.0
        mention = f'<a href="tg://user?id={uid}">#{s_bid}</a>'
        with sqlite3.connect(DB_PATH) as conn:
            if win:
                profit = int(round(bet * mult - bet))
                conn.execute("UPDATE Users SET coins = coins + ?, wins = wins + 1 WHERE real_id = ?", (profit, uid))
                txt = f"🌹Поздравляем, {mention}! Вы угадали исход и забрали {profit}Ж\n\nВыбранный исход: {mode_lbl}"
            else:
                conn.execute("UPDATE Users SET coins = coins - ?, losses = losses + 1 WHERE real_id = ?", (bet, uid))
                txt = f"🥀{mention}, вы проиграли {bet}Ж\n\nВыбранный исход: {mode_lbl}"
            conn.commit()
        bot.send_message(chat_id=call.message.chat.id, text=txt, parse_mode="HTML")
    finally: LOCKS[uid].release()



init_db()
print("есть")
bot.infinity_polling()