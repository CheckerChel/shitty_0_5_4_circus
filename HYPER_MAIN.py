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
			active_name_id INTEGER DEFAULT NULL,
			coins INTEGER DEFAULT 0,
			loks INTEGER DEFAULT 0,
			time_kd INTEGER DEFAULT 0,
			time_loks INTEGER DEFAULT 0,
			wins INTEGER DEFAULT 0,
			losses INTEGER DEFAULT 0
		)
		""")
        cursor.execute("""
		CREATE TABLE IF NOT EXISTS UserNames (
			name_id INTEGER PRIMARY KEY AUTOINCREMENT,
			owner_id INTEGER NOT NULL,
			name_value TEXT NOT NULL,
			FOREIGN KEY(owner_id) REFERENCES Users(real_id)
		)
		""")
        cursor.execute("PRAGMA table_info(Users)")
        cols = [col[1] for col in cursor.fetchall()]
        if "active_name_id" not in cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN active_name_id INTEGER DEFAULT NULL")
        if "all_names" not in cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN all_names INTEGER DEFAULT 0")
        if "last_bet" not in cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN last_bet INTEGER DEFAULT 0")
        if "all_keys" not in cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN all_keys INTEGER DEFAULT 0")
        
        cursor.execute("""
        UPDATE Users 
        SET all_names = (
            SELECT COUNT(*) 
            FROM UserNames 
            WHERE UserNames.owner_id = Users.real_id
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



def check(id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM Users WHERE real_id = ?", (id,))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO Users (real_id) VALUES (?)", (id,))
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



@bot.message_handler(imc=True, func=lambda m: m.text and m.from_user.id in CHATS and m.text.lower() == '-весь кд')
def admin_reset_all_cooldowns(message):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE Users SET time_kd = 0, time_loks = 0")
    bot.reply_to(message, "<b>🚨КД на бонус сброшены у всех пользователей!</b>", parse_mode="HTML")

@bot.message_handler(imc=True, func=lambda m: m.text and m.from_user.id in CHATS and m.text.lower() == '-весь кд')
def admin_reset_all_cooldowns(message):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE Users SET time_kd = 0, time_loks = 0")
    bot.reply_to(message, "🚨<b>КД на бонус обнулён у всех пользователей!</b>", parse_mode="HTML")




@bot.message_handler(imc=True, func=lambda m: m.text and re.match(r'^\+имя($|\s)', m.text.lower()))
def buy_name_into_collection(message):
    uid = message.from_user.id
    check(uid)
    name_arg = message.text[5:].strip()
    if not name_arg:
        return bot.reply_to(message, "Использование: +имя [ваше имя]")
    if not (3 <= len(name_arg) <= 20) or not re.match(r'^[а-яА-ЯёЁ0-9 ]+$', name_arg):
        return bot.reply_to(message, "Имя должно быть от 3 до 20 символов и содержать только русские буквы, цифры и пробелы")
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return
    try:
        u = get_user("real_id", uid)
        if int(u["coins"]) < 5000:
            return bot.reply_to(message, "Недостаточно средств")
        with sqlite3.connect(DB_PATH) as conn:
            existing = conn.execute("SELECT owner_id FROM UserNames WHERE name_value = ? COLLATE NOCASE", (name_arg,)).fetchone()
        if existing:
            owner = get_user("real_id", existing[0])
            return bot.reply_to(message, f"Извините, но данное имя уже принадлежит <a href=\"tg://user?id={owner['real_id']}\">#{owner['bot_id']}</a>", parse_mode="HTML")
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("✅Подтвердить", callback_data=f"buyname_{u['bot_id']}_{name_arg}", style="success"))
        bot.reply_to(message, f"Вы уверены, что хотите приобрести себе имя «{name_arg}» за 5000Ж?", reply_markup=markup)
    finally: LOCKS[uid].release()



