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
DB_PATH = "data/new_db.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
		CREATE TABLE IF NOT EXISTS Users (
			bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
			real_id INTEGER NOT NULL,
			coins INTEGER DEFAULT 0,
			time INTEGER DEFAULT 0,
			luck REAL DEFAULT 1,
			luck_time INTEGER DEFAULT 0
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



def get_user_data(field, value):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT bot_id, real_id, coins, luck FROM Users WHERE {field} = ?", (value,))
        return cursor.fetchone()

@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().split()[0] in ['баланс', 'б'])
def show_balance(message):
    check(message.from_user.id)
    args = message.text.split()
    target_user = None
    if len(args) > 1:
        target_id = args[1].replace('#', '')
        if target_id.isdigit():
            target_user = get_user_data("bot_id", int(target_id))
            if not target_user:
                bot.reply_to(message, "Пользователь не найден")
                return
    elif message.reply_to_message:
        target_user = get_user_data("real_id", message.reply_to_message.from_user.id)
        if not target_user:
            bot.reply_to(message, "Пользователь не найден")
            return
    else:
        target_user = get_user_data("real_id", message.from_user.id)
    bot_id, real_id, coins, luck, _ = target_user
    luck_percent = int(round(luck * 100 - 100))
    
    text = f'👤<a href="tg://user?id={real_id}">#{bot_id}</a>\n📦Баланс: {coins}Ж\n🍀Доп. удача: {luck_percent}%'
    bot.send_message(message.chat.id, text, parse_mode="HTML")



def get_user_by_expr(field, value):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT bot_id, real_id, coins FROM Users WHERE {field} = ?", (value,))
        return cursor.fetchone()
def delete_msg_after_timeout(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().startswith('дать '))
def request_transfer(message):
    check(message.from_user.id)
    args = message.text.split()
    if len(args) < 2:
        return
    try:
        amount = int(args[1])
        if amount <= 0: return
    except ValueError:
        return
    sender = get_user_by_expr("real_id", message.from_user.id)
    if not sender or sender[2] < amount:
        bot.reply_to(message, "Недостаточно жетонов")
        return
    target_user = None
    if len(args) > 2:
        t_id = args[2].replace('#', '')
        if t_id.isdigit():
            target_user = get_user_by_expr("bot_id", int(t_id))
    elif message.reply_to_message:
        check(message.reply_to_message.from_user.id)
        target_user = get_user_by_expr("real_id", message.reply_to_message.from_user.id)
    if not target_user or sender[0] == target_user[0]:
        bot.reply_to(message, "Пользователь не найден")
        return
    
    markup = InlineKeyboardMarkup()
    btn = InlineKeyboardButton(text="✅Подтвердить", callback_data=f"pay_{sender[0]}_{target_user[0]}_{amount}", style="success")
    markup.add(btn)
    text = f'Вы уверены что хотите перевести {amount}Ж на <a href="tg://user?id={target_user[1]}">#{target_user[0]}</a>?'
    sent_msg = bot.reply_to(message, text, parse_mode="HTML", reply_markup=markup)
    
    threading.Timer(60.0, delete_msg_after_timeout, args=[sent_msg.chat.id, sent_msg.message_id]).start()



