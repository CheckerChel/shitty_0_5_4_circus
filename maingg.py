import telebot
import os
import sqlite3
import time
import random
import re

token = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(token)
CHATS = [-1003724538567, 7163427034]

from telebot import types

class Filter(telebot.SimpleCustomFilter):
    key = "imc"
    def check(self, message):
        return message.chat.id in CHATS
bot.add_custom_filter(Filter())

os.makedirs("data", exist_ok=True)
DB_PATH = "data/new_db.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
		CREATE TABLE IF NOT EXISTS Users (
			bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
			real_id INTEGER NOT NULL,
			ob REAL DEFAULT 0.0,
			lvl INTEGER DEFAULT 1,
			wins INTEGER DEFAULT 0,
			time INTEGER DEFAULT 0,
			bot_name TEXT DEFAULT '-'
		)
		""")
        conn.commit()

def check(id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM Users WHERE real_id = ?", (id,))
        user = cursor.fetchone()
        if user is None:
            cursor.execute("INSERT INTO Users (real_id) VALUES (?)", (id,))
            conn.commit()

@bot.message_handler(func=lambda message: message.text and message.text.lower()=="инфо", imc=True)
def info_cmd(message):
	check(message.from_user.id)
	bot.reply_to(message, "🎪Основная информация о боте.\n\nОБ - Очки Безумия, местная валюта.\n«Об» - помолиться.\n«Дать [число]» - передать ОБ.\n«Б»/«проф» - посмотреть профиль.\n«Уровень» - повысить свой уровень.\n«Уровень [число]» - узнать цену каждого уровня. Всего их 10.\n«Орёл/решка [число]» - сыграть в монетку на ОБ.\n«Имя [текст]» - поставить себе имя.\n«Обтоп» - посмотреть топ-10 богачей.\n«Винтоп» - посмотреть топ-10 лидеров по кол-ву побед.\n\nВо многих командах (например «дать») можно либо в конце указать айди нужного пользователя, либо либо ответить на любое его сообщение в чате. По доп.вопросам обращайтесь к @yamexa.")

@bot.message_handler(func=lambda message: message.text and message.text.lower().startswith("имя "), imc=True)
def change_name(message):
    user_id = message.from_user.id
    check(user_id)
    
    new_name = message.text[4:].strip()
    
    if not (3 <= len(new_name) <= 30):
        bot.reply_to(message, "❗Имя должно содержать только от 3 до 30 символов")
        return
        
    if not re.match(r"^[a-zA-Zа-яА-ЯёЁ0-9\s.,!\?-]+$", new_name):
        bot.reply_to(message, "❗Данное имя содержит недопустимые символы")
        return

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET bot_name = ? WHERE real_id = ?", (new_name, user_id))
        conn.commit()
        
    bot.reply_to(message, f"☕Ваше новое имя: {new_name}")



@bot.message_handler(func=lambda message: message.text and message.text.lower() == "об", imc=True)
def new_ob(message):
    user_id = message.from_user.id
    check(user_id)
    current_time = int(time.time())
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT time, lvl FROM Users WHERE real_id = ?", (user_id,))
        user_data = cursor.fetchone()
        last_time = user_data[0]
        lvl = user_data[1]
        time_passed = current_time - last_time
        if time_passed < 3600:
            m = ((3600 - time_passed) // 60) + 1
            bot.reply_to(message, f"⏳Не торопись, подожди ещё минуток... {m}")
            return
        n = round(random.uniform(0.01, 0.05), 2)
        final_ob = round(n * lvl, 2)
        cursor.execute("UPDATE Users SET ob = ob + ?, time = ? WHERE real_id = ?", (final_ob, current_time, user_id))
        conn.commit()
        bot.reply_to(message, f"✨Ты помолился и получил {final_ob} очков безумия (ОБ). Возвращайся через час")

@bot.message_handler(func=lambda message: message.text and (message.text.lower() in ["б", "проф"] or message.text.lower().startswith(("б ", "проф "))), imc=True)
def view_profile(message):
    user_id = message.from_user.id
    check(user_id)
    target_real_id = None
    args = message.text.split()
    
    if message.reply_to_message:
        target_real_id = message.reply_to_message.from_user.id
    elif len(args) > 1 and args[1].isdigit():
        target_bot_id = int(args[1])
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT real_id FROM Users WHERE bot_id = ?", (target_bot_id,))
            res = cursor.fetchone()
            if res:
                target_real_id = res[0]
            else:
                bot.reply_to(message, "❌Пользователь не найден")
                return
    else:
        target_real_id = user_id

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT bot_id, ob, lvl, wins, bot_name FROM Users WHERE real_id = ?", (target_real_id,))
        res = cursor.fetchone()
        if res:
            bot_id, ob, lvl, wins, display_name = res
            balance = round(ob, 2)
            mention = f'<a href="tg://user?id={target_real_id}">{display_name}</a>'
            
            response_text = (
                f"💠 {mention} 💠\n\n"
                f"🆔Айди {bot_id}\n"
                f"🔮Уровень {lvl}\n"
                f"💰Баланс: {balance} об\n"
                f"🛡️Побед: {wins}"
            )
            bot.reply_to(message, response_text, parse_mode="HTML")
        else:
            bot.reply_to(message, "❌Пользователь не найден")



@bot.message_handler(func=lambda message: message.text and message.text.lower().startswith(("дать ", "передать ")), imc=True)
def send_ob(message):
    user_id = message.from_user.id
    check(user_id)
    args = message.text.split()
    if len(args) < 2:
        return
    try:
        ob_amount = round(float(args[1]), 2)
    except ValueError:
        bot.reply_to(message, "❗Сумма перевода должна быть числом.")
        return
        
    if ob_amount <= 0:
        bot.reply_to(message, "❗Сумма перевода должна быть больше нуля.")
        return
        
    if ob_amount < 0.01:
        bot.reply_to(message, "❗Минимальная сумма перевода: 0.01")
        return
        
    target_real_id = None
    if message.reply_to_message:
        target_real_id = message.reply_to_message.from_user.id
    elif len(args) > 2 and args[2].isdigit():
        target_bot_id = int(args[2])
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT real_id FROM Users WHERE bot_id = ?", (target_bot_id,))
            res = cursor.fetchone()
            if res:
                target_real_id = res[0]
            else:
                bot.reply_to(message, "❌Пользователь не найден")
                return
    else:
        bot.reply_to(message, "❗Укажите ID получателя")
        return

    if target_real_id == user_id:
        bot.reply_to(message, "🙄Вы не можете переводить очки самому себе")
        return

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ob FROM Users WHERE real_id = ?", (user_id,))
        user_ob = cursor.fetchone()[0]
        if user_ob < ob_amount:
            bot.reply_to(message, "❌Недостаточно средств")
            return
        cursor.execute("SELECT bot_name FROM Users WHERE real_id = ?", (target_real_id,))
        target_name = cursor.fetchone()[0]
        
    mention = f'<a href="tg://user?id={target_real_id}">{target_name}</a>'
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("ПОДТВЕРДИТЬ", callback_data=f"tr_{user_id}_{target_real_id}_{ob_amount}"))
    bot.reply_to(message, f"Вы уверены, что хотите передать {ob_amount} об на {mention}?", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("tr_"))
def confirm_transfer(call):
    data = call.data.split("_", 3)
    if len(data) < 4:
        return
        
    sender_id = int(data[1])
    receiver_id = int(data[2])
    amount = float(data[3])
    
    if call.from_user.id != sender_id:
        bot.answer_callback_query(call.id, "Это не ваш перевод!", show_alert=True)
        return

    try:
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
    except Exception:
        bot.answer_callback_query(call.id, "Перевод уже обрабатывается или завершен.")
        return
        
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        cursor.execute("UPDATE Users SET ob = ob - ? WHERE real_id = ? AND ob >= ?", (amount, sender_id, amount))
        if cursor.rowcount == 0:
            bot.answer_callback_query(call.id, "Ошибка: Недостаточно средств.")
            return
            
        check(receiver_id)
        cursor.execute("UPDATE Users SET ob = ob + ? WHERE real_id = ?", (amount, receiver_id))
        conn.commit()
        
        cursor.execute("SELECT bot_name FROM Users WHERE real_id = ?", (receiver_id,))
        target_name = cursor.fetchone()[0]
        
    mention = f'<a href="tg://user?id={receiver_id}">{target_name}</a>'
    bot.edit_message_text(f"✅Вы передали {amount} об на {mention}.", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")


@bot.message_handler(func=lambda message: message.text and message.text.lower() == "обтоп", imc=True)
def view_ob_top(message):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT real_id, bot_name, ob FROM Users ORDER BY ob DESC LIMIT 10")
        users = cursor.fetchall()
        
    if not users:
        bot.reply_to(message, "Топ пока пуст.")
        return
        
    response_text = "👑Топ игроков по ОБ:\n"
    for i, user in enumerate(users, 1):
        user_real_id = user[0]
        user_name = user[1]
        user_ob = user[2]
        
        mention = f'<a href="tg://user?id={user_real_id}">{user_name}</a>'
        response_text += f"{i}. {mention} — {round(user_ob, 2)} об\n"
        
    bot.reply_to(message, response_text, parse_mode="HTML")


@bot.message_handler(func=lambda message: message.text and message.text.lower() == "винтоп", imc=True)
def view_win_top(message):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT real_id, bot_name, wins FROM Users ORDER BY wins DESC, time ASC LIMIT 10")
        rows = cursor.fetchall()
    text = "⚔️Топ-10 победителей:\n"
    for i, row in enumerate(rows, 1):
        mention = f'<a href="tg://user?id={row[0]}">{row[1]}</a>'
        text += f"{i}. {mention} - {row[2]} побед.\n"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text and message.text.lower().startswith(("орёл ", "орел ", "решка ")), imc=True)
def play_coin(message):
    user_id = message.from_user.id
    check(user_id)
    args = message.text.split()
    if len(args) < 2:
        return
    try:
        bet = round(float(args[1]), 2)
    except ValueError:
        return
    if bet < 0.01:
        bot.reply_to(message, "❗Минимальная ставка: 0.01")
        return
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ob FROM Users WHERE real_id = ?", (user_id,))
        user_ob = cursor.fetchone()[0]
        if user_ob < bet:
            bot.reply_to(message, "❌Недостаточно средств")
            return
        cmd = args[0].lower()
        choice = "орёл" if "ор" in cmd else "решка"
        outcome = random.choice(["орёл", "решка"])
        
        if choice == outcome:
            cursor.execute("UPDATE Users SET ob = ob + ?, wins = wins + ? WHERE real_id = ?", (bet, 1, user_id))
            conn.commit()
            bot.reply_to(message, f"🌹Выпало: {outcome}. Твой выигрыш: {round(bet * 2, 2)} об!")
        else:
            cursor.execute("UPDATE Users SET ob = ob - ? WHERE real_id = ?", (bet, user_id))
            conn.commit()
            bot.reply_to(message, f"🥀Выпало: {outcome}. Ты проиграл {bet} об")

@bot.message_handler(func=lambda message: message.text and message.text.lower().startswith("создать ") and message.from_user.id in CHATS, imc=True)
def admin_create_ob(message):
    user_id = message.from_user.id
    check(user_id)
    args = message.text.split()
    if len(args) < 2:
        return
    try:
        amount = round(float(args[1]), 2)
    except ValueError:
        return
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET ob = ob + ? WHERE real_id = ?", (amount, user_id))
        conn.commit()
    bot.reply_to(message, f"Вы выдали себе {amount} об")



PRICES = {2: 1.0, 3: 5.0, 4: 10.0, 5: 15.0, 6: 20.0, 7: 30.0, 8: 50.0, 9: 75.0, 10: 100.0}

@bot.message_handler(func=lambda message: message.text and message.text.lower().startswith(("установить уровень ")), imc=True)
def admin_set_lvl(message):
    if message.from_user.id not in CHATS:
        return
    user_id = message.from_user.id
    check(user_id)
    args = message.text.split()
    if len(args) < 3:
        return
    if not args[2].isdigit():
        return
    target_lvl = int(args[2])
    if not (1 <= target_lvl <= 10):
        return
    current_time = int(time.time())
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET lvl = ?, time = ? WHERE real_id = ?", (target_lvl, current_time, user_id))
        conn.commit()
    bot.reply_to(message, f"Вы установили себе {target_lvl} уровень.")

@bot.message_handler(func=lambda message: message.text and (message.text.lower() in ["уровень", "ур"] or message.text.lower().startswith(("уровень ", "ур "))), imc=True)
def lvl_command(message):
    user_id = message.from_user.id
    check(user_id)
    args = message.text.split()
    if len(args) == 1:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT lvl FROM Users WHERE real_id = ?", (user_id,))
            current_lvl = cursor.fetchone()[0]
        if current_lvl >= 10:
            bot.reply_to(message, "✨У вас уже максимальный уровень!")
            return
        next_lvl = current_lvl + 1
        cost = PRICES[next_lvl]
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("ПОВЫСИТЬ", callback_data=f"up_{user_id}_{next_lvl}"))
        bot.reply_to(message, f"Повысить уровень за {cost} об?", reply_markup=markup)
    else:
        if not args[1].isdigit():
            return
        target_lvl = int(args[1])
        if target_lvl == 1:
            bot.reply_to(message, "Уровень 1 является начальным.")
            return
        if target_lvl not in PRICES:
            return
        cost = PRICES[target_lvl]
        bot.reply_to(message, f"Уровень {target_lvl} стоит {cost} об.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("up_"))
def confirm_lvl_up(call):
    data = call.data.split("_")
    buyer_id = int(data[1])
    target_lvl = int(data[2])
    if call.from_user.id != buyer_id:
        return
    cost = PRICES[target_lvl]
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ob, lvl FROM Users WHERE real_id = ?", (buyer_id,))
        user_data = cursor.fetchone()
        user_ob = user_data[0]
        current_lvl = user_data[1]
        if current_lvl >= target_lvl:
            bot.answer_callback_query(call.id, "Уровень уже повышен.")
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
            return
        if user_ob < cost:
            bot.answer_callback_query(call.id, "Недостаточно средств.")
            return
        current_time = int(time.time())
        cursor.execute("UPDATE Users SET ob = ob - ?, lvl = ?, time = ? WHERE real_id = ?", (cost, target_lvl, current_time, buyer_id))
        conn.commit()
    bot.edit_message_text(f"🎉Ваш уровень повышен до {target_lvl}!", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)



init_db()
print("есть")
bot.infinity_polling()