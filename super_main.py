import telebot
import os
import sqlite3
import time
import random
import re
import math

token = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(token)
CHATS = [-1003724538567, 7163427034]
ITEMS_PER_PAGE = 15

from telebot import types
import math
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


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
			coins REAL DEFAULT 0.0,
			lvl INTEGER DEFAULT 1,
			wins INTEGER DEFAULT 0,
			time INTEGER DEFAULT 0,
			all_mr INTEGER DEFAULT 0,
			bot_name TEXT DEFAULT '-'
		)
		""")
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Mushrooms (
            mr_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mr_name TEXT NOT NULL,
            mr_sticker TEXT NOT NULL,
            mr_rare TEXT NOT NULL,
            mr_price INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES Users (real_id)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS MushroomTypes (
            type_id INTEGER PRIMARY KEY AUTOINCREMENT,
            mr_name TEXT NOT NULL,
            mr_sticker TEXT NOT NULL
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



def get_inventory_data(user_id, page=1):
    check(user_id)
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT all_mr FROM Users WHERE real_id = ?", (user_id,))
        all_mr_row = cursor.fetchone()
        all_mr = all_mr_row[0] if all_mr_row else 0
        
        cursor.execute("SELECT COUNT(*) FROM Mushrooms WHERE user_id = ?", (user_id,))
        total_items_row = cursor.fetchone()
        total_items = total_items_row[0] if total_items_row else 0
        
        total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if total_items > 0 else 1
        
        if page > total_pages:
            page = total_pages
        if page < 1:
            page = 1
            
        offset = (page - 1) * ITEMS_PER_PAGE
        cursor.execute("""
            SELECT mr_id, mr_price, mr_name, mr_rare 
            FROM Mushrooms 
            WHERE user_id = ? 
            ORDER BY mr_id DESC 
            LIMIT ? OFFSET ?
        """, (user_id, ITEMS_PER_PAGE, offset))
        
        mushrooms = cursor.fetchall()

    text_lines = [f"<b>Ваших грибов: {all_mr}</b>\n"]
    
    for mr_id, mr_price, mr_name, mr_rare in mushrooms:
        short_rare = "О" if mr_rare == "Обычный" else ("Э" if mr_rare == "Элитный" else "Л")
        text_lines.append(f"#{mr_id} ({mr_price}R) — [{short_rare}] {mr_name}")
        
    text_lines.append(f"\n<b>Стр. {page}/{total_pages}</b>")
    final_text = "\n".join(text_lines)
    
    markup = InlineKeyboardMarkup()
    buttons = []
    
    if total_pages > 1:
        if page > 1:
            buttons.append(InlineKeyboardButton("‹", callback_data=f"inv_page:{page-1}:{user_id}"))
        if page < total_pages:
            buttons.append(InlineKeyboardButton("›", callback_data=f"inv_page:{page+1}:{user_id}"))
            
        if buttons:
            markup.row(*buttons)
            
    return final_text, markup



@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() in ["инвентарь", "инв", "/inv"], imc=True)
def show_inventory(message):
    try:
        user_id = message.from_user.id
        text, markup = get_inventory_data(user_id, page=1)
        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        print(f"Ошибка в команде инвентаря: {e}")

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("inv_page:"), imc=True)
def refresh_inventory(call):
    try:
        data_parts = call.data.split(":")
        page = int(data_parts[1])
        owner_id = int(data_parts[2])
        
        if call.from_user.id != owner_id:
            try:
                bot.answer_callback_query(call.id, text="Это не ваша корзина!", show_alert=True)
            except Exception:
                pass
            return

        text, markup = get_inventory_data(owner_id, page)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup
        )
    except Exception:
        pass
    finally:
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass


@bot.message_handler(func=lambda msg: msg.text and (msg.text.lower().startswith("проф") or msg.text.lower().startswith("/prof")), imc=True)
def show_profile(message):
    try:
        target_id = None
        args = message.text.split()

        if message.reply_to_message:
            target_id = message.reply_to_message.from_user.id
            check(target_id)

        elif len(args) > 1:
            potential_id = args[1]
            if potential_id.isdigit():
                num = int(potential_id)
                with sqlite3.connect(DB_PATH) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT real_id FROM Users WHERE bot_id = ? OR real_id = ?", (num, num))
                    row = cursor.fetchone()
                    if row:
                        target_id = row[0]

        elif len(args) == 1:
            target_id = message.from_user.id
            check(target_id)

        if not target_id:
            bot.reply_to(message, "Пользователь не найден")
            return

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT bot_id, bot_name, all_mr, coins, wins, real_id FROM Users WHERE real_id = ?", (target_id,))
            user_data = cursor.fetchone()

        if not user_data:
            bot.reply_to(message, "Пользователь не найден")
            return

        bot_id, bot_name, all_mr, coins, wins, real_id = user_data
        profile_link = f'<a href="tg://user?id={real_id}">#{bot_id}</a>'
        
        text = (
            f"<b>Профиль {profile_link}:</b>\n"
            f"Имя: {bot_name}\n"
            f"Грибов: {all_mr}\n"
            f"Баланс: {coins}R\n"
            f"Побед: {wins}"
        )

        bot.send_message(message.chat.id, text, parse_mode="HTML")

    except Exception as e:
        print(f"Ошибка в команде профиля: {e}")



@bot.message_handler(func=lambda msg: msg.text and (msg.text.lower().startswith("продать ") or msg.text.lower().startswith("/sell ")), imc=True)
def sell_mushroom_cmd(message):
    try:
        user_id = message.from_user.id
        check(user_id)
        
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            return
            
        mr_id = int(args[1])

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, mr_price FROM Mushrooms WHERE mr_id = ?", (mr_id,))
            row = cursor.fetchone()

        if not row:
            bot.reply_to(message, "Гриб не найден")
            return

        owner_id, price = row[0], row[1]
        if owner_id != user_id:
            bot.reply_to(message, "Это не ваш гриб!")
            return

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Продать", callback_data=f"sell_confirm:{mr_id}:{user_id}"))
        bot.reply_to(message, f"Вы уверены что хотите продать #{mr_id} за {price}R?", reply_markup=markup)
    except Exception as e:
        print(f"Ошибка команды продажи: {e}")

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("sell_confirm:"), imc=True)
def sell_mushroom_callback(call):
    try:
        data_parts = call.data.split(":")
        mr_id = int(data_parts[1])
        owner_id = int(data_parts[2])

        if call.from_user.id != owner_id:
            try:
                bot.answer_callback_query(call.id, text="Данная кнопка не для вас", show_alert=True)
            except Exception: pass
            return

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT mr_price FROM Mushrooms WHERE mr_id = ? AND user_id = ?", (mr_id, owner_id))
            row = cursor.fetchone()
            
            if not row:
                bot.edit_message_text("Гриб уже продан или не существует.", chat_id=call.message.chat.id, message_id=call.message.message_id)
                return
                
            price = row[0]
            
            cursor.execute("DELETE FROM Mushrooms WHERE mr_id = ?", (mr_id,))
            cursor.execute("UPDATE Users SET coins = round(coins + ?, 2) WHERE real_id = ?", (price, owner_id))
            conn.commit()

        bot.edit_message_text(f"#{mr_id} продан за {price}R", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
    except Exception: pass
    finally:
        try: bot.answer_callback_query(call.id)
        except Exception: pass



@bot.message_handler(func=lambda msg: msg.text and any(msg.text.lower().startswith(x) for x in ["дать ", "передать ", "/give "]), imc=True)
def give_cmd(message):
    try:
        user_id = message.from_user.id
        check(user_id)
        
        args = message.text.split()
        if len(args) < 2:
            return

        target_arg = args.lower()
        
        # ВЕТКА А: ПЕРЕДАЧА ГРИБА (формат: дать #5 или дать #5 12345)
        if target_arg.startswith("#"):
            mr_id_str = target_arg.replace("#", "")
            if not mr_id_str.isdigit(): 
                return
            mr_id = int(mr_id_str)

            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM Mushrooms WHERE mr_id = ?", (mr_id,))
                row = cursor.fetchone()

            if not row:
                bot.reply_to(message, "Гриб не найден")
                return

            owner_id = row
            if owner_id != user_id:
                bot.reply_to(message, "Это не ваш гриб")
                return

            target_user_id = None
            if message.reply_to_message:
                target_user_id = message.reply_to_message.from_user.id
                check(target_user_id)
            elif len(args) > 2 and args.isdigit():
                target_user_id = int(args)
            
            if not target_user_id: 
                return
            if target_user_id == user_id:
                return

            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT bot_name FROM Users WHERE real_id = ?", (target_user_id,))
                t_row = cursor.fetchone()

            if not t_row:
                bot.reply_to(message, "Пользователь не найден")
                return

            t_name = t_row
            t_link = f'<a href="tg://user?id={target_user_id}">{t_name}</a>'
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Передать", callback_data=f"give_mr:{mr_id}:{user_id}:{target_user_id}"))
            bot.send_message(message.chat.id, f"Вы уверены что хотите передать гриб #{mr_id} на {t_link}?", parse_mode="HTML", reply_markup=markup)

        # ВЕТКА Б: ПЕРЕДАЧА МОНЕТ (формат: дать 50r или дать 50р 12345)
        else:
            clean_amount = args.lower().replace("r", "").replace("р", "")
            try:
                amount = round(float(clean_amount), 2)
            except ValueError:
                return

            if amount <= 0: 
                return

            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT coins FROM Users WHERE real_id = ?", (user_id,))
                my_coins_row = cursor.fetchone()
            
            my_coins = my_coins_row if my_coins_row else 0.0

            if my_coins < amount:
                bot.reply_to(message, "Недостаточно средств")
                return

            target_user_id = None
            if message.reply_to_message:
                target_user_id = message.reply_to_message.from_user.id
                check(target_user_id)
            elif len(args) > 2 and args.isdigit():
                target_user_id = int(args)

            if not target_user_id: 
                return
            if target_user_id == user_id: 
                return

            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT bot_name FROM Users WHERE real_id = ?", (target_user_id,))
                t_row = cursor.fetchone()

            if not t_row:
                bot.reply_to(message, "Пользователь не найден")
                return

            t_name = t_row
            t_link = f'<a href="tg://user?id={target_user_id}">{t_name}</a>'

            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Передать", callback_data=f"give_money:{amount}:{user_id}:{target_user_id}"))
            bot.send_message(message.chat.id, f"Вы уверены что хотите передать {amount}R на {t_link}?", parse_mode="HTML", reply_markup=markup)

    except Exception as e:
        print(f"Ошибка команды передачи: {e}")

# ОБРАБОТЧИК КНОПКИ ПЕРЕДАЧИ ГРИБА
@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("give_mr:"), imc=True)
def give_mr_callback(call):
    try:
        data_parts = call.data.split(":")
        mr_id = int(data_parts)
        sender_id = int(data_parts)
        recipient_id = int(data_parts)

        if call.from_user.id != sender_id:
            try: 
                bot.answer_callback_query(call.id, text="Эта кнопка не для тебя", show_alert=True)
            except Exception: pass
            return

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM Mushrooms WHERE mr_id = ? AND user_id = ?", (mr_id, sender_id))
            if not cursor.fetchone():
                bot.edit_message_text("Передача отменена: гриб уже не принадлежит вам или не существует.", chat_id=call.message.chat.id, message_id=call.message.message_id)
                return

            cursor.execute("UPDATE Mushrooms SET user_id = ? WHERE mr_id = ?", (recipient_id, mr_id))
            cursor.execute("UPDATE Users SET all_mr = max(0, all_mr - 1) WHERE real_id = ?", (sender_id,))
            cursor.execute("UPDATE Users SET all_mr = all_mr + 1 WHERE real_id = ?", (recipient_id,))
            conn.commit()

        bot.edit_message_text(f"Гриб #{mr_id} успешно передан!", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
    except Exception: pass
    finally:
        try: bot.answer_callback_query(call.id)
        except Exception: pass

# ОБРАБОТЧИК КНОПКИ ПЕРЕДАЧИ ДЕНЕГ
@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("give_money:"), imc=True)
def give_money_callback(call):
    try:
        data_parts = call.data.split(":")
        amount = float(data_parts)
        sender_id = int(data_parts)
        recipient_id = int(data_parts)

        if call.from_user.id != sender_id:
            try: 
                bot.answer_callback_query(call.id, text="Эта кнопка не для тебя", show_alert=True)
            except Exception: pass
            return

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT coins FROM Users WHERE real_id = ?", (sender_id,))
            sender_coins_row = cursor.fetchone()
            sender_coins = sender_coins_row if sender_coins_row else 0.0
            
            if sender_coins < amount:
                bot.edit_message_text("Недостаточно средств для завершения транзакции.", chat_id=call.message.chat.id, message_id=call.message.message_id)
                return

            cursor.execute("UPDATE Users SET coins = round(coins - ?, 2) WHERE real_id = ?", (amount, sender_id))
            cursor.execute("UPDATE Users SET coins = round(coins + ?, 2) WHERE real_id = ?", (amount, recipient_id))
            conn.commit()

        bot.edit_message_text(f"Перевод завершён! {amount}R успешно переведены.", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
    except Exception: pass
    finally:
        try: bot.answer_callback_query(call.id)
        except Exception: pass



#создать вид
#название
#айди стикера
@bot.message_handler(func=lambda msg: msg.text and msg.text.lower().startswith("создать вид"), imc=True)
def create_mushroom_type(message):
    try:
        lines = [line.strip() for line in message.text.split("\n") if line.strip()]
        if len(lines) < 3:
            bot.reply_to(message, "Ошибка: неверный формат! Должно быть 3 строки.")
            return

        name = lines[1]
        sticker_id = lines[2]

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO MushroomTypes (mr_name, mr_sticker) VALUES (?, ?)",
                (name, sticker_id)
            )
            conn.commit()
            mr_type = cursor.lastrowid

        bot.reply_to(message, f"Новый вид добавлен. Айди: {mr_type}")
    except Exception as e:
        print(f"Ошибка создания вида: {e}")


#см вид [айди]
@bot.message_handler(func=lambda msg: msg.text and msg.text.lower().startswith("см вид "), imc=True)
def view_mushroom_type(message):
    try:
        args = message.text.split()
        if len(args) < 3 or not args[2].isdigit():
            return
            
        mr_type = int(args[2])

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT mr_name, mr_sticker FROM MushroomTypes WHERE type_id = ?", (mr_type,))
            row = cursor.fetchone()

        if not row:
            bot.reply_to(message, "Вид не найден")
            return

        mr_name, mr_sticker = row
        bot.send_sticker(message.chat.id, mr_sticker, reply_to_message_id=message.message_id)
        bot.send_message(message.chat.id, f"Название: {mr_name}\nАйди: {mr_type}")
    except Exception as e:
        print(f"Ошибка просмотра вида: {e}")

TYPES_PER_PAGE = 20

def get_types_list_data(page=1):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM MushroomTypes")
        total_items_row = cursor.fetchone()
        total_items = total_items_row[0] if total_items_row else 0
        
        total_pages = math.ceil(total_items / TYPES_PER_PAGE) if total_items > 0 else 1
        
        if page > total_pages:
            page = total_pages
        if page < 1:
            page = 1
            
        offset = (page - 1) * TYPES_PER_PAGE
        cursor.execute("""
            SELECT type_id, mr_name 
            FROM MushroomTypes 
            ORDER BY type_id ASC 
            LIMIT ? OFFSET ?
        """, (TYPES_PER_PAGE, offset))
        
        types_list = cursor.fetchall()

    text_lines = [f"<b>Всего видов: {total_items}</b>\n"]
    
    for type_id, mr_name in types_list:
        text_lines.append(f"#{type_id} {mr_name}")
        
    text_lines.append(f"\n<b>Стр. {page}/{total_pages}</b>")
    final_text = "\n".join(text_lines)
    
    markup = InlineKeyboardMarkup()
    buttons = []
    
    if total_pages > 1:
        if page > 1:
            buttons.append(InlineKeyboardButton("‹", callback_data=f"types_page:{page-1}"))
        if page < total_pages:
            buttons.append(InlineKeyboardButton("›", callback_data=f"types_page:{page+1}"))
            
        if buttons:
            markup.row(*buttons)
            
    return final_text, markup


#список видов
@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() == "список видов", imc=True)
def show_types_list(message):
    try:
        text, markup = get_types_list_data(page=1)
        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        print(f"Ошибка в списке видов: {e}")

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("types_page:"), imc=True)
def refresh_types_list(call):
    try:
        page = int(call.data.split(":")[1])
        text, markup = get_types_list_data(page)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup
        )
    except Exception:
        pass
    finally:
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass


#редкости
RARE_OPTIONS = ["Обычный", "Элитный", "Легендарный"]
RARE_CHANCES = [80.0, 19.95, 0.05]

def get_price_by_rare(rare):
    if rare == "Обычный":
        return round(random.uniform(0.01, 0.5), 2)
    elif rare == "Элитный":
        return round(random.uniform(0.5, 2.0), 2)
    else:
        return round(random.uniform(2.0, 5.0), 2)


#пик
@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() in ["собирать", "пик", "/pick"], imc=True)
def pick_mushrooms(message):
    try:
        user_id = message.from_user.id
        check(user_id)
        current_time = int(time.time())

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT time FROM Users WHERE real_id = ?", (user_id,))
            user_time = cursor.fetchone()

        if user_time and user_time[0] and current_time < user_time[0]:
            time_left = user_time[0] - current_time
            minutes = time_left // 60
            seconds = time_left % 60
            bot.reply_to(message, f"Не торопись, подожди ещё {minutes} мин. {seconds} сек.")
            return

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT mr_name, mr_sticker FROM MushroomTypes")
            available_types = cursor.fetchall()

        if not available_types:
            bot.reply_to(message, "В лесу ещё нет грибов! Сначала администратор должен создать виды грибов.")
            return

        found_mushrooms = []
        new_cooldown = current_time + 3600

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            for _ in range(3):
                m_type = random.choice(available_types)
                mr_name, mr_sticker = m_type[0], m_type[1]
                
                rare = random.choices(RARE_OPTIONS, weights=RARE_CHANCES, k=1)[0]
                price = get_price_by_rare(rare)
                
                cursor.execute("""
                    INSERT INTO Mushrooms (user_id, mr_name, mr_sticker, mr_rare, mr_price)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, mr_name, mr_sticker, rare, price))
                
                mr_id = cursor.lastrowid
                short_rare = "О" if rare == "Обычный" else ("Э" if rare == "Элитный" else "Л")
                found_mushrooms.append(f"#{mr_id} ({price}R) — [{short_rare}] {mr_name}")

            cursor.execute("""
                UPDATE Users 
                SET time = ?, all_mr = all_mr + 3 
                WHERE real_id = ?
            """, (new_cooldown, user_id))
            conn.commit()

        text_lines = ["Ты прогулялся по лесу и нашёл новые грибы:"]
        text_lines.extend(found_mushrooms)
        text_lines.append("\nПиши «/look [айди] чтобы узнать побольше о грибочке.")
        
        bot.send_message(message.chat.id, "\n".join(text_lines))

    except Exception as e:
        print(f"Ошибка в команде сбора грибов: {e}")