@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def confirm_transfer(call):
    _, s_bot_id, t_bot_id, amount_str = call.data.split("_")
    s_bot_id, t_bot_id, amount = int(s_bot_id), int(t_bot_id), int(amount_str)
    sender = get_user_by_expr("bot_id", s_bot_id)
    if not sender or call.from_user.id != sender[1]:
        bot.answer_callback_query(call.id)
        return
    bot.answer_callback_query(call.id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT coins FROM Users WHERE bot_id = ?", (s_bot_id,))
        res = cursor.fetchone()
        
        if not res or res[0] < amount:
            try:
                bot.edit_message_text("Недостаточно жетонов", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
            except Exception:
                pass
            return
        cursor.execute("UPDATE Users SET coins = coins - ? WHERE bot_id = ?", (amount, s_bot_id))
        cursor.execute("UPDATE Users SET coins = coins + ? WHERE bot_id = ?", (amount, t_bot_id))
        conn.commit()
    target = get_user_by_expr("bot_id", t_bot_id)
    new_text = f'💸<a href="tg://user?id={sender[1]}">#{s_bot_id}</a> перевёл {amount}Ж на <a href="tg://user?id={target[1]}">#{t_bot_id}</a>'
    
    try:
        bot.edit_message_text(new_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=None)
    except Exception:
        pass



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower() == 'кд снять')
def reset_cooldown(message):
    if message.from_user.id not in CHATS:
        return
        
    check(message.from_user.id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET time = 0 WHERE real_id = ?", (message.from_user.id,))
        conn.commit()
    bot.reply_to(message, "Ваш личный КД на бонус был успешно обнулен!")



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().startswith('выдать жетоны '))
def self_give_coins(message):
    if message.from_user.id not in CHATS:
        return
    check(message.from_user.id)
    args = message.text.split()
    if len(args) < 3:
        return
    try:
        amount = int(args[2])
        if amount <= 0: return
    except ValueError:
        return
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET coins = coins + ? WHERE real_id = ?", (amount, message.from_user.id))
        conn.commit()
    bot.reply_to(message, f"Вы выдали себе {amount}Ж")



def get_user_data(field, value):
    current_time = int(time.time())
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT bot_id, real_id, coins, luck, luck_time FROM Users WHERE {field} = ?", (value,))
        res = cursor.fetchone()
        if not res:
            return None
        
        bot_id, real_id, coins, luck, luck_time = res
        if luck_time > 0 and current_time > luck_time:
            cursor.execute("UPDATE Users SET luck = 1, luck_time = 0 WHERE real_id = ?", (real_id,))
            conn.commit()
            luck = 1.0
            luck_time = 0
            
        return bot_id, real_id, coins, luck, luck_time

import time
import random

@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower() == 'бонус')
def get_bonus(message):
    check(message.from_user.id)
    current_time = int(time.time())
    
    user_data = get_user_data("real_id", message.from_user.id)
    if not user_data: return
    _, _, _, current_luck, luck_time = user_data
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT time FROM Users WHERE real_id = ?", (message.from_user.id,))
        res = cursor.fetchone()
        user_time = res[0] if res else 0
        
        if current_time - user_time < 10800:
            remaining = 10800 - (current_time - user_time)
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            bot.reply_to(message, f"⏳Не торопись! Осталось ждать:\n{hours} ч. {minutes} мин. {seconds} сек.")
            return

        bonus = random.randint(100, 300)
        rand_val = random.random()

        if rand_val < 0.00001:
            bonus = random.randint(1000, 10000)
            text = f"🎉Джекпот! Ваш бонус составил {bonus}Ж. Возвращайтесь через:\n3 ч. 0 мин. 0 сек."
            cursor.execute("UPDATE Users SET coins = coins + ?, time = ? WHERE real_id = ?", (bonus, current_time, message.from_user.id))
        elif rand_val < 0.001:
            new_luck = current_luck + 0.05
            new_luck_time = max(luck_time, current_time) + 18000
            luck_percent = int(round(new_luck * 100 - 100))
            text = f"✨Вау! Твой бонус составил {bonus}Ж, а также ты получил +5% дополнительной удачи! В течение 5 часов каждый твой выигрыш будет на {luck_percent}% больше. Возвращайтесь через:\n3 ч. 0 мин. 0 сек."
            cursor.execute("UPDATE Users SET coins = coins + ?, time = ?, luck = ?, luck_time = ? WHERE real_id = ?", 
                           (bonus, current_time, new_luck, new_luck_time, message.from_user.id))
        else:
            text = f"💰Вы забрали бонус в {bonus}Ж.\nВозвращайтесь через 3 часа"
            cursor.execute("UPDATE Users SET coins = coins + ?, time = ? WHERE real_id = ?", (bonus, current_time, message.from_user.id))
            
        conn.commit()
    bot.reply_to(message, text)



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().split()[0] in ['кубы', 'кости'])
def init_dice_game(message):
    check(message.from_user.id)
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Укажите ставку")
        return
    try:
        bet = int(args[1])
        if bet <= 0: return
    except ValueError:
        return

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT coins FROM Users WHERE real_id = ?", (message.from_user.id,))
        res = cursor.fetchone()
        if not res or res[0] < bet:
            bot.reply_to(message, "Недостаточно жетонов")
            return
        cursor.execute("UPDATE Users SET coins = coins - ? WHERE real_id = ?", (bet, message.from_user.id))
        conn.commit()

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(text="Чётное", callback_data=f"dice_{bet}_is_even", style="success"),
        InlineKeyboardButton(text="Нечётное", callback_data=f"dice_{bet}_is_odd", style="danger")
    )
    markup.row(
        InlineKeyboardButton(text="Больше", callback_data=f"dice_{bet}_high", style="success"),
        InlineKeyboardButton(text="Меньше", callback_data=f"dice_{bet}_low", style="danger")
    )
    
    row3 = [InlineKeyboardButton(text=str(i), callback_data=f"dice_{bet}_exact_{i}") for i in range(1, 4)]
    row4 = [InlineKeyboardButton(text=str(i), callback_data=f"dice_{bet}_exact_{i}") for i in range(4, 7)]
    markup.row(*row3)
    markup.row(*row4)

    bot.reply_to(message, "Выбери исход:\n• Четное/нечетное — 2х\nБольше/меньше — 2х\nТочное число - 6х", reply_markup=markup)



