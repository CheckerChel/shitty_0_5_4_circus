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
CHATS = [-1003724538567, 7163427034]
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
			time INTEGER DEFAULT 0,
			elite INTEGER DEFAULT 0,
			master INTEGER DEFAULT 0,
			hyper INTEGER DEFAULT 0,
			lvl INTEGER DEFAULT 1
		)
		""")
        for column, definition in [("hyper", "INTEGER DEFAULT 0"), ("lvl", "INTEGER DEFAULT 1")]:
            try:
                cursor.execute(f"ALTER TABLE Users ADD COLUMN {column} {definition}")
            except sqlite3.OperationalError:
                pass
        conn.commit()



def get_user_by_expr(field, val):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT bot_id, real_id, coins, elite, master, hyper, lvl FROM Users WHERE {field} = ?", (val,))
        return cursor.fetchone()

def delete_msg_after_timeout(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass



def check(id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM Users WHERE real_id = ?", (id,))
        user = cursor.fetchone()
        if user is None:
            cursor.execute("INSERT INTO Users (real_id) VALUES (?)", (id,))
            conn.commit()






@bot.message_handler(imc=True, func=lambda m: m.text and (m.text.lower() in ['баланс', 'б'] or m.text.lower().startswith('б ')))
def get_balance(message):
    target_id = None
    is_bot_id = False

    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    else:
        args = message.text.split(maxsplit=1)
        if len(args) > 1:
            if args[1].isdigit():
                target_id = int(args[1])
                is_bot_id = True
        else:
            target_id = message.from_user.id

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if is_bot_id:
            cursor.execute("SELECT bot_id, real_id, coins, elite, master, hyper, lvl FROM Users WHERE bot_id = ?", (target_id,))
        else:
            if target_id == message.from_user.id:
                check(target_id)
            cursor.execute("SELECT bot_id, real_id, coins, elite, master, hyper, lvl FROM Users WHERE real_id = ?", (target_id,))
        
        user = cursor.fetchone()

    if not user:
        bot.reply_to(message, "Пользователь не найден")
        return

    bot_id, real_id, coins, elite, master, hyper, lvl = user
    mention = f'<a href="tg://user?id={real_id}">#{bot_id}</a>'
    
    text = (
        f"👤{mention}\n"
        f"Уровень: {lvl}\n"
        f"Жетонов: {coins}Ж\n"
        f"Элитных кубов: {elite} шт.\n"
        f"Мастер-кубов: {master} шт.\n"
        f"Гиперкубов: {hyper} шт."
    )
    bot.reply_to(message, text, parse_mode="HTML")



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().startswith('дать'))
def request_transfer(message):
    check(message.from_user.id)
    args = message.text.split()
    
    if len(args) < 3 or args[1].lower() not in ['ж', 'эк', 'мк', 'гк']:
        bot.reply_to(message, "Используйте верный вид команды:\nдать [ж/эк/мк/гк] [сумма] [айди]")
        return
        
    res_type = args[1].lower()

    try:
        amount = int(args[2])
        if amount <= 0: return
    except (ValueError, IndexError):
        bot.reply_to(message, "Используйте верный вид команды:\nдать [ж/эк/мк/гк] [сумма] [айди]")
        return

    sender = get_user_by_expr("real_id", message.from_user.id)
    if not sender: return

    res_indexes = {'ж': 2, 'эк': 3, 'мк': 4, 'гк': 5}
    idx = res_indexes[res_type]
    if sender[idx] < amount:
        bot.reply_to(message, "Недостаточно средств")
        return

    target_user = None
    if len(args) > 3:
        t_id = args[3].replace('#', '')
        if t_id.isdigit():
            target_user = get_user_by_expr("bot_id", int(t_id))
    elif message.reply_to_message:
        check(message.reply_to_message.from_user.id)
        target_user = get_user_by_expr("real_id", message.reply_to_message.from_user.id)

    if not target_user or sender[0] == target_user[0]:
        bot.reply_to(message, "Пользователь не найден")
        return

    res_names = {'ж': 'Ж', 'эк': 'элитных кубов', 'мк': 'мастер-кубов', 'гк': 'гиперкубов'}
    
    markup = InlineKeyboardMarkup()
    btn = InlineKeyboardButton(text="✅Подтвердить", callback_data=f"pay_{res_type}_{sender[0]}_{target_user[0]}_{amount}")
    markup.add(btn)
    
    text = f'Вы уверены что хотите перевести {amount} {res_names[res_type]} на <a href="tg://user?id={target_user[1]}">#{target_user[0]}</a>?'
    sent_msg = bot.reply_to(message, text, parse_mode="HTML", reply_markup=markup)
    
    threading.Timer(60.0, delete_msg_after_timeout, args=[sent_msg.chat.id, sent_msg.message_id]).start()


@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def confirm_transfer(call):
    _, res_type, s_bot_id, t_bot_id, amount_str = call.data.split("_")
    s_bot_id, t_bot_id, amount = int(s_bot_id), int(t_bot_id), int(amount_str)
    
    sender = get_user_by_expr("bot_id", s_bot_id)
    if not sender or call.from_user.id != sender[1]:
        bot.answer_callback_query(call.id)
        return
        
    bot.answer_callback_query(call.id)
    fields = {'ж': 'coins', 'эк': 'elite', 'мк': 'master', 'гк': 'hyper'}
    field = fields[res_type]

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT {field} FROM Users WHERE bot_id = ?", (s_bot_id,))
        res = cursor.fetchone()
        
        if not res or res[0] < amount:
            try:
                bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
            except Exception:
                pass
            return
            
        cursor.execute(f"UPDATE Users SET {field} = {field} - ? WHERE bot_id = ?", (amount, s_bot_id))
        cursor.execute(f"UPDATE Users SET {field} = {field} + ? WHERE bot_id = ?", (amount, t_bot_id))
        conn.commit()

    target = get_user_by_expr("bot_id", t_bot_id)
    
    res_labels = {'ж': f"{amount}Ж", 'эк': f"{amount} элитных кубов", 'мк': f"{amount} мастер-кубов", 'гк': f"{amount} гиперкубов"}
    lbl = res_labels[res_type]

    new_text = f'💸<a href="tg://user?id={sender[1]}">#{s_bot_id}</a> перевёл {lbl} на <a href="tg://user?id={target[1]}">#{t_bot_id}</a>'
    
    try:
        bot.edit_message_text(new_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=None)
    except Exception:
        pass



@bot.message_handler(regexp=r"^вж \d+$", imc=True)
def give_coins_admin(message):
    user_id = message.from_user.id
    if user_id not in CHATS:
        return
    amount = int(message.text.split()[1])
    check(user_id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Users SET coins = coins + ? WHERE real_id = ?", 
            (amount, user_id)
        )
        conn.commit()
    bot.reply_to(message, f"Вы выдали себе {amount}Ж")



@bot.message_handler(regexp=r"^вэк \d+$", imc=True)
def give_elite_admin(message):
    user_id = message.from_user.id
    if user_id not in CHATS:
        return
    amount = int(message.text.split()[1])
    check(user_id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET elite = elite + ? WHERE real_id = ?", (amount, user_id))
        conn.commit()
    bot.reply_to(message, f"Вы выдали себе {amount} элитных кубов")



@bot.message_handler(regexp=r"^вмк \d+$", imc=True)
def give_master_admin(message):
    user_id = message.from_user.id
    if user_id not in CHATS:
        return
    amount = int(message.text.split()[1])
    check(user_id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET master = master + ? WHERE real_id = ?", (amount, user_id))
        conn.commit()
    bot.reply_to(message, f"Вы выдали себе {amount} мастер-кубов")



@bot.message_handler(regexp=r"^вгк \d+$", imc=True)
def give_hyper_admin(message):
    user_id = message.from_user.id
    if user_id not in CHATS:
        return
    amount = int(message.text.split()[1])
    check(user_id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET hyper = hyper + ? WHERE real_id = ?", (amount, user_id))
        conn.commit()
    bot.reply_to(message, f"Вы выдали себе {amount} гиперкубов")



@bot.message_handler(regexp=r"^влвл \d+$", imc=True)
def give_level_admin(message):
    user_id = message.from_user.id
    if user_id not in CHATS:
        return
    amount = int(message.text.split()[1])
    check(user_id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET lvl = lvl + ? WHERE real_id = ?", (amount, user_id))
        conn.commit()
    bot.reply_to(message, f"Вы добавили себе {amount} ур.")



@bot.message_handler(func=lambda m: m.text and m.text.lower() == "бонус", imc=True)
def get_bonus(message):
    user_id = message.from_user.id
    
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
        
    if not LOCKS[user_id].acquire(blocking=False):
        return
        
    try:
        check(user_id)
        current_time = int(time.time())

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT coins, time, lvl FROM Users WHERE real_id = ?", (user_id,))
            res = cursor.fetchone()
            coins, last_time, lvl = res

            cooldown = 3600 - (lvl - 1) * 300
            if cooldown < 300:
                cooldown = 300

            if current_time - last_time < cooldown:
                remains = cooldown - (current_time - last_time)
                mins = remains // 60
                secs = remains % 60
                bot.reply_to(message, f"⏳Не так часто! Подожди ещё:\n{mins} мин. {secs} сек.")
                return

            bonus = random.randint(100, 500)
            rand = random.random()

            if lvl >= 7 and rand < 0.0001:
                cubes = random.randint(1, 2)
                cursor.execute(
                    "UPDATE Users SET coins = coins + ?, hyper = hyper + ?, time = ? WHERE real_id = ?",
                    (bonus, cubes, current_time, user_id)
                )
                text = f"💥Легендарная удача! Вы забрали {bonus}Ж и {cubes} гиперкуба! Возвращайтесь через час"
            elif rand < 0.05:
                cubes = random.randint(1, 2)
                cursor.execute(
                    "UPDATE Users SET coins = coins + ?, master = master + ?, time = ? WHERE real_id = ?",
                    (bonus, cubes, current_time, user_id)
                )
                text = f"📦Вы забрали {bonus}Ж и {cubes} мастер-куба! Возвращайтесь через час"
            elif rand < 0.33:
                cubes = random.randint(1, 4)
                cursor.execute(
                    "UPDATE Users SET coins = coins + ?, elite = elite + ?, time = ? WHERE real_id = ?",
                    (bonus, cubes, current_time, user_id)
                )
                text = f"📦Вы забрали {bonus}Ж и {cubes} элитных куба! Возвращайтесь через час"
            else:
                cursor.execute(
                    "UPDATE Users SET coins = coins + ?, time = ? WHERE real_id = ?",
                    (bonus, current_time, user_id)
                )
                text = f"📦Вы забрали {bonus}Ж. Возвращайтесь через час"

            conn.commit()

        bot.reply_to(message, text)
    finally:
        LOCKS[user_id].release()



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower() == '-кд')
def reset_cooldown(message):
    if message.from_user.id not in CHATS:
        return
    check(message.from_user.id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET time = 0 WHERE real_id = ?", (message.from_user.id,))
        conn.commit()
    bot.reply_to(message, "Ваш личный КД на бонус был успешно обнулен!")



LEVEL_PRICES = {
    2: ('coins', 500000, "Ж"),
    3: ('coins', 1000000, "Ж"),
    4: ('coins', 5000000, "Ж"),
    5: ('coins', 10000000, "Ж"),
    6: ('coins', 100000000, "Ж"),
    7: ('master', 25, "мастер-кубов"),
    8: ('master', 50, "мастер-кубов"),
    9: ('master', 75, "мастер-кубов"),
    10: ('master', 100, "мастер-кубов")
}

@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower() == 'уровни')
def show_levels_info(message):
    text = (
        "Цена уровней:\n"
        "Ур. 1 - начальный\n"
        "Ур. 2 - 500000Ж\n"
        "Ур. 3 - 1000000Ж\n"
        "Ур. 4 - 5000000Ж\n"
        "Ур. 5 - 10000000Ж\n"
        "Ур. 6 - 100000000Ж\n"
        "Ур. 7 - 25МК\n"
        "Ур. 8 - 50МК\n"
        "Ур. 9 - 75МК\n"
        "Ур. 10 - 100МК.\n\n"
        "Каждый уровень уменьшает кд на 5 минут. Начиная с 7 уровня имеется шанс выбить Гиперкубы. Чтобы прокачаться, напишите Уровень"
    )
    bot.reply_to(message, text)


@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower() == 'уровень')
def request_level_up(message):
    user_id = message.from_user.id
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
    if not LOCKS[user_id].acquire(blocking=False):
        return
    try:
        check(user_id)
        sender = get_user_by_expr("real_id", user_id)
        if not sender: return
        
        bot_id = sender[0]
        lvl = sender[6]

        if lvl >= 10:
            bot.reply_to(message, "⚡Вы не можете покачаться ещё, ваш уровень максимальный")
            return

        next_lvl = lvl + 1
        _, price, res_name = LEVEL_PRICES[next_lvl]

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⚡Прокачаться", callback_data=f"lvlup_{bot_id}"))

        text = f"Ваш текущий уровень: {lvl}.\nСледующий стоит {price} {res_name}"
        bot.reply_to(message, text, reply_markup=markup)
    finally:
        LOCKS[user_id].release()


@bot.callback_query_handler(func=lambda call: call.data.startswith("lvlup_"))
def confirm_level_up(call):
    s_bot_id = int(call.data.split("_")[1])
    sender = get_user_by_expr("bot_id", s_bot_id)
    
    if not sender or call.from_user.id != sender[1]:
        bot.answer_callback_query(call.id)
        return

    user_id = sender[1]
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
    if not LOCKS[user_id].acquire(blocking=False):
        bot.answer_callback_query(call.id)
        return

    bot.answer_callback_query(call.id)
    try:
        lvl = sender[6]
        if lvl >= 10:
            try: bot.edit_message_text("⚡Вы не можете прокачаться ещё, ваш уровень максимальный", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
            except Exception: pass
            return

        next_lvl = lvl + 1
        field, price, _ = LEVEL_PRICES[next_lvl]

        db_field_map = {'coins': 2, 'master': 4}
        if sender[db_field_map[field]] < price:
            try: bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
            except Exception: pass
            return

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE Users SET {field} = {field} - ?, lvl = ? WHERE bot_id = ?", (price, next_lvl, s_bot_id))
            conn.commit()

        try: bot.edit_message_text(f"⚡Поздравляем! Вы прокачались до уровня {next_lvl}", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        except Exception: pass
    finally:
        LOCKS[user_id].release()



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().split() in [['лидер'], ['лидеры']])
def show_leaderboard(message):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT bot_id, real_id, coins FROM Users WHERE coins > 0 ORDER BY coins DESC LIMIT 15")
        leaders = cursor.fetchall()
    text = "<b>👑Топ-15 богачей</b>\n\n"
    if not leaders:
        text += "Таблица пуста"
    else:
        for idx, (bot_id, real_id, coins) in enumerate(leaders, 1):
            text += f"{idx}. <a href=\"tg://user?id={real_id}\">#{bot_id}</a> — {coins}Ж\n"
    bot.reply_to(message, text, parse_mode="HTML")



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().startswith('обмен'))
def exchange_request(message):
    user_id = message.from_user.id
    
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
        
    if not LOCKS[user_id].acquire(blocking=False):
        return
        
    try:
        check(user_id)
        args = message.text.split()
        
        err_msg = "Правильный вид команды:\nОбмен [сумма_1] [ж/эк/мк/гк] [сумма_2] [ж/эк/мк/гк]\n\nПример: обмен 1 гк 10 мк"
        if len(args) != 5:
            bot.reply_to(message, err_msg)
            return

        try:
            amt1, amt2 = int(args[1]), int(args[3])
            if amt1 <= 0 or amt2 <= 0:
                bot.reply_to(message, err_msg)
                return
        except ValueError:
            bot.reply_to(message, err_msg)
            return

        v1, v2 = args[2].lower(), args[4].lower()
        valid = ['ж', 'эк', 'мк', 'гк']
        
        if v1 not in valid or v2 not in valid:
            bot.reply_to(message, err_msg)
            return

        if v1 == v2:
            bot.reply_to(message, "Нельзя обмениваться одним и тем же")
            return

        sender = get_user_by_expr("real_id", user_id)
        if not sender: return
        
        fields = {'ж': 2, 'эк': 3, 'мк': 4, 'гк': 5}
        if sender[fields[v1]] < amt1:
            bot.reply_to(message, "Недостаточно средств")
            return

        bot_id = sender[0]
        mention = f'<a href="tg://user?id={user_id}">#{bot_id}</a>'
        res_names = {'ж': 'Ж', 'эк': 'элитных кубов', 'мк': 'мастер-кубов', 'гк': 'гиперкубов'}

        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton(text="✅Обмен", callback_data=f"trade_{bot_id}_{amt1}_{v1}_{amt2}_{v2}")
        markup.add(btn)

        text = f"✨Внимание! {mention} предлагает обмен своих {amt1} {res_names[v1]} на чужие {amt2} {res_names[v2]}"
        bot.reply_to(message, text, parse_mode="HTML", reply_markup=markup)
    finally:
        LOCKS[user_id].release()


@bot.callback_query_handler(func=lambda call: call.data.startswith("trade_"))
def exchange_confirm(call):
    _, s_bot_id_str, amt1_str, v1, amt2_str, v2 = call.data.split("_")
    s_bot_id = int(s_bot_id_str)
    amt1, amt2 = int(amt1_str), int(amt2_str)
    
    sender = get_user_by_expr("bot_id", s_bot_id)
    if not sender:
        bot.answer_callback_query(call.id)
        return

    if call.from_user.id == sender[1]:
        bot.answer_callback_query(call.id)
        return

    t_real_id = call.from_user.id
    check(t_real_id)
    
    target = get_user_by_expr("real_id", t_real_id)
    if not target: return
    t_bot_id = target[0]

    if s_bot_id not in LOCKS: LOCKS[s_bot_id] = threading.Lock()
    if t_bot_id not in LOCKS: LOCKS[t_bot_id] = threading.Lock()

    if not LOCKS[s_bot_id].acquire(blocking=False):
        bot.answer_callback_query(call.id)
        return
    if not LOCKS[t_bot_id].acquire(blocking=False):
        LOCKS[s_bot_id].release()
        bot.answer_callback_query(call.id)
        return

    db_fields = {'ж': 'coins', 'эк': 'elite', 'мк': 'master', 'гк': 'hyper'}
    f1, f2 = db_fields[v1], db_fields[v2]
    res_names = {'ж': 'Ж', 'эк': 'элитных кубов', 'мк': 'мастер-кубов', 'гк': 'гиперкубов'}

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT {f2} FROM Users WHERE bot_id = ?", (t_bot_id,))
            t_res = cursor.fetchone()
            if not t_res or t_res[0] < amt2:
                bot.answer_callback_query(call.id, "Недостаточно средств", show_alert=True)
                return

            bot.answer_callback_query(call.id)

            cursor.execute(f"SELECT {f1} FROM Users WHERE bot_id = ?", (s_bot_id,))
            s_res = cursor.fetchone()
            if not s_res or s_res[0] < amt1:
                s_mention = f'<a href="tg://user?id={sender[1]}">#{s_bot_id}</a>'
                try:
                    bot.edit_message_text(f"⛔Упс! Обмен отменяется в связи с тем, что {s_mention} на данный момент уже не имеет нужных средств", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=None)
                except Exception:
                    pass
                return

            cursor.execute(f"UPDATE Users SET {f1} = {f1} - ?, {f2} = {f2} + ? WHERE bot_id = ?", (amt1, amt2, s_bot_id))
            cursor.execute(f"UPDATE Users SET {f2} = {f2} - ?, {f1} = {f1} + ? WHERE bot_id = ?", (amt2, amt1, t_bot_id))
            conn.commit()

        s_mention = f'<a href="tg://user?id={sender[1]}">#{s_bot_id}</a>'
        t_mention = f'<a href="tg://user?id={t_real_id}">#{t_bot_id}</a>'
        new_text = f"🎉Успешный обмен!\n{s_mention} получил {amt2} {res_names[v2]}, а {t_mention} получил {amt1} {res_names[v1]}."
        
        try:
            bot.edit_message_text(new_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=None)
        except Exception:
            pass
    finally:
        LOCKS[t_bot_id].release()
        LOCKS[s_bot_id].release()



@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() in ["инфо", "/info"], imc=True)
def show_info(message):
    try:
        check(message.from_user.id)
        bot.reply_to(message, "ℹ️<b>Информация о боте</b>\n\nЖетоны (Ж) — собственная валюта бота.\nЭлитные кубы (ЭК) — обычные кубы для игр, но с удвоенным выигрышем.\nМастер-кубы (МК) — обычные кубы для игр, но с выигрыш помножен на 10.\nПолучить данные элементы можно случайным образом в бонусе.\n\n<b>Команды:</b>\n- Кубы — выбор игр.\n- Дать — передача жетонов или кубов.\n- Бонус — забрать бонус.\n- Лидер — посмотреть топ-15 богачей.\n- Обмен — безопасный обмен.\n- Уровни — посмотреть цены уровней.\n- Уровень — прокачаться.\n\n<b>По любым вопросам —</b> @yamexa", parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка команды инфо: {e}")


# ИГРОВЫЕ КОМАНДЫ
# ИГРОВЫЕ КОМАНДЫ
# ИГРОВЫЕ КОМАНДЫ
# ИГРОВЫЕ КОМАНДЫ
# ИГРОВЫЕ КОМАНДЫ



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().startswith('кубы'))
def cubes_game_start(message):
    user_id = message.from_user.id
    
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
        
    if not LOCKS[user_id].acquire(blocking=False):
        return
        
    try:
        check(user_id)
        args = message.text.split()
        
        if len(args) == 1:
            bot.reply_to(message, "Выберите игру:\n• Кубы [ставка]\n• Эк [ставка]\n• Мк [ставка]\n• Гк [ставка] [эк/мк]")
            return

        try:
            bet = int(args[1])
            if bet <= 0: return
        except (ValueError, IndexError):
            return

        sender = get_user_by_expr("real_id", user_id)
        if not sender or sender[2] < bet:
            bot.reply_to(message, "Недостаточно средств")
            return

        bot_id = sender[0]
        mention = f'<a href="tg://user?id={user_id}">#{bot_id}</a>'
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("Чётное х2", callback_data=f"c_even_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("Нечётное х2", callback_data=f"c_odd_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("Больше х2", callback_data=f"c_big_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("Меньше х2", callback_data=f"c_small_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("1 х6", callback_data=f"c_n1_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("2 х6", callback_data=f"c_n2_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("3 х6", callback_data=f"c_n3_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("4 х6", callback_data=f"c_n4_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("5 х6", callback_data=f"c_n5_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("6 х6", callback_data=f"c_n6_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("Лесенка вверх х36", callback_data=f"c_up_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("Лесенка вниз х36", callback_data=f"c_down_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("Дубль х6", callback_data=f"c_dbl_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("Трипл х36", callback_data=f"c_tpl_{bot_id}_{bet}_{message.message_id}"))

        text = f"👤{mention}\nСтавка: {bet}"
        bot.reply_to(message, text, parse_mode="HTML", reply_markup=markup)
    finally:
        LOCKS[user_id].release()



@bot.callback_query_handler(func=lambda call: call.data.startswith("c_"))
def cubes_game_callback(call):
    _, mode, s_bot_id, bet_str, orig_msg_id = call.data.split("_")
    s_bot_id, bet, orig_msg_id = int(s_bot_id), int(bet_str), int(orig_msg_id)
    
    sender = get_user_by_expr("bot_id", s_bot_id)
    if not sender or call.from_user.id != sender[1]:
        bot.answer_callback_query(call.id)
        return

    user_id = sender[1]
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
        
    if not LOCKS[user_id].acquire(blocking=False):
        bot.answer_callback_query(call.id)
        return

    bot.answer_callback_query(call.id)
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT coins FROM Users WHERE bot_id = ?", (s_bot_id,))
            res = cursor.fetchone()
            
            if not res or res[0] < bet:
                try:
                    bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
                except Exception:
                    pass
                return

        try:
            bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception:
            pass

        dice_count = 1
        if mode == "dbl":
            dice_count = 2
        elif mode in ["up", "down", "tpl"]:
            dice_count = 3

        dices = []
        for _ in range(dice_count):
            try:
                msg = bot.send_dice(chat_id=call.message.chat.id, reply_to_message_id=orig_msg_id)
                dices.append(msg.dice.value)
            except Exception:
                msg = bot.send_dice(chat_id=call.message.chat.id)
                dices.append(msg.dice.value)
            time.sleep(0.1)

        win = False
        mult = 0

        if mode == "even" and dices[0] % 2 == 0: win, mult = True, 2
        elif mode == "odd" and dices[0] % 2 != 0: win, mult = True, 2
        elif mode == "big" and dices[0] > 3: win, mult = True, 2
        elif mode == "small" and dices[0] <= 3: win, mult = True, 2
        elif mode.startswith("n"):
            target_num = int(mode[1])
            if dices[0] == target_num: win, mult = True, 6
        elif mode == "dbl" and dices[0] == dices[1]: win, mult = True, 6
        elif mode == "tpl" and (dices[0] == dices[1] == dices[2]): win, mult = True, 36
        elif mode == "up":
            if dices in [[1,2,3], [2,3,4], [3,4,5], [4,5,6], [1,3,5], [2,4,6]]: win, mult = True, 36
        elif mode == "down":
            if dices in [[6,5,4], [5,4,3], [4,3,2], [3,2,1], [6,4,2], [5,3,1]]: win, mult = True, 36

        mention = f'<a href="tg://user?id={user_id}">#{s_bot_id}</a>'
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            if win:
                profit = bet * mult - bet
                cursor.execute("UPDATE Users SET coins = coins + ? WHERE bot_id = ?", (profit, s_bot_id))
                new_text = f"Поздравляем, {mention}! Вы угадали исход и забрали {profit}Ж"
            else:
                cursor.execute("UPDATE Users SET coins = coins - ? WHERE bot_id = ?", (bet, s_bot_id))
                new_text = f"{mention}, вы проиграли {bet}Ж"
            conn.commit()

        bot.send_message(chat_id=call.message.chat.id, text=new_text, parse_mode="HTML")
    finally:
        LOCKS[user_id].release()



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().startswith('эк'))
def elite_game_start(message):
    user_id = message.from_user.id
    
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
        
    if not LOCKS[user_id].acquire(blocking=False):
        return
        
    try:
        check(user_id)
        args = message.text.split()
        
        if len(args) == 1:
            bot.reply_to(message, "Выберите игру:\n• Кубы [ставка]\n• Эк [ставка]\n• Мк [ставка]\n• Гк [ставка] [эк/мк]")
            return

        try:
            bet = int(args[1])
            if bet <= 0: return
        except (ValueError, IndexError):
            return

        sender = get_user_by_expr("real_id", user_id)
        if not sender or sender[2] < bet:
            bot.reply_to(message, "Недостаточно средств")
            return
            
        if sender[3] < 1:
            bot.reply_to(message, "Недостаточно элитных кубов")
            return

        bot_id = sender[0]
        mention = f'<a href="tg://user?id={user_id}">#{bot_id}</a>'
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("Чётное х4", callback_data=f"e_even_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("Нечётное х4", callback_data=f"e_odd_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("Больше х4", callback_data=f"e_big_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("Меньше х4", callback_data=f"e_small_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("1 х12", callback_data=f"e_n1_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("2 х12", callback_data=f"e_n2_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("3 х12", callback_data=f"e_n3_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("4 х12", callback_data=f"e_n4_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("5 х12", callback_data=f"e_n5_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("6 х12", callback_data=f"e_n6_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("Лесенка вверх х72", callback_data=f"e_up_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("Лесенка вниз х72", callback_data=f"e_down_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("Дубль х12", callback_data=f"e_dbl_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("Трипл х72", callback_data=f"e_tpl_{bot_id}_{bet}_{message.message_id}"))

        text = f"👤{mention}\nСтавка: {bet}"
        bot.reply_to(message, text, parse_mode="HTML", reply_markup=markup)
    finally:
        LOCKS[user_id].release()



@bot.callback_query_handler(func=lambda call: call.data.startswith("e_"))
def elite_game_callback(call):
    _, mode, s_bot_id, bet_str, orig_msg_id = call.data.split("_")
    s_bot_id, bet, orig_msg_id = int(s_bot_id), int(bet_str), int(orig_msg_id)
    
    sender = get_user_by_expr("bot_id", s_bot_id)
    if not sender or call.from_user.id != sender[1]:
        bot.answer_callback_query(call.id)
        return

    user_id = sender[1]
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
        
    if not LOCKS[user_id].acquire(blocking=False):
        bot.answer_callback_query(call.id)
        return

    bot.answer_callback_query(call.id)
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT coins, elite FROM Users WHERE bot_id = ?", (s_bot_id,))
            res = cursor.fetchone()
            
            if not res or res[0] < bet:
                try:
                    bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
                except Exception:
                    pass
                return

            if res[1] < 1:
                try:
                    bot.edit_message_text("Недостаточно элитных кубов", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
                except Exception:
                    pass
                return

        try:
            bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception:
            pass

        dice_count = 1
        if mode == "dbl":
            dice_count = 2
        elif mode in ["up", "down", "tpl"]:
            dice_count = 3

        dices = []
        for _ in range(dice_count):
            try:
                msg = bot.send_dice(chat_id=call.message.chat.id, reply_to_message_id=orig_msg_id)
                dices.append(msg.dice.value)
            except Exception:
                msg = bot.send_dice(chat_id=call.message.chat.id)
                dices.append(msg.dice.value)
            time.sleep(0.1)

        win = False
        mult = 0

        if mode == "even" and dices[0] % 2 == 0: win, mult = True, 4
        elif mode == "odd" and dices[0] % 2 != 0: win, mult = True, 4
        elif mode == "big" and dices[0] > 3: win, mult = True, 4
        elif mode == "small" and dices[0] <= 3: win, mult = True, 4
        elif mode.startswith("n"):
            target_num = int(mode[1])
            if dices[0] == target_num: win, mult = True, 12
        elif mode == "dbl" and dices[0] == dices[1]: win, mult = True, 12
        elif mode == "tpl" and (dices[0] == dices[1] == dices[2]): win, mult = True, 72
        elif mode == "up":
            if dices in [[1,2,3], [2,3,4], [3,4,5], [4,5,6], [1,3,5], [2,4,6]]: win, mult = True, 72
        elif mode == "down":
            if dices in [[6,5,4], [5,4,3], [4,3,2], [3,2,1], [6,4,2], [5,3,1]]: win, mult = True, 72

        mention = f'<a href="tg://user?id={user_id}">#{s_bot_id}</a>'
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET elite = elite - 1 WHERE bot_id = ?", (s_bot_id,))
            if win:
                profit = bet * mult - bet
                cursor.execute("UPDATE Users SET coins = coins + ? WHERE bot_id = ?", (profit, s_bot_id))
                new_text = f"Поздравляем, {mention}! Вы угадали исход и забрали {profit}Ж"
            else:
                cursor.execute("UPDATE Users SET coins = coins - ? WHERE bot_id = ?", (bet, s_bot_id))
                new_text = f"{mention}, вы проиграли {bet}Ж"
            conn.commit()

        bot.send_message(chat_id=call.message.chat.id, text=new_text, parse_mode="HTML")
    finally:
        LOCKS[user_id].release()



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().startswith('мк'))
def master_game_start(message):
    user_id = message.from_user.id
    
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
        
    if not LOCKS[user_id].acquire(blocking=False):
        return
        
    try:
        check(user_id)
        args = message.text.split()
        
        if len(args) == 1:
            bot.reply_to(message, "Выберите игру:\n• Кубы [ставка]\n• Эк [ставка]\n• Мк [ставка]\n• Гк [ставка] [эк/мк]")
            return

        try:
            bet = int(args[1])
            if bet <= 0: return
        except (ValueError, IndexError):
            return

        sender = get_user_by_expr("real_id", user_id)
        if not sender or sender[2] < bet:
            bot.reply_to(message, "Недостаточно средств")
            return
            
        if sender[4] < 1:
            bot.reply_to(message, "Недостаточно мастер-кубов")
            return

        bot_id = sender[0]
        mention = f'<a href="tg://user?id={user_id}">#{bot_id}</a>'
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("Чётное х20", callback_data=f"m_even_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("Нечётное х20", callback_data=f"m_odd_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("Больше х20", callback_data=f"m_big_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("Меньше х20", callback_data=f"m_small_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("1 х60", callback_data=f"m_n1_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("2 х60", callback_data=f"m_n2_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("3 х60", callback_data=f"m_n3_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("4 х60", callback_data=f"m_n4_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("5 х60", callback_data=f"m_n5_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("6 х60", callback_data=f"m_n6_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("Лесенка вверх х360", callback_data=f"m_up_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("Лесенка вниз х360", callback_data=f"m_down_{bot_id}_{bet}_{message.message_id}"))
        markup.row(InlineKeyboardButton("Дубль х60", callback_data=f"m_dbl_{bot_id}_{bet}_{message.message_id}"), InlineKeyboardButton("Трипл х360", callback_data=f"m_tpl_{bot_id}_{bet}_{message.message_id}"))

        text = f"👤{mention}\nСтавка: {bet}"
        bot.reply_to(message, text, parse_mode="HTML", reply_markup=markup)
    finally:
        LOCKS[user_id].release()



@bot.callback_query_handler(func=lambda call: call.data.startswith("m_"))
def master_game_callback(call):
    _, mode, s_bot_id, bet_str, orig_msg_id = call.data.split("_")
    s_bot_id, bet, orig_msg_id = int(s_bot_id), int(bet_str), int(orig_msg_id)
    
    sender = get_user_by_expr("bot_id", s_bot_id)
    if not sender or call.from_user.id != sender[1]:
        bot.answer_callback_query(call.id)
        return

    user_id = sender[1]
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
        
    if not LOCKS[user_id].acquire(blocking=False):
        bot.answer_callback_query(call.id)
        return

    bot.answer_callback_query(call.id)
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT coins, master FROM Users WHERE bot_id = ?", (s_bot_id,))
            res = cursor.fetchone()
            
            if not res or res[0] < bet:
                try:
                    bot.edit_message_text("Недостаточно средств", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
                except Exception:
                    pass
                return

            if res[1] < 1:
                try:
                    bot.edit_message_text("Недостаточно мастер-кубов", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
                except Exception:
                    pass
                return

        try:
            bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception:
            pass

        dice_count = 1
        if mode == "dbl":
            dice_count = 2
        elif mode in ["up", "down", "tpl"]:
            dice_count = 3

        dices = []
        for _ in range(dice_count):
            try:
                msg = bot.send_dice(chat_id=call.message.chat.id, reply_to_message_id=orig_msg_id)
                dices.append(msg.dice.value)
            except Exception:
                msg = bot.send_dice(chat_id=call.message.chat.id)
                dices.append(msg.dice.value)
            time.sleep(0.1)

        win = False
        mult = 0

        if mode == "even" and dices[0] % 2 == 0: win, mult = True, 20
        elif mode == "odd" and dices[0] % 2 != 0: win, mult = True, 20
        elif mode == "big" and dices[0] > 3: win, mult = True, 20
        elif mode == "small" and dices[0] <= 3: win, mult = True, 20
        elif mode.startswith("n"):
            target_num = int(mode[1])
            if dices[0] == target_num: win, mult = True, 60
        elif mode == "dbl" and dices[0] == dices[1]: win, mult = True, 60
        elif mode == "tpl" and (dices[0] == dices[1] == dices[2]): win, mult = True, 360
        elif mode == "up":
            if dices in [[1,2,3], [2,3,4], [3,4,5], [4,5,6], [1,3,5], [2,4,6]]: win, mult = True, 360
        elif mode == "down":
            if dices in [[6,5,4], [5,4,3], [4,3,2], [3,2,1], [6,4,2], [5,3,1]]: win, mult = True, 360

        mention = f'<a href="tg://user?id={user_id}">#{s_bot_id}</a>'
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET master = master - 1 WHERE bot_id = ?", (s_bot_id,))
            if win:
                profit = bet * mult - bet
                cursor.execute("UPDATE Users SET coins = coins + ? WHERE bot_id = ?", (profit, s_bot_id))
                new_text = f"Поздравляем, {mention}! Вы угадали исход и забрали {profit}Ж"
            else:
                cursor.execute("UPDATE Users SET coins = coins - ? WHERE bot_id = ?", (bet, s_bot_id))
                new_text = f"{mention}, вы проиграли {bet}Ж"
            conn.commit()

        bot.send_message(chat_id=call.message.chat.id, text=new_text, parse_mode="HTML")
    finally:
        LOCKS[user_id].release()



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().startswith('гк'))
def hyper_game_start(message):
    user_id = message.from_user.id
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
    if not LOCKS[user_id].acquire(blocking=False):
        return
    try:
        check(user_id)
        args = message.text.split()
        if len(args) < 3 or args[2].lower() not in ['эк', 'мк']:
            bot.reply_to(message, "Выберите игру:\n• Кубы [ставка]\n• Эк [ставка]\n• Мк [ставка]\n• Гк [ставка] [эк/мк]")
            return
        try:
            bet = int(args[1])
            if bet <= 0: return
        except ValueError:
            return
        res_type = args[2].lower()
        sender = get_user_by_expr("real_id", user_id)
        if not sender or sender[5] < 1:
            bot.reply_to(message, "Недостаточно гиперкубов")
            return
        idx = 3 if res_type == 'эк' else 4
        if sender[idx] < bet:
            bot.reply_to(message, f"Недостаточно {res_type.upper()}")
            return
        bot_id = sender[0]
        mention = f'<a href="tg://user?id={user_id}">#{bot_id}</a>'
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("Чётное х2", callback_data=f"h_even_{bot_id}_{bet}_{res_type}_{message.message_id}"), InlineKeyboardButton("Нечётное х2", callback_data=f"h_odd_{bot_id}_{bet}_{res_type}_{message.message_id}"))
        markup.row(InlineKeyboardButton("Больше х2", callback_data=f"h_big_{bot_id}_{bet}_{res_type}_{message.message_id}"), InlineKeyboardButton("Меньше х2", callback_data=f"h_small_{bot_id}_{bet}_{res_type}_{message.message_id}"))
        markup.row(InlineKeyboardButton("1 х6", callback_data=f"h_n1_{bot_id}_{bet}_{res_type}_{message.message_id}"), InlineKeyboardButton("2 х6", callback_data=f"h_n2_{bot_id}_{bet}_{res_type}_{message.message_id}"), InlineKeyboardButton("3 х6", callback_data=f"h_n3_{bot_id}_{bet}_{res_type}_{message.message_id}"))
        markup.row(InlineKeyboardButton("4 х6", callback_data=f"h_n4_{bot_id}_{bet}_{res_type}_{message.message_id}"), InlineKeyboardButton("5 х6", callback_data=f"h_n5_{bot_id}_{bet}_{res_type}_{message.message_id}"), InlineKeyboardButton("6 х6", callback_data=f"h_n6_{bot_id}_{bet}_{res_type}_{message.message_id}"))
        markup.row(InlineKeyboardButton("Лесенка вверх х36", callback_data=f"h_up_{bot_id}_{bet}_{res_type}_{message.message_id}"), InlineKeyboardButton("Лесенка вниз х36", callback_data=f"h_down_{bot_id}_{bet}_{res_type}_{message.message_id}"))
        markup.row(InlineKeyboardButton("Дубль х6", callback_data=f"h_dbl_{bot_id}_{bet}_{res_type}_{message.message_id}"), InlineKeyboardButton("Трипл х36", callback_data=f"h_tpl_{bot_id}_{bet}_{res_type}_{message.message_id}"))
        text = f"👤{mention}\nСтавка: {bet} {res_type.upper()}"
        bot.reply_to(message, text, parse_mode="HTML", reply_markup=markup)
    finally:
        LOCKS[user_id].release()



@bot.callback_query_handler(func=lambda call: call.data.startswith("h_"))
def hyper_game_callback(call):
    _, mode, s_bot_id, bet_str, res_type, orig_msg_id = call.data.split("_")
    s_bot_id, bet, orig_msg_id = int(s_bot_id), int(bet_str), int(orig_msg_id)
    sender = get_user_by_expr("bot_id", s_bot_id)
    if not sender or call.from_user.id != sender[1]:
        bot.answer_callback_query(call.id)
        return
    user_id = sender[1]
    if user_id not in LOCKS:
        LOCKS[user_id] = threading.Lock()
    if not LOCKS[user_id].acquire(blocking=False):
        bot.answer_callback_query(call.id)
        return
    bot.answer_callback_query(call.id)
    try:
        db_fields = {'эк': 'elite', 'мк': 'master'}
        field = db_fields[res_type]
        idx = 3 if res_type == 'эк' else 4
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT hyper, {field} FROM Users WHERE bot_id = ?", (s_bot_id,))
            res = cursor.fetchone()
            if not res or res[0] < 1:
                try: bot.edit_message_text("Недостаточно гиперкубов", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
                except Exception: pass
                return
            if res[1] < bet:
                try: bot.edit_message_text(f"Недостаточно {res_type.upper()}", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
                except Exception: pass
                return
        try: bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception: pass
        dice_count = 1
        if mode == "dbl": dice_count = 2
        elif mode in ["up", "down", "tpl"]: dice_count = 3
        dices = []
        for _ in range(dice_count):
            try:
                msg = bot.send_dice(chat_id=call.message.chat.id, reply_to_message_id=orig_msg_id)
                dices.append(msg.dice.value)
            except Exception:
                msg = bot.send_dice(chat_id=call.message.chat.id)
                dices.append(msg.dice.value)
            time.sleep(0.1)
        win = False
        mult = 0
        if mode == "even" and dices[0] % 2 == 0: win, mult = True, 2
        elif mode == "odd" and dices[0] % 2 != 0: win, mult = True, 2
        elif mode == "big" and dices[0] > 3: win, mult = True, 2
        elif mode == "small" and dices[0] <= 3: win, mult = True, 2
        elif mode.startswith("n"):
            target_num = int(mode[1])
            if dices[0] == target_num: win, mult = True, 6
        elif mode == "dbl" and dices[0] == dices[1]: win, mult = True, 6
        elif mode == "tpl" and (dices[0] == dices[1] == dices[2]): win, mult = True, 36
        elif mode == "up":
            if dices in [[1,2,3], [2,3,4], [3,4,5], [4,5,6], [1,3,5], [2,4,6]]: win, mult = True, 36
        elif mode == "down":
            if dices in [[6,5,4], [5,4,3], [4,3,2], [3,2,1], [6,4,2], [5,3,1]]: win, mult = True, 36
        mention = f'<a href="tg://user?id={user_id}">#{s_bot_id}</a>'
        res_label = 'элитных кубов' if res_type == 'эк' else 'мастер-кубов'
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET hyper = hyper - 1 WHERE bot_id = ?", (s_bot_id,))
            if win:
                profit = bet * mult - bet
                cursor.execute(f"UPDATE Users SET {field} = {field} + ? WHERE bot_id = ?", (profit, s_bot_id))
                new_text = f"Поздравляем, {mention}! Вы угадали исход и получили {profit} {res_label}"
            else:
                cursor.execute(f"UPDATE Users SET {field} = {field} - ? WHERE bot_id = ?", (bet, s_bot_id))
                new_text = f"{mention}, вы проиграли {bet} {res_label}"
            conn.commit()
        bot.send_message(chat_id=call.message.chat.id, text=new_text, parse_mode="HTML")
    finally:
        LOCKS[user_id].release()



init_db()
print("есть")
bot.infinity_polling()