@bot.message_handler(imc=True, func=lambda m: m.text and m.text.lower() == '-имя')
def remove_active_name(message):
    uid = message.from_user.id
    check(uid)
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return
    try:
        u = get_user("real_id", uid)
        if u["active_name_id"] is None:
            return bot.reply_to(message, "У вас не установлено имя")
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE Users SET active_name_id = NULL WHERE real_id = ?", (uid,))
        bot.reply_to(message, "Вы успешно отключили отображение имени")
    finally: LOCKS[uid].release()



@bot.message_handler(imc=True, func=lambda m: m.text and re.match(r'^выдать имя($|\s)', m.text.lower()))
def admin_give_name(message):
    if message.from_user.id not in CHATS: return
    if not message.reply_to_message:
        return bot.reply_to(message, "Чтобы выдать имя, ответьте этой командой на сообщение нужного игрока")
    name_arg = message.text[11:].strip()
    if not name_arg:
        return bot.reply_to(message, "Использование: выдать имя [имя] (в ответ на сообщение)")
    target_id = message.reply_to_message.from_user.id
    check(target_id)
    trg = get_user("real_id", target_id)
    if not trg:
        return bot.reply_to(message, "Пользователь не найден в базе")
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute("SELECT owner_id FROM UserNames WHERE name_value = ? COLLATE NOCASE", (name_arg,)).fetchone()
        if existing:
            owner = get_user("real_id", existing[0])
            return bot.reply_to(message, f"Извините, но данное имя уже принадлежит <a href=\"tg://user?id={owner['real_id']}\">#{owner['bot_id']}</a>", parse_mode="HTML")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO UserNames (owner_id, name_value) VALUES (?, ?)", (target_id, name_arg))
        conn.commit()
    mention = f'<a href="tg://user?id={target_id}">#{trg["bot_id"]}</a>'
    bot.reply_to(message, f"Имя «{name_arg}» выдано для {mention}", parse_mode="HTML")