@bot.callback_query_handler(func=lambda call: call.data.startswith("dice_"))
def process_dice_click(call):
    data = call.data.split("_")
    bet = int(data[1])
    game_type = data[2]
    chosen_val = data[3] if len(data) > 3 else None

    if call.message.reply_to_message and call.message.reply_to_message.from_user.id != call.from_user.id:
        bot.answer_callback_query(call.id)
        return

    user_data = get_user_data("real_id", call.from_user.id)
    if not user_data:
        bot.answer_callback_query(call.id)
        return
    bot_id, real_id, coins, luck, _ = user_data

    if call.message.reply_markup is None:
        bot.answer_callback_query(call.id)
        return

    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
    except Exception:
        return

    cube_result = random.randint(1, 6)
    is_win = False

    if game_type == "is":
        correct_text = "Чётное" if cube_result % 2 == 0 else "Нечётное"
        choice_text = "Чётное" if chosen_val == "even" else "Нечётное"
        if chosen_val == "even" and cube_result % 2 == 0: is_win = True
        elif chosen_val == "odd" and cube_result % 2 != 0: is_win = True
        multiplier = 2
    elif game_type == "high":
        correct_text = "Больше" if cube_result >= 4 else "Меньше"
        choice_text = "Больше"
        if cube_result >= 4: is_win = True
        multiplier = 2
    elif game_type == "low":
        correct_text = "Меньше" if cube_result <= 3 else "Больше"
        choice_text = "Меньше"
        if cube_result <= 3: is_win = True
        multiplier = 2
    elif game_type == "exact":
        correct_text = str(cube_result)
        choice_text = f"Число {chosen_val}"
        if cube_result == int(chosen_val): is_win = True
        multiplier = 6

    if is_win:
        reward = int(round((bet * multiplier) * luck))
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET coins = coins + ? WHERE real_id = ?", (reward, call.from_user.id))
            conn.commit()
        end_text = f"🌹Удача! Правильный ответ был — {correct_text}.\nТы выиграл {reward}Ж"
    else:
        end_text = f"🥀Неудача! Правильный ответ был — {correct_text}.\nТы выбрал — {choice_text}.\nТы проиграл {bet}Ж"

    try:
        bot.edit_message_text(end_text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
    except Exception: pass



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().startswith('установить удачу '))
def set_luck(message):
    if message.from_user.id not in CHATS:
        return
    check(message.from_user.id)
    args = message.text.split()
    if len(args) < 3: return
    try:
        val = float(args[2].replace(',', '.'))
        if val < 0: return
    except ValueError:
        return
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET luck = ?, luck_time = 0 WHERE real_id = ?", (val, message.from_user.id))
        conn.commit()
    bot.reply_to(message, f"Ваша удача успешно установлена на значение {val}")



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().split()[0] in ['орел', 'орёл', 'решка'])
def game_coinflip(message):
    check(message.from_user.id)
    args = message.text.split()
    user_choice = args[0].lower()
    if user_choice == 'орёл':
        user_choice = 'орел'

    if len(args) < 2:
        bot.reply_to(message, "Укажите ставку")
        return
    try:
        bet = int(args[1])
        if bet <= 0: return
    except ValueError:
        return

    user_data = get_user_data("real_id", message.from_user.id)
    if not user_data: return
    bot_id, real_id, coins, luck, _ = user_data

    if coins < bet:
        bot.reply_to(message, "Недостаточно жетонов")
        return

    bot_result = random.choice(['орел', 'решка'])
    result_word = "орёл" if bot_result == "орел" else "решка"
    
    if user_choice == bot_result:
        reward = int(round((bet * 2) * luck))
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET coins = coins + ? WHERE real_id = ?", (reward, message.from_user.id))
            conn.commit()
        bot.reply_to(message, f"🌹Выпало: {result_word}.\nТы выиграл {reward}Ж")
    else:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET coins = coins - ? WHERE real_id = ?", (bet, message.from_user.id))
            conn.commit()
        bot.reply_to(message, f"🥀Выпало: {result_word}.\nТы проиграл {bet}Ж")