@bot.message_handler(func=lambda msg: msg.text and (msg.text.lower().startswith("/look ") or msg.text.lower().startswith("см ")), imc=True)
def look_mushroom(message):
    try:
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            return

        mr_id = int(args[1])

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.mr_name, m.mr_sticker, m.mr_rare, m.mr_price, u.bot_name, u.real_id
                FROM Mushrooms m
                JOIN Users u ON m.user_id = u.real_id
                WHERE m.mr_id = ?
            """, (mr_id,))
            row = cursor.fetchone()

        if not row:
            bot.reply_to(message, "Гриб не найден")
            return

        mr_name, mr_sticker, mr_rare, mr_price, bot_name, owner_real_id = row
        owner_link = f'<a href="tg://user?id={owner_real_id}">{bot_name}</a>'

        bot.send_sticker(message.chat.id, mr_sticker, reply_to_message_id=message.message_id)
        
        text = (
            f"Название: {mr_name}\n"
            f"Айди: {mr_id}\n"
            f"Редкость: {mr_rare}\n"
            f"Стоимость: {mr_price}\n"
            f"Владелец: {owner_link}"
        )
        
        bot.send_message(message.chat.id, text, parse_mode="HTML")

    except Exception as e:
        print(f"Ошибка в команде просмотра гриба: {e}")



@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() in ["гтоп", "/gtop"], imc=True)
def show_gtop_menu(message):
    try:
        check(message.from_user.id)
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("Грибы", callback_data="gtop:mushrooms"),
            InlineKeyboardButton("Победы", callback_data="gtop:wins"),
            InlineKeyboardButton("Валюта", callback_data="gtop:coins")
        )
        bot.reply_to(message, "Выберите топ", reply_markup=markup)
    except Exception as e:
        print(f"Ошибка меню топа: {e}")

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("gtop:"), imc=True)
def process_gtop_callback(call):
    try:
        top_type = call.data.split(":")[1]
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            if top_type == "mushrooms":
                title = "Топ-10 лучших собирателей:"
                cursor.execute("SELECT real_id, bot_name, all_mr FROM Users ORDER BY all_mr DESC LIMIT 10")
                rows = cursor.fetchall()
                lines = [f"{i+1}. <a href='tg://user?id={r[0]}'>{r[1]}</a> — {r[2]}" for i, r in enumerate(rows)]
            elif top_type == "wins":
                title = "Топ-10 лучших победителей:"
                cursor.execute("SELECT real_id, bot_name, wins FROM Users ORDER BY wins DESC LIMIT 10")
                rows = cursor.fetchall()
                lines = [f"{i+1}. <a href='tg://user?id={r[0]}'>{r[1]}</a> — {r[2]}" for i, r in enumerate(rows)]
            else:
                title = "Топ-10 лучших богачей:"
                cursor.execute("SELECT real_id, bot_name, coins FROM Users ORDER BY coins DESC LIMIT 10")
                rows = cursor.fetchall()
                lines = [f"{i+1}. <a href='tg://user?id={r[0]}'>{r[1]}</a> — {r[2]}R" for i, r in enumerate(rows)]

        final_text = f"<b>{title}</b>\n" + "\n".join(lines)
        bot.edit_message_text(final_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=None)
    except Exception: pass
    finally:
        try: bot.answer_callback_query(call.id)
        except Exception: pass



# 1. ТЕКСТОВЫЙ ОБРАБОТЧИК: СОЗДАНИЕ ДУЭЛИ (сообщение игрока)
@bot.message_handler(func=lambda msg: msg.text and (msg.text.lower().startswith("дуэль") or msg.text.lower().startswith("/duel")), imc=True)
def create_duel_cmd(message):
    try:
        user_id = message.from_user.id
        check(user_id)
        
        args = message.text.split()
        stake = 0.0
        
        if len(args) > 1:
            clean_stake = args[1].lower().replace("r", "").replace("р", "")
            try:
                stake = round(float(clean_stake), 2)
            except ValueError:
                return
            
            if stake < 0: 
                return
            
            if stake > 0:
                with sqlite3.connect(DB_PATH) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT coins FROM Users WHERE real_id = ?", (user_id,))
                    res_row = cursor.fetchone()
                    res = res_row[0] if res_row else 0.0
                    if res < stake:
                        bot.reply_to(message, "Недостаточно средств")
                        return

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Сразиться", callback_data=f"duel_join:{user_id}:{stake}"))
        
        text = "Ждём соперника" if stake == 0 else f"Ждём соперника\nСтавка: {stake}R"
        bot.reply_to(message, text, reply_markup=markup)
    except Exception as e:
        print(f"Ошибка создания дуэли: {e}")


# 2. ПЕРВЫЙ CALLBACK: ПРИНЯТИЕ ДУЭЛИ СЛЕДУЮЩИМ ИГРОКОМ
@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("duel_join:"), imc=True)
def join_duel_callback(call):
    try:
        data_parts = call.data.split(":")
        p1_id = int(data_parts[1])
        stake = float(data_parts[2])
        p2_id = call.from_user.id
        check(p2_id)

        if p2_id == p1_id:
            try: 
                bot.answer_callback_query(call.id, text="Нельзя биться с самим собой", show_alert=True)
            except Exception: pass
            return

        if stake > 0:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT coins FROM Users WHERE real_id = ?", (p2_id,))
                res2_row = cursor.fetchone()
                res2 = res2_row[0] if res2_row else 0.0
                
                cursor.execute("SELECT coins FROM Users WHERE real_id = ?", (p1_id,))
                res1_row = cursor.fetchone()
                res1 = res1_row[0] if res1_row else 0.0
                
                if res2 < stake or res1 < stake:
                    try: 
                        bot.answer_callback_query(call.id, text="Недостаточно средств", show_alert=True)
                    except Exception: pass
                    return

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT bot_name FROM Users WHERE real_id = ?", (p1_id,))
            p1_row = cursor.fetchone()
            p1_name = p1_row[0] if p1_row else "-"
            
            cursor.execute("SELECT bot_name FROM Users WHERE real_id = ?", (p2_id,))
            p2_row = cursor.fetchone()
            p2_name = p2_row[0] if p2_row else "-"

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("Камень", callback_data=f"duel_play:{p1_id}:{p2_id}:{stake}:-:К"),
            InlineKeyboardButton("Ножницы", callback_data=f"duel_play:{p1_id}:{p2_id}:{stake}:-:Н"),
            InlineKeyboardButton("Бумага", callback_data=f"duel_play:{p1_id}:{p2_id}:{stake}:-:Б")
        )

        p1_link = f'<a href="tg://user?id={p1_id}">{p1_name}</a>'
        p2_link = f'<a href="tg://user?id={p2_id}">{p2_name}</a>'
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception: pass
        
        bot.send_message(call.message.chat.id, f"{p1_link} VS {p2_link}", parse_mode="HTML", reply_markup=markup)
    except Exception: pass
    finally:
        try: bot.answer_callback_query(call.id)
        except Exception: pass



@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("duel_play:"), imc=True)
def play_duel_callback(call):
    try:
        data_parts = call.data.split(":")
        p1_id = int(data_parts[1])
        p2_id = int(data_parts[2])
        stake = float(data_parts[3])
        p1_choice = data_parts[4]
        p2_choice = data_parts[5]
        
        clicker_id = call.from_user.id
        
        if clicker_id != p1_id and clicker_id != p2_id:
            try: 
                bot.answer_callback_query(call.id, text="Это не твой бой", show_alert=True)
            except Exception: pass
            return

        current_choice = p2_choice
        
        if clicker_id == p1_id:
            if p1_choice != "-":
                choice_word = "Камень" if p1_choice == "К" else ("Ножницы" if p1_choice == "Н" else "Бумагу")
                try: 
                    bot.answer_callback_query(call.id, text=f"Ты уже выбрал {choice_word}, жди выбор соперника", show_alert=True)
                except Exception: pass
                return
            p1_choice = current_choice
            p2_choice = data_parts[4] if data_parts[4] != "-" else "-"
        else:
            p1_choice_saved = data_parts[4]
            if p1_choice_saved != "-":
                p1_choice = p1_choice_saved
                p2_choice = current_choice
            else:
                if p2_choice != "-":
                    choice_word = "Камень" if p2_choice == "К" else ("Ножницы" if p2_choice == "Н" else "Бумагу")
                    try: 
                        bot.answer_callback_query(call.id, text=f"Ты уже выбрал {choice_word}, жди выбор соперника", show_alert=True)
                    except Exception: pass
                    return
                p1_choice = "-"
                p2_choice = current_choice

        choice_name = "Камень" if current_choice == "К" else ("Ножницы" if current_choice == "Н" else "Бумагу")
        
        if p1_choice != "-" and p2_choice != "-":
            try: 
                bot.answer_callback_query(call.id, text=f"Ты выбрал {choice_name}", show_alert=True)
            except Exception: pass
            
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT bot_name FROM Users WHERE real_id = ?", (p1_id,))
                p1_row = cursor.fetchone()
                p1_name = p1_row[0] if p1_row else "-"
                
                cursor.execute("SELECT bot_name FROM Users WHERE real_id = ?", (p2_id,))
                p2_row = cursor.fetchone()
                p2_name = p2_row[0] if p2_row else "-"

            p1_link = f'<a href="tg://user?id={p1_id}">{p1_name}</a>'
            p2_link = f'<a href="tg://user?id={p2_id}">{p2_name}</a>'
            
            full_words = {"К": "Камень", "Н": "Ножницы", "Б": "Бумага"}
            w1, w2 = full_words[p1_choice], full_words[p2_choice]

            if p1_choice == p2_choice:
                try: bot.delete_message(call.message.chat.id, call.message.message_id)
                except Exception: pass
                text = f"Ничья: {p1_link} и {p2_link} выбрали {w1}."
                if stake > 0: 
                    text += f"\n\nСтавка: {stake}R"
                bot.send_message(call.message.chat.id, text, parse_mode="HTML")
                return

            p1_wins = (p1_choice == "К" and p2_choice == "Н") or (p1_choice == "Н" and p2_choice == "Б") or (p1_choice == "Б" and p2_choice == "К")
            
            winner_id, winner_link, loser_id, loser_link = (p1_id, p1_link, p2_id, p2_link) if p1_wins else (p2_id, p2_link, p1_id, p1_link)

            if stake > 0:
                with sqlite3.connect(DB_PATH) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT coins FROM Users WHERE real_id = ?", (loser_id,))
                    l_coins_row = cursor.fetchone()
                    l_coins = l_coins_row[0] if l_coins_row else 0.0
                    
                    cursor.execute("SELECT coins FROM Users WHERE real_id = ?", (winner_id,))
                    w_coins_row = cursor.fetchone()
                    w_coins = w_coins_row[0] if w_coins_row else 0.0
                    
                    if l_coins >= stake and w_coins >= stake:
                        cursor.execute("UPDATE Users SET coins = round(coins - ?, 2) WHERE real_id = ?", (stake, loser_id))
                        cursor.execute("UPDATE Users SET coins = round(coins + ?, 2), wins = wins + 1 WHERE real_id = ?", (stake, winner_id))
                        conn.commit()
                    else:
                        try: bot.delete_message(call.message.chat.id, call.message.message_id)
                        except Exception: pass
                        bot.send_message(call.message.chat.id, "Матч аннулирован: у одного из игроков испарились средства во время боя.")
                        return
            else:
                with sqlite3.connect(DB_PATH) as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE Users SET wins = wins + 1 WHERE real_id = ?", (winner_id,))
                    conn.commit()

            try: bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception: pass
            
            text = (
                f"{w1} VS {w2}\n"
                f"Победитель — {winner_link}\n"
                f"Проигравший — {loser_link}"
            )
            if stake > 0: 
                text += f"\n\nСтавка: {stake}R"
            bot.send_message(call.message.chat.id, text, parse_mode="HTML")
            return

        try: 
            bot.answer_callback_query(call.id, text=f"Ты выбрал {choice_name}", show_alert=True)
        except Exception: pass
        
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("Камень", callback_data=f"duel_play:{p1_id}:{p2_id}:{stake}:{p1_choice}:К"),
            InlineKeyboardButton("Ножницы", callback_data=f"duel_play:{p1_id}:{p2_id}:{stake}:{p1_choice}:Н"),
            InlineKeyboardButton("Бумага", callback_data=f"duel_play:{p1_id}:{p2_id}:{stake}:{p1_choice}:Б")
        )
        
        try:
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
        except Exception: pass

    except Exception as e:
        print(f"Ошибка логики дуэли: {e}")



@bot.message_handler(func=lambda msg: msg.text and msg.text.lower().startswith("создать валюту "), imc=True)
def admin_add_coins(message):
    try:
        user_id = message.from_user.id
        check(user_id)
        
        args = message.text.split()
        if len(args) < 3:
            return
            
        try:
            amount = round(float(args[2]), 2)
        except ValueError:
            return
            
        if amount <= 0:
            return

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET coins = round(coins + ?, 2) WHERE real_id = ?", (amount, user_id))
            conn.commit()

        bot.reply_to(message, f"✅ Баланс успешно пополнен на {amount}R")
    except Exception as e:
        print(f"Ошибка админ-выдачи валюты: {e}")



@bot.message_handler(func=lambda msg: msg.text and msg.text.lower().startswith("удалить валюту "), imc=True)
def admin_remove_coins(message):
    try:
        user_id = message.from_user.id
        check(user_id)
        
        args = message.text.split()
        if len(args) < 3:
            return
            
        try:
            amount = round(float(args[2]), 2)
        except ValueError:
            return
            
        if amount <= 0:
            return

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT coins FROM Users WHERE real_id = ?", (user_id,))
            current_coins_row = cursor.fetchone()
            current_coins = current_coins_row[0] if current_coins_row else 0.0

            if current_coins - amount < 0:
                bot.reply_to(message, "Минусовой баланс запрещён")
                return

            cursor.execute("UPDATE Users SET coins = round(coins - ?, 2) WHERE real_id = ?", (amount, user_id))
            conn.commit()

        bot.reply_to(message, f"📉 С баланса успешно списано {amount}R")
    except Exception as e:
        print(f"Ошибка админ-списания валюты: {e}")



@bot.message_handler(func=lambda msg: msg.text and msg.text.lower().startswith("создать гриб"), imc=True)
def admin_create_mushroom(message):
    try:
        user_id = message.from_user.id
        lines = [line.strip() for line in message.text.split("\n") if line.strip()]
        if len(lines) < 5:
            bot.reply_to(message, "Ошибка: неверный формат! Должно быть 5 строк.")
            return

        type_id = int(lines[1])
        mr_id = int(lines[2])
        short_rare = lines[3].upper()
        price = round(float(lines[4]), 2)

        rare_mapping = {"О": "Обычный", "Э": "Элитный", "Л": "Легендарный"}
        if short_rare not in rare_mapping:
            bot.reply_to(message, "Ошибка: редкость должна быть О, Э или Л.")
            return
        full_rare = rare_mapping[short_rare]

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT mr_name, mr_sticker FROM MushroomTypes WHERE type_id = ?", (type_id,))
            type_row = cursor.fetchone()
            if not type_row:
                bot.reply_to(message, "Вид не найден")
                return
            mr_name, mr_sticker = type_row

            cursor.execute("SELECT 1 FROM Mushrooms WHERE mr_id = ?", (mr_id,))
            if cursor.fetchone():
                bot.reply_to(message, "Айди гриба занят")
                return

            cursor.execute("""
                INSERT INTO Mushrooms (mr_id, user_id, mr_name, mr_sticker, mr_rare, mr_price)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (mr_id, user_id, mr_name, mr_sticker, full_rare, price))
            
            cursor.execute("UPDATE Users SET all_mr = all_mr + 1 WHERE real_id = ?", (user_id,))
            conn.commit()

        bot.reply_to(message, f"✅ Гриб #{mr_id} успешно создан и добавлен в ваш инвентарь!")
    except Exception as e:
        print(f"Ошибка админ-создания гриба: {e}")