@bot.callback_query_handler(func=lambda c: c.data.startswith("buyname_"))
def confirm_buy_name(call):
    parts = call.data.split("_", 2)
    s_bid = int(parts[1])
    name_arg = parts[2]
    u = get_user("bot_id", s_bid)
    if not u or call.from_user.id != u["real_id"]: return bot.answer_callback_query(call.id)
    uid = u["real_id"]
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return bot.answer_callback_query(call.id)
    bot.answer_callback_query(call.id)
    try:
        u_fresh = get_user("real_id", uid)
        if int(u_fresh["coins"]) < 5000:
            try: bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception: pass
            return
        with sqlite3.connect(DB_PATH) as conn:
            existing = conn.execute("SELECT owner_id FROM UserNames WHERE name_value = ? COLLATE NOCASE", (name_arg,)).fetchone()
            if existing:
                owner = get_user("real_id", existing)
                try: bot.edit_message_text(f"Извините, но данное имя уже принадлежит <a href=\"tg://user?id={owner['real_id']}\">#{owner['bot_id']}</a>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
                except Exception: pass
                return
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET coins = coins - 5000 WHERE real_id = ?", (uid,))
            cursor.execute("INSERT INTO UserNames (owner_id, name_value) VALUES (?, ?)", (uid, name_arg))
            conn.commit()
        mention = f'<a href="tg://user?id={uid}">#{s_bid}</a>'
        try: bot.edit_message_text(f"{mention} приобрёл себе имя «{name_arg}»", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
        except Exception: pass
    finally: LOCKS[uid].release()



@bot.message_handler(imc=True, func=lambda m: m.text and re.match(r'^установить имя($|\s)', m.text.lower()))
def set_active_name(message):
    uid = message.from_user.id
    check(uid)
    arg = message.text[15:].strip()
    if not arg.isdigit():
        return bot.reply_to(message, "Укажите корректный номер имени числом")
    nid = int(arg)
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            name_row = conn.execute("SELECT name_id, owner_id, name_value FROM UserNames WHERE name_id = ?", (nid,)).fetchone()
        if not name_row:
            return bot.reply_to(message, "Данного номера не существует")
        if name_row[1] != uid:
            return bot.reply_to(message, "Это не ваше имя")
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE Users SET active_name_id = ? WHERE real_id = ?", (nid, uid))
        bot.reply_to(message, f"Вы успешно установили имя «{name_row[2]}» как активное")
    finally: LOCKS[uid].release()



def build_names_page(target_uid, viewer_bid, page):
    u = get_user("real_id", target_uid)
    with sqlite3.connect(DB_PATH) as conn:
        all_names = conn.execute("SELECT name_id, name_value FROM UserNames WHERE owner_id = ? ORDER BY name_id ASC", (target_uid,)).fetchall()
    total = len(all_names)
    pages_count = max(1, math.ceil(total / 20))
    if page < 1: page = 1
    if page > pages_count: page = pages_count
    txt = f"<b>📒Коллекция Имён <a href=\"tg://user?id={u['real_id']}\">#{u['bot_id']}</a></b>\n\n"
    if not all_names:
        txt += "В коллекции пока нет имён.\n\n"
    else:
        start_idx = (page - 1) * 20
        end_idx = start_idx + 20
        page_names = all_names[start_idx:end_idx]
        for idx, row in enumerate(page_names, start=start_idx + 1):
            txt += f"{idx}. #{row[0]} — {row[1]}\n"
        txt += "\n"
    txt += f"Стр. {page}/{pages_count}"
    markup = InlineKeyboardMarkup()
    if pages_count > 1:
        prev_cb = f"nav_{viewer_bid}_{u['bot_id']}_{page-1}" if page > 1 else "nav_noop"
        next_cb = f"nav_{viewer_bid}_{u['bot_id']}_{page+1}" if page < pages_count else "nav_noop"
        markup.row(InlineKeyboardButton("⬅️", callback_data=prev_cb), InlineKeyboardButton("➡️", callback_data=next_cb))
    return txt, markup



@bot.message_handler(imc=True, func=lambda m: m.text and re.match(r'^имена($|\s)', m.text.lower()))
def show_names_collection(message):
    viewer_uid = message.from_user.id
    check(viewer_uid)
    viewer_user = get_user("real_id", viewer_uid)
    target_uid, is_bot = viewer_uid, False
    if message.reply_to_message:
        target_uid = message.reply_to_message.from_user.id
    else:
        args = message.text.split(maxsplit=1)
        if len(args) > 1:
            clean_arg = args[1].replace('#', '').strip()
            if clean_arg.isdigit():
                target_uid, is_bot = int(clean_arg), True
            else:
                return bot.reply_to(message, "Укажите корректный #ID пользователя или ответьте на его сообщение")
    if not is_bot and target_uid == message.from_user.id:
        check(target_uid)
    t_user = get_user("bot_id" if is_bot else "real_id", target_uid)
    if not t_user:
        return bot.reply_to(message, "Пользователь не найден")
    txt, markup = build_names_page(t_user["real_id"], viewer_user["bot_id"], 1)
    bot.reply_to(message, txt, parse_mode="HTML", reply_markup=markup if markup.keyboard else None)



@bot.callback_query_handler(func=lambda c: c.data.startswith("nav_"))
def navigate_names_collection(call):
    if call.data == "nav_noop":
        return bot.answer_callback_query(call.id)
    _, v_bid, t_bid, page_str = call.data.split("_")
    v_bid, t_bid, page = int(v_bid), int(t_bid), int(page_str)
    viewer = get_user("bot_id", v_bid)
    if not viewer or call.from_user.id != viewer["real_id"]:
        return bot.answer_callback_query(call.id, "Вы не можете управлять этим меню", show_alert=True)
    target = get_user("bot_id", t_bid)
    if not target:
        return bot.answer_callback_query(call.id)
    bot.answer_callback_query(call.id)
    txt, markup = build_names_page(target["real_id"], v_bid, page)
    try: bot.edit_message_text(txt, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup if markup.keyboard else None)
    except Exception: pass



@bot.message_handler(imc=True, func=lambda m: m.text and re.match(r'^имя дать($|\s)', m.text.lower()))
def gift_name_request(message):
    uid = message.from_user.id
    check(uid)
    raw_args = message.text[8:].strip()
    if not raw_args:
        return bot.reply_to(message, "Использование: имя дать [номер]")
    args = raw_args.split()
    if not args[0].isdigit():
        return bot.reply_to(message, "Первым аргументом должен быть числовой номер вашего имени")
    nid = int(args[0])
    is_bot = False
    if len(args) > 1 and args[1].replace('#', '').isdigit():
        target_id = int(args[1].replace('#', ''))
        is_bot = True
    elif message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    else:
        return bot.reply_to(message, "Укажите айди игрока или ответьте на его сообщение")
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return
    try:
        snd = get_user("real_id", uid)
        trg = get_user("bot_id" if is_bot else "real_id", target_id)
        if not trg:
            return bot.reply_to(message, "Пользователь не найден")
        if snd["bot_id"] == trg["bot_id"]:
            return bot.reply_to(message, "Нельзя передать имя самому себе")
        with sqlite3.connect(DB_PATH) as conn:
            name_row = conn.execute("SELECT name_id, owner_id FROM UserNames WHERE name_id = ?", (nid,)).fetchone()
        if not name_row:
            return bot.reply_to(message, "Данного номера имени не существует")
        if name_row[1] != uid:
            return bot.reply_to(message, "Это не ваше имя")
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("✅Подтвердить", callback_data=f"gname_{snd['bot_id']}_{trg['bot_id']}_{nid}", style="success"))
        bot.reply_to(message, f"Вы уверены, что хотите передать имя #{nid} на <a href=\"tg://user?id={trg['real_id']}\">#{trg['bot_id']}</a>?", parse_mode="HTML", reply_markup=markup)
    finally: LOCKS[uid].release()



@bot.callback_query_handler(func=lambda c: c.data.startswith("gname_"))
def confirm_gift_name(call):
    _, s_bid, t_bid, nid_str = call.data.split("_")
    s_bid, t_bid, nid = int(s_bid), int(t_bid), int(nid_str)
    snd = get_user("bot_id", s_bid)
    if not snd or call.from_user.id != snd["real_id"]:
        return bot.answer_callback_query(call.id, "Вы не можете управлять этим меню", show_alert=True)
    uid = snd["real_id"]
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return bot.answer_callback_query(call.id)
    bot.answer_callback_query(call.id)
    try:
        trg = get_user("bot_id", t_bid)
        if not trg:
            try: bot.edit_message_text("Пользователь не найден", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception: pass
            return
        with sqlite3.connect(DB_PATH) as conn:
            name_row = conn.execute("SELECT name_id, owner_id, name_value FROM UserNames WHERE name_id = ?", (nid,)).fetchone()
            if not name_row or name_row[1] != uid:
                try: bot.edit_message_text("Имя больше вам не принадлежит или не существует", chat_id=call.message.chat.id, message_id=call.message.message_id)
                except Exception: pass
                return
            conn.execute("UPDATE UserNames SET owner_id = ? WHERE name_id = ?", (trg["real_id"], nid))
            conn.execute("UPDATE Users SET active_name_id = NULL WHERE real_id = ? AND active_name_id = ?", (uid, nid))
            conn.commit()
        mention_snd = f'<a href="tg://user?id={uid}">#{s_bid}</a>'
        mention_trg = f'<a href="tg://user?id={trg["real_id"]}">#{t_bid}</a>'
        try: bot.edit_message_text(f"🎁{mention_snd} передал имя #{nid} на {mention_trg}", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
        except Exception: pass
    finally: LOCKS[uid].release()



@bot.message_handler(imc=True, func=lambda m: m.text and re.match(r'^имя\s+\d+$', m.text.lower().strip()))
def show_name_info(message):
    arg = message.text[4:].strip()
    nid = int(arg)
    with sqlite3.connect(DB_PATH) as conn:
        name_row = conn.execute("SELECT name_id, owner_id, name_value FROM UserNames WHERE name_id = ?", (nid,)).fetchone()
    if not name_row:
        return bot.reply_to(message, "Данного номера имени не существует")
    owner_uid = name_row[1]
    name_val = name_row[2]
    owner = get_user("real_id", owner_uid)
    if not owner:
        return bot.reply_to(message, "Владелец имени не найден в базе данных")
    txt = (
        f"🪪Имя #{nid}\n"
        f"Владелец: <a href=\"tg://user?id={owner['real_id']}\">#{owner['bot_id']}</a>\n"
        f"Текст: «{name_val}»"
    )
    bot.reply_to(message, txt, parse_mode="HTML")



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



@bot.message_handler(imc=True, func=lambda m: m.text and re.match(r'^кл($|\s)', m.text.lower()))
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
        bot.reply_to(message, f"Вы уверены, что хотите приобрести {amount}Л за {cost}Ж?\nНа момент подтверждения курс может измениться", reply_markup=markup)
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



@bot.message_handler(imc=True, func=lambda m: m.text and re.match(r'^пл($|\s)', m.text.lower()))
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
        bot.reply_to(message, f"Вы уверены, что хотите продать {amount}Л за {revenue}Ж?\nНа момент подтверждения курс может измениться", reply_markup=markup)
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



@bot.message_handler(imc=True, func=lambda m: m.text and re.match(r'^л($|\s)', m.text.lower().strip()))
def get_loks_balance(message):
    t_id, is_bot = message.from_user.id, False
    if message.reply_to_message:
        t_id = message.reply_to_message.from_user.id
    else:
        args = message.text.split(maxsplit=1)
        if len(args) > 1:
            clean_arg = args[1].replace('#', '').strip()
            if clean_arg.isdigit():
                t_id, is_bot = int(clean_arg), True
    if not is_bot and t_id == message.from_user.id:
        check(t_id)
    u = get_user("bot_id" if is_bot else "real_id", t_id)
    if not u:
        return bot.reply_to(message, "Пользователь не найден")
    user_label = f'<a href="tg://user?id={u["real_id"]}">#{u["bot_id"]}</a>'
    if u["active_name_id"]:
        with sqlite3.connect(DB_PATH) as conn:
            active_name = conn.execute("SELECT name_value FROM UserNames WHERE name_id = ?", (u["active_name_id"],)).fetchone()
        if active_name:
            user_label += f', {active_name[0]}'
    total_loks = get_total_loks()
    estimated_coins = calc_sell_return(total_loks, int(u["loks"]))
    txt = (
        f'👤{user_label}\n'
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
        f"️Цена за 1Л — {price}Ж\n"
        f"Комиссия — {fee_val}%\n\n"
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



@bot.message_handler(imc=True, func=lambda m: m.text and re.match(r'^б($|\s)', m.text.lower().strip()))
def get_balance(message):
    t_id, is_bot = message.from_user.id, False
    if message.reply_to_message:
        t_id = message.reply_to_message.from_user.id
    else:
        args = message.text.split(maxsplit=1)
        if len(args) > 1:
            clean_arg = args[1].replace('#', '').strip()
            if clean_arg.isdigit():
                t_id, is_bot = int(clean_arg), True
    if not is_bot and t_id == message.from_user.id:
        check(t_id)
    u = get_user("bot_id" if is_bot else "real_id", t_id)
    if not u:
        return bot.reply_to(message, "Пользователь не найден")
    user_label = f'<a href="tg://user?id={u["real_id"]}">#{u["bot_id"]}</a>'
    if u["active_name_id"]:
        with sqlite3.connect(DB_PATH) as conn:
            active_name = conn.execute("SELECT name_value FROM UserNames WHERE name_id = ?", (u["active_name_id"],)).fetchone()
        if active_name:
            user_label += f', {active_name[0]}'
    txt = (
        f'👤{user_label}\n\n'
        f'💰Жетонов: {int(u["coins"])}Ж\n'
        f'🪙Локсов: {int(u["loks"])}Л\n'
        f'🗨️Кол-во Имён: {int(u["all_names"])}\n'
        f'🔑Ключей: {int(u["all_keys"])}\n'
        f'🌹Побед: {int(u["wins"])}\n'
        f'🥀Проигрышей: {int(u["losses"])}'
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
        if u["time_kd"] != -1 and now - u["time_kd"] < 5400:
            rem = 5400 - (now - u["time_kd"])
            bot.reply_to(message, f"⏳Не так быстро! Подожди ещё:\n{rem//3600} ч. {(rem%3600)//60} мин. {rem%60} сек.")
            return
        
        nkd = -1 if u["time_kd"] == -1 else now
        
        if random.random() < 0.01:
            amt = random.randint(1000, 3000)
            keys_amt = random.randint(1, 3)
            keys_word = "ключ" if keys_amt == 1 else "ключа"
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("UPDATE Users SET coins = coins + ?, all_keys = all_keys + ?, time_kd = ? WHERE real_id = ?", (amt, keys_amt, nkd, uid))
            bot.reply_to(message, f"💥Джекпот! Вы получили {amt}Ж и {keys_amt} {keys_word}. Возвращайтесь позже")
        else:
            amt = random.randint(100, 400)
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("UPDATE Users SET coins = coins + ?, time_kd = ? WHERE real_id = ?", (amt, nkd, uid))
            bot.reply_to(message, f"📦Вы получили {amt}Ж. Возвращайтесь позже")
            
    finally: LOCKS[uid].release()



@bot.message_handler(imc=True, func=lambda m: m.text and m.from_user.id in CHATS and m.text.lower().startswith('вк '))
def admin_give_keys(message):
    args = message.text.split()
    try:
        amt = int(args[1])
    except (IndexError, ValueError):
        return bot.reply_to(message, "Используйте: вк [число]")
        
    uid = message.from_user.id
    check(uid)
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE Users SET all_keys = all_keys + ? WHERE real_id = ?", (amt, uid))
        
    bot.reply_to(message, f"Вы успешно выдали себе {amt} кл.")



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



@bot.message_handler(imc=True, func=lambda m: m.text and (m.text.lower().startswith('ключ дать') or m.text.lower().startswith('ключи дать')))
def gift_keys_request(message):
    uid = message.from_user.id
    check(uid)
    cmd_len = 10 if message.text.lower().startswith('ключ дать') else 11
    raw_args = message.text[cmd_len:].strip()
    if not raw_args:
        return bot.reply_to(message, "Использование: ключ дать [кол-во] [айди]")
    args = raw_args.split()
    try:
        amt = int(args[0])
        if amt <= 0: raise ValueError
    except (IndexError, ValueError):
        return bot.reply_to(message, "Укажите корректное положительное число ключей")
    is_bot = False
    if len(args) > 1 and args[1].replace('#', '').isdigit():
        target_id = int(args[1].replace('#', ''))
        is_bot = True
    elif message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    else:
        return bot.reply_to(message, "Укажите айди игрока или ответьте на его сообщение")
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return
    try:
        snd = get_user("real_id", uid)
        trg = get_user("bot_id" if is_bot else "real_id", target_id)
        if not trg:
            return bot.reply_to(message, "Пользователь не найден")
        if snd["bot_id"] == trg["bot_id"]:
            return bot.reply_to(message, "Нельзя передать ключи самому себе")
        if int(snd["all_keys"]) < amt:
            return bot.reply_to(message, "Недостаточно ключей для передачи")
        
        if amt % 10 == 1 and amt % 100 != 11: kw = "ключ"
        elif amt % 10 in (2, 3, 4) and amt % 100 not in (12, 13, 14): kw = "ключа"
        else: kw = "ключей"
        
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("✅Подтвердить", callback_data=f"gkey_{snd['bot_id']}_{trg['bot_id']}_{amt}", style="success"))
        bot.reply_to(message, f"Вы уверены, что хотите передать {amt} {kw} на <a href=\"tg://user?id={trg['real_id']}\">#{trg['bot_id']}</a>?", parse_mode="HTML", reply_markup=markup)
    finally: LOCKS[uid].release()



@bot.callback_query_handler(func=lambda c: c.data.startswith("gkey_"))
def confirm_gift_keys(call):
    _, s_bid, t_bid, amt_str = call.data.split("_")
    s_bid, t_bid, amt = int(s_bid), int(t_bid), int(amt_str)
    snd = get_user("bot_id", s_bid)
    if not snd or call.from_user.id != snd["real_id"]:
        return bot.answer_callback_query(call.id, "Вы не можете управлять этим меню", show_alert=True)
    uid = snd["real_id"]
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return bot.answer_callback_query(call.id)
    bot.answer_callback_query(call.id)
    try:
        trg = get_user("bot_id", t_bid)
        if not trg:
            try: bot.edit_message_text("Пользователь не найден", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception: pass
            return
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            current_keys = cursor.execute("SELECT all_keys FROM Users WHERE real_id = ?", (uid,)).fetchone()[0]
            if current_keys < amt:
                try: bot.edit_message_text("У вас уже недостаточно ключей", chat_id=call.message.chat.id, message_id=call.message.message_id)
                except Exception: pass
                return
            conn.execute("UPDATE Users SET all_keys = all_keys - ? WHERE real_id = ?", (amt, uid))
            conn.execute("UPDATE Users SET all_keys = all_keys + ? WHERE real_id = ?", (trg["real_id"], amt))
            conn.commit()
            
        if amt % 10 == 1 and amt % 100 != 11: kw = "ключ"
        elif amt % 10 in (2, 3, 4) and amt % 100 not in (12, 13, 14): kw = "ключа"
        else: kw = "ключей"
            
        mention_snd = f'<a href="tg://user?id={uid}">#{s_bid}</a>'
        mention_trg = f'<a href="tg://user?id={trg["real_id"]}">#{t_bid}</a>'
        try: bot.edit_message_text(f"🔑{mention_snd} передал {amt} {kw} на {mention_trg}", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
        except Exception: pass
    finally: LOCKS[uid].release()



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



@bot.message_handler(imc=True, func=lambda m: m.text and m.text.lower().strip() == 'вернуть')
def rollback_bet_request(message):
    uid = message.from_user.id
    check(uid)
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return
    try:
        u = get_user("real_id", uid)
        if int(u["all_keys"]) <= 0:
            return bot.reply_to(message, "Недостаточно ключей")
        if int(u["last_bet"]) <= 0:
            return bot.reply_to(message, "У вас нет последней проигранной игры")
        
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("✅Подтвердить", callback_data=f"rbet_{u['bot_id']}", style="success"))
        bot.reply_to(message, f"Вы уверены что хотите вернуть себе {int(u['last_bet'])}Ж с последней проигранной игры?", reply_markup=markup)
    finally: LOCKS[uid].release()



@bot.callback_query_handler(func=lambda c: c.data.startswith("rbet_"))
def confirm_rollback_bet(call):
    s_bid = int(call.data.split("_")[1])
    u = get_user("bot_id", s_bid)
    if not u or call.from_user.id != u["real_id"]: 
        return bot.answer_callback_query(call.id, "Вы не можете управлять этим меню", show_alert=True)
    uid = u["real_id"]
    if uid not in LOCKS: LOCKS[uid] = threading.Lock()
    if not LOCKS[uid].acquire(blocking=False): return bot.answer_callback_query(call.id)
    bot.answer_callback_query(call.id)
    try:
        u_fresh = get_user("real_id", uid)
        if int(u_fresh["all_keys"]) <= 0:
            try: bot.edit_message_text("Недостаточно ключей", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception: pass
            return
        if int(u_fresh["last_bet"]) <= 0:
            try: bot.edit_message_text("У вас нет последней проигранной игры", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception: pass
            return
            
        return_sum = int(u_fresh["last_bet"])
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE Users SET coins = coins + ?, all_keys = all_keys - 1, last_bet = 0 WHERE real_id = ?", (return_sum, uid))
            conn.commit()
            
        mention = f'<a href="tg://user?id={uid}">#{s_bid}</a>'
        try: bot.edit_message_text(f"💸{mention} использовал ключ и вернул себе {return_sum}Ж", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
        except Exception: pass
    finally: LOCKS[uid].release()



@bot.message_handler(imc=True, func=lambda m: m.text and m.text.lower() in ['инфо', 'инфа', '/info', '/info@shittycircusbot'])
def send_info(message):
    bot.reply_to(message, "<b>ℹ️Информация о боте</b>\n\nОсновная валюта бота — жетоны (Ж). Их можно получать в бонусах и побеждая в играх.\nВторостепенная валюта — локсы (Л). В отличие от жетонов, с локсами почти ничего нельзя делать, и они служат активами.\nИмена — это эксклюзивные элементы профиля. Каждое Имя увеличивает любой итоговый выигрыш на +1%, суммирование разрешено вплоть до +25%.\nКлючи — полезные элементы, дающие возможность вернуть ставку обратно от последней проигранной игры. Найти их можно в бонусе.\n\n<b>Основные команды:</b>\n- Б — просмотр баланса\n- Бет [ставка] — игра на жетоны\n- Дать [сумма] — передача жетонов\n- Бонус — бесплатные жетоны\n- Лидер — топ-15 богачей\n- Курс — информация о локсах\n- Имя [номер] — просмотреть Имя\n- Имена — просмотреть коллекцию Имён\n- +Имя [текст] — преобрести Имя за 5000Ж\n- Установить имя [номер] — установка одного из Имён\n- -Имя — убрать установленное Имя\n- Имя дать [номер] — передача имени\n- Вернуть — использовать ключ\n- Ключи дать — передача ключей\n\nВ некоторых командах можно в конце указывать айди профиля, либо отвечать на сообщение нужного пользователя. Все элементы бота математически упрощены для простоты и комфорта. По любым вопросам — @yamexa", parse_mode="HTML")



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
                base_profit = int(round(bet * mult - bet))
                names_count = int(u_fresh["all_names"]) if u_fresh["all_names"] else 0
                bonus_pct = min(names_count, 25)
                bonus_val = int(round(base_profit * (bonus_pct / 100.0)))
                profit = base_profit + bonus_val
                
                conn.execute("UPDATE Users SET coins = coins + ?, wins = wins + 1 WHERE real_id = ?", (profit, uid))
                txt = f"🌹Поздравляем, {mention}! Вы угадали исход и забрали {profit}Ж"
                if bonus_pct > 0:
                    txt += f" (включая бонус коллекции +{bonus_pct}%: +{bonus_val}Ж)"
                txt += f"\n\nВыбранный исход: {mode_lbl}"
            else:
                conn.execute("UPDATE Users SET coins = coins - ?, losses = losses + 1, last_bet = ? WHERE real_id = ?", (bet, bet, uid))
                txt = f"🥀{mention}, вы проиграли {bet}Ж\n\nВыбранный исход: {mode_lbl}"
            conn.commit()
        bot.send_message(chat_id=call.message.chat.id, text=txt, parse_mode="HTML")
    finally: LOCKS[uid].release()



init_db()
print("есть")
bot.infinity_polling()