import time
import random
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

duels = {}

@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().startswith('дуэль '))
def create_duel(message):
    check(message.from_user.id)
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Укажите ставку")
        return
    try:
        bet = int(args[1])
        if bet <= 0: return
    except ValueError:
        return

    user_data = get_user_data("real_id", message.from_user.id)
    if not user_data: return
    bot_id, real_id, coins, _, _ = user_data

    if coins < bet:
        bot.reply_to(message, "Недостаточно жетонов")
        return

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="⚔️", callback_data=f"join_{real_id}_{bet}", style="success"))
    
    text = f'🛡️<a href="tg://user?id={real_id}">#{bot_id}</a> ждёт соперника.\nСтавка: {bet}Ж'
    bot.reply_to(message, text, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("join_"))
def join_duel(call):
    _, creator_real_id, bet_str = call.data.split("_")
    creator_real_id = int(creator_real_id)
    bet = int(bet_str)
    joiner_real_id = call.from_user.id

    if joiner_real_id == creator_real_id:
        bot.answer_callback_query(call.id)
        return

    check(joiner_real_id)
    joiner_data = get_user_data("real_id", joiner_real_id)
    creator_data = get_user_data("real_id", creator_real_id)
    
    if not joiner_data or not creator_data:
        bot.answer_callback_query(call.id)
        return

    j_bot_id, _, j_coins, _, _ = joiner_data
    c_bot_id, _, c_coins, _, _ = creator_data

    if j_coins < bet:
        bot.answer_callback_query(call.id, text="Недостаточно жетонов", show_alert=True)
        return

    if c_coins < bet:
        bot.answer_callback_query(call.id, text="У создателя дуэли больше нет жетонов", show_alert=True)
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception: pass
        return

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET coins = coins - ? WHERE real_id = ?", (bet, creator_real_id))
        cursor.execute("UPDATE Users SET coins = coins - ? WHERE real_id = ?", (bet, joiner_real_id))
        conn.commit()

    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception: pass

    game_id = call.message.message_id
    duels[game_id] = {
        "p1": creator_real_id, "p1_bid": c_bot_id, "p1_choice": None,
        "p2": joiner_real_id, "p2_bid": j_bot_id, "p2_choice": None,
        "bet": bet, "start": time.time()
    }

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(text="🪨", callback_data=f"rsp_{game_id}_r"),
        InlineKeyboardButton(text="✂️", callback_data=f"rsp_{game_id}_s"),
        InlineKeyboardButton(text="🧻", callback_data=f"rsp_{game_id}_p")
    )

    text = f'⚔️<a href="tg://user?id={creator_real_id}">#{c_bot_id}</a> VS <a href="tg://user?id={joiner_real_id}">#{j_bot_id}</a>\nСтавка: {bet}Ж'
    bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("rsp_"))