# 1. КОМАНДА СМЕНЫ ИМЕНИ (имя, /name)
@bot.message_handler(func=lambda msg: msg.text and (msg.text.lower().startswith("имя ") or msg.text.lower().startswith("/name ")), imc=True)
def change_bot_name(message):
    try:
        user_id = message.from_user.id
        check(user_id)
        
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            return
            
        new_name = args[1].strip()
        
        # Если игрок находится в списке CHATS, мы полностью пропускаем любые проверки
        if user_id not in CHATS:
            # Проверка длины: не менее 3 и не более 30 символов
            if len(new_name) < 3 or len(new_name) > 30:
                bot.reply_to(message, "Длина имени должна быть от 3 до 30 символов!")
                return
                
            # Проверка символов: только русский, английский, цифры и пробелы
            if not re.match(r"^[a-zA-Zа-яА-ЯёЁ0-9 ]+$", new_name):
                bot.reply_to(message, "Имя содержит запрещённые символы")
                return

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET bot_name = ? WHERE real_id = ?", (new_name, user_id))
            conn.commit()

        bot.reply_to(message, f"Ваше игровое имя успешно изменено на: {new_name}")
    except Exception as e:
        print(f"Ошибка смены имени: {e}")



# 2. КОМАНДА ИНФОРМАЦИИ (инфо, /info)
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