def process_rsp_choice(call):
    _, game_id_str, choice = call.data.split("_")
    game_id = int(game_id_str)
    user_real_id = call.from_user.id

    if game_id not in duels:
        bot.answer_callback_query(call.id)
        return

    game = duels[game_id]
    if user_real_id != game["p1"] and user_real_id != game["p2"]:
        bot.answer_callback_query(call.id)
        return

    emoji_map = {"r": "🪨", "s": "✂️", "p": "🧻"}
    
    if user_real_id == game["p1"]:
        if game["p1_choice"] is not None:
            bot.answer_callback_query(call.id, text=f"Ты уже выбрал {emoji_map[game['p1_choice']]}", show_alert=True)
            return
        game["p1_choice"] = choice
    else:
        if game["p2_choice"] is not None:
            bot.answer_callback_query(call.id, text=f"Ты уже выбрал {emoji_map[game['p2_choice']]}", show_alert=True)
            return
        game["p2_choice"] = choice

    bot.answer_callback_query(call.id)

    if time.time() - game["start"] > 180:
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception: pass
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET coins = coins + ? WHERE real_id = ?", (game["bet"], game["p1"]))
            cursor.execute("UPDATE Users SET coins = coins + ? WHERE real_id = ?", (game["bet"], game["p2"]))
            conn.commit()

        text = f'<a href="tg://user?id={game["p1"]}">#{game["p1_bid"]}</a> VS <a href="tg://user?id={game["p2"]}">#{game["p2_bid"]}</a>\n🕛Ничья! Бездействие привело к окончанию боя.\nСтавка была: {game["bet"]}Ж'
        bot.send_message(call.message.chat.id, text, parse_mode="HTML")
        duels.pop(game_id, None)
        return

    if game["p1_choice"] and game["p2_choice"]:
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception: pass

        p1_c, p2_c = game["p1_choice"], game["p2_choice"]
        bet = game["bet"]
        
        if p1_c == p2_c:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE Users SET coins = coins + ? WHERE real_id = ?", (bet, game["p1"]))
                cursor.execute("UPDATE Users SET coins = coins + ? WHERE real_id = ?", (bet, game["p2"]))
                conn.commit()
            end_text = f'<a href="tg://user?id={game["p1"]}">#{game["p1_bid"]}</a> VS <a href="tg://user?id={game["p2"]}">#{game["p2_bid"]}</a>\nСтавка: {bet}Ж\n☕Ничья! #{game["p1_bid"]} и #{game["p2_bid"]} выбрали {emoji_map[p1_c]}'
        else:
            p1_win = (p1_c == "r" and p2_c == "s") or (p1_c == "s" and p2_c == "p") or (p1_c == "p" and p2_c == "r")
            
            if p1_win:
                win_id, win_bid, win_emoji = game["p1"], game["p1_bid"], emoji_map[p1_c]
                lose_id, lose_bid, lose_emoji = game["p2"], game["p2_bid"], emoji_map[p2_c]
            else:
                win_id, win_bid, win_emoji = game["p2"], game["p2_bid"], emoji_map[p2_c]
                lose_id, lose_bid, lose_emoji = game["p1"], game["p1_bid"], emoji_map[p1_c]

            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE Users SET coins = coins + ? WHERE real_id = ?", (bet * 2, win_id))
                conn.commit()

            end_text = f'⚔️<a href="tg://user?id={game["p1"]}">#{game["p1_bid"]}</a> VS <a href="tg://user?id={game["p2"]}">#{game["p2_bid"]}</a>\nСтавка: {bet}Ж\n🏆Победитель — {win_emoji} <a href="tg://user?id={win_id}">#{win_bid}</a>\n🪦Проигравший — {lose_emoji} <a href="tg://user?id={lose_id}">#{lose_bid}</a>'

        bot.send_message(call.message.chat.id, end_text, parse_mode="HTML")
        duels.pop(game_id, None)



@bot.message_handler(imc=True, func=lambda message: message.text and message.text.lower().split() in [['лидер'], ['лидеры']])
def show_leaderboard(message):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT bot_id, real_id, coins FROM Users WHERE coins > 0 ORDER BY coins DESC LIMIT 15")
        leaders = cursor.fetchall()
    text = "<b>👑Топ-15 богачей группы</b>\n\n"
    if not leaders:
        text += "Таблица пуста"
    else:
        for idx, (bot_id, real_id, coins) in enumerate(leaders, 1):
            text += f"{idx}. <a href=\"tg://user?id={real_id}\">#{bot_id}</a> — {coins}Ж\n"
    bot.reply_to(message, text, parse_mode="HTML")



@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() in ["инфо", "/info"], imc=True)
def show_info(message):
    try:
        check(message.from_user.id)
        bot.reply_to(message, "Хай!")
    except Exception as e:
        print(f"Ошибка команды инфо: {e}")



init_db()
print("есть")
bot.infinity_polling()