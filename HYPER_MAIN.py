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
DB_PATH = "data/very_db.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            real_id INTEGER NOT NULL,
            bot_name TEXT NOT NULL DEFAULT "",
            coins INTEGER DEFAULT 0,
            eat INTEGER DEFAULT 0,
            time_kd INTEGER DEFAULT 0,
            food INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS FoodTypes (
            food_type INTEGER PRIMARY KEY AUTOINCREMENT,
            food_sticker TEXT NOT NULL,
            food_name TEXT NOT NULL
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Inventory (
            food_id INTEGER PRIMARY KEY AUTOINCREMENT,
            real_id INTEGER NOT NULL,
            food_type INTEGER NOT NULL,
            food_price INTEGER NOT NULL,
            food_points INTEGER NOT NULL,
            FOREIGN KEY (food_type) REFERENCES FoodTypes(food_type)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Shop (
            food_type INTEGER UNIQUE,
            price INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (food_type) REFERENCES FoodTypes(food_type)
        )
        """)
        conn.commit()



def check(id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM Users WHERE real_id = ?", (id,))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO Users (real_id) VALUES (?)", (id,))
            conn.commit()



def check_and_update_shop():
    now_ts = time.time() + 3 * 3600
    struct_time = time.gmtime(now_ts)
    
    current_day_start = now_ts - (struct_time.tm_hour * 3600 + struct_time.tm_min * 60 + struct_time.tm_sec)
    next_day_start = current_day_start + 86400
    
    rem = int(next_day_start - now_ts)
    hours = rem // 3600
    mins = (rem % 3600) // 60
    secs = rem % 60
    time_str = f"{hours} ч. {mins} мин. {secs} сек."
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM Shop")
        has_items = c.fetchone()[0] > 0
        
        c.execute("SELECT COUNT(*) FROM FoodTypes")
        total_types = c.fetchone()[0]
        
        if total_types < 5:
            return time_str, False
            
        try:
            with open("data/shop_date.txt", "r") as f:
                last_update_day = int(f.read().strip())
        except:
            last_update_day = 0
            
        current_day_number = struct_time.tm_yday + (struct_time.tm_year * 366)
        
        if current_day_number != last_update_day or not has_items:
            c.execute("DELETE FROM Shop")
            c.execute("SELECT food_type FROM FoodTypes")
            all_types = [r[0] for r in c.fetchall()]
            
            shop_types = random.sample(all_types, 5)
            for f_type in shop_types:
                price = random.randint(5, 50)
                c.execute("INSERT OR REPLACE INTO Shop (food_type, price, quantity) VALUES (?, ?, 5)", (f_type, price))
            conn.commit()
            
            with open("data/shop_date.txt", "w") as f:
                f.write(str(current_day_number))
                
    return time_str, True



@bot.message_handler(func=lambda message: message.text and message.text.lower() in ["магазин", "магаз"], imc=True)
def shop_cmd(message):
    time_str, success = check_and_update_shop()
    if not success:
        bot.send_message(message.chat.id, "В базе данных должно быть минимум 5 видов еды, чтобы открыть магазин")
        return
        
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT s.quantity, t.food_name, s.price
            FROM Shop s
            JOIN FoodTypes t ON s.food_type = t.food_type
            ORDER BY s.food_type ASC
        """)
        rows = c.fetchall()
        
    lines = []
    for i, (qty, fname, price) in enumerate(rows, 1):
        lines.append(f"{i}. {qty}/5 <b>{fname}</b>\n• Цена: {price} Ж")
        
    txt = "<b>🏪Магазин с продуктами</b>\nПокупка: купить [номер]\n\n" + "\n\n".join(lines) + f"\n\n⏳Магазин обновится через:\n{time_str}"
    bot.send_message(message.chat.id, txt, parse_mode="HTML")



@bot.message_handler(func=lambda message: message.text and message.text.lower().split()[0] == "купить", imc=True)
def buy_food_cmd(message):
    uid = message.from_user.id
    tokens = message.text.split()
    if len(tokens) < 2 or not tokens[1].isdigit():
        return
    idx = int(tokens[1])
    if idx < 1 or idx > 5:
        bot.send_message(message.chat.id, "Неверный номер товара. Выберите от 1 до 5")
        return
        
    check(uid)
    time_str, success = check_and_update_shop()
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT coins FROM Users WHERE real_id = ?", (uid,))
        user_coins = c.fetchone()[0]
        if user_coins < 0:
            bot.send_message(message.chat.id, "Недостаточно средств")
            return
            
        c.execute("""
            SELECT s.food_type, s.price, s.quantity, t.food_name 
            FROM Shop s 
            JOIN FoodTypes t ON s.food_type = t.food_type 
            ORDER BY s.food_type ASC
        """)
        items = c.fetchall()
        
    if idx > len(items):
        bot.send_message(message.chat.id, "Товар не найден")
        return
        
    ftype, price, qty, fname = items[idx - 1]
    
    if qty <= 0:
        bot.send_message(message.chat.id, "Данного продукта не осталось в наличии")
        return
    if user_coins < price:
        bot.send_message(message.chat.id, "Недостаточно средств")
        return
        
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("✅Подтвердить", callback_data=f"buyshop_{uid}_{message.message_id}_{ftype}_{price}"))
    bot.send_message(message.chat.id, f"Вы уверены, что хотите купить <b>{fname}</b> за {price} Ж?", reply_markup=kb, parse_mode="HTML")



@bot.callback_query_handler(func=lambda call: call.data.startswith("buyshop_"))
def buy_food_callback(call):
    _, owner_id, msg_id, ftype, price = call.data.split("_")
    owner_id, msg_id, ftype, price = int(owner_id), int(msg_id), int(ftype), int(price)
    
    if call.from_user.id != owner_id:
        bot.answer_callback_query(call.id, "Это не твое меню!", show_alert=True)
        return
    if msg_id in LOCKS:
        bot.answer_callback_query(call.id)
        return
    LOCKS[msg_id] = True
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT coins, bot_id, bot_name FROM Users WHERE real_id = ?", (owner_id,))
        coins, bid, name = c.fetchone()
        
        if coins < price:
            bot.edit_message_text("Недостаточно средств", call.message.chat.id, call.message.message_id, reply_markup=None)
            del LOCKS[msg_id]
            return
            
        c.execute("SELECT quantity FROM Shop WHERE food_type = ?", (ftype,))
        shop_res = c.fetchone()
        if not shop_res or shop_res[0] <= 0:
            bot.edit_message_text("Данного продукта не осталось в наличии", call.message.chat.id, call.message.message_id, reply_markup=None)
            del LOCKS[msg_id]
            return
            
        c.execute("SELECT food_name FROM FoodTypes WHERE food_type = ?", (ftype,))
        fname = c.fetchone()[0]
        
        points = random.randint(1, 5)
        
        c.execute("UPDATE Shop SET quantity = quantity - 1 WHERE food_type = ?", (ftype,))
        c.execute("UPDATE Users SET coins = coins - ?, food = food + 1 WHERE real_id = ?", (price, owner_id))
        c.execute("INSERT INTO Inventory (real_id, food_type, food_price, food_points) VALUES (?, ?, ?, ?)", (owner_id, ftype, price, points))
        conn.commit()
        
    disp = name if name else f"#{bid}"
    link = f'<a href="tg://user?id={owner_id}">{disp}</a>'
    bot.edit_message_text(f"🔖{link} купил <b>{fname}</b> за {price} Ж", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=None)
    del LOCKS[msg_id]



@bot.message_handler(func=lambda message: message.text and message.text.lower().split()[0] in ["баланс", "б"], imc=True)
def balance_cmd(message):
    uid = message.from_user.id
    tokens = message.text.split(maxsplit=1)
    arg = tokens[1] if len(tokens) > 1 else None
    
    if message.reply_to_message and not arg:
        uid = message.reply_to_message.from_user.id
        if message.reply_to_message.from_user.is_bot:
            bot.send_message(message.chat.id, "Пользователь не найден")
            return

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        if arg:
            if arg.isdigit():
                c.execute("SELECT real_id, bot_id, bot_name, coins, food, eat FROM Users WHERE bot_id = ?", (int(arg),))
            else:
                c.execute("SELECT real_id, bot_id, bot_name, coins, food, eat FROM Users WHERE bot_name = ?", (arg,))
        else:
            check(uid)
            c.execute("SELECT real_id, bot_id, bot_name, coins, food, eat FROM Users WHERE real_id = ?", (uid,))
        res = c.fetchone()
        
    if not res:
        bot.send_message(message.chat.id, "Пользователь не найден")
        return
        
    t_uid, bid, name, coins, food, eat = res
    link = f'<a href="tg://user?id={t_uid}">#{bid}</a>'
    head = f"👤{link}, <b>{name}</b>\n\n" if name else f"👤{link}\n\n"
    txt = f"{head}💰Жетонов: {coins} Ж\n🍭Еды: {food} шт.\n✨Очков сытости: {eat} ОС"
    bot.send_message(message.chat.id, txt, parse_mode="HTML")



@bot.message_handler(func=lambda message: message.text and message.text.lower() in ["лидер", "лидеры"], imc=True)
def leaders_cmd(message):
    uid = message.from_user.id
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("💰", callback_data=f"top_coins_{uid}_{message.message_id}"),
        InlineKeyboardButton("🍭", callback_data=f"top_food_{uid}_{message.message_id}"),
        InlineKeyboardButton("✨", callback_data=f"top_eat_{uid}_{message.message_id}")
    )
    bot.send_message(message.chat.id, "Выберите топ", reply_markup=kb)



@bot.callback_query_handler(func=lambda call: call.data.startswith("top_"))
def leaders_callback(call):
    mode, cfg_name, owner_id, msg_id = call.data.split("_")
    owner_id, msg_id = int(owner_id), int(msg_id)
    if call.from_user.id != owner_id:
        bot.answer_callback_query(call.id, "Это не твое меню!", show_alert=True)
        return
    if msg_id in LOCKS:
        bot.answer_callback_query(call.id)
        return
    LOCKS[msg_id] = True
    
    cfg_field = {"coins": "coins", "food": "food", "eat": "eat"}[cfg_name]
    cfg_title = {"coins": "жетонам", "food": "кол-ву еды", "eat": "очкам сытости"}[cfg_name]
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(f"SELECT real_id, bot_id, bot_name, {cfg_field} FROM Users ORDER BY {cfg_field} DESC LIMIT 15")
        rows = c.fetchall()
    lines = []
    for i, (rid, bid, name, val) in enumerate(rows, 1):
        disp = name if name else f"#{bid}"
        link = f'<a href="tg://user?id={rid}">{disp}</a>'
        lines.append(f"{i}. {link} — {val}")
    text = f"<b>👑Топ-15 лидеров по {cfg_title}</b>\n\n" + "\n".join(lines)
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=None)
    del LOCKS[msg_id]



@bot.message_handler(func=lambda message: message.text and message.from_user.id in CHATS and message.text.lower().split()[0] in ["+вж", "+вос"], imc=True)
def admin_give_res_cmd(message):
    uid = message.from_user.id
    tokens = message.text.split()
    if len(tokens) < 2 or not tokens[1].isdigit():
        return
    val = int(tokens[1])
    cmd = tokens[0].lower()
    field = "coins" if cmd == "+вж" else "eat"
    res_name = "жетонов" if cmd == "+вж" else "очков сытости"
    check(uid)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(f"UPDATE Users SET {field} = {field} + ? WHERE real_id = ?", (val, uid))
        conn.commit()
    bot.send_message(message.chat.id, f"Вы выдали себе {val} {res_name}")



@bot.message_handler(func=lambda message: message.text and message.text.lower().split()[0] in ["+имя", "++имя"], imc=True)
def change_name_cmd(message):
    uid = message.from_user.id
    tokens = message.text.split(maxsplit=1)
    if len(tokens) < 2:
        return
    name = tokens[1].strip()
    cmd = tokens[0].lower()
    check(uid)
    if cmd == "++имя":
        if uid not in CHATS:
            return
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("UPDATE Users SET bot_name = ? WHERE real_id = ?", (name, uid))
            c.execute("SELECT bot_id FROM Users WHERE real_id = ?", (uid,))
            bid = c.fetchone()[0]
            conn.commit()
        link = f'<a href="tg://user?id={uid}">#{bid}</a>'
        bot.send_message(message.chat.id, f"🏷️{link} купил себе имя <b>{name}</b>", parse_mode="HTML")
        return
    if not re.match(r"^[а-яА-ЯёЁ0-9\s]{3,10}$", name):
        bot.send_message(message.chat.id, "Имена поддерживают только русский алфавит, цифры и длину в 3-10 символов")
        return
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT coins FROM Users WHERE real_id = ?", (uid,))
        if c.fetchone()[0] < 1000:
            bot.send_message(message.chat.id, "Недостаточно средств")
            return
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("✅Подтвердить", callback_data=f"setname_{uid}_{message.message_id}_{name[:20]}"))
    bot.send_message(message.chat.id, f"Вы уверены что хотите сменить своё имя на <b>{name}</b> за 1000 Ж?", reply_markup=kb, parse_mode="HTML")



@bot.callback_query_handler(func=lambda call: call.data.startswith("setname_"))
def change_name_callback(call):
    _, owner_id, msg_id, name = call.data.split("_", 3)
    owner_id, msg_id = int(owner_id), int(msg_id)
    if call.from_user.id != owner_id:
        bot.answer_callback_query(call.id, "Это не твое меню!", show_alert=True)
        return
    if msg_id in LOCKS:
        bot.answer_callback_query(call.id)
        return
    LOCKS[msg_id] = True
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT coins, bot_id FROM Users WHERE real_id = ?", (owner_id,))
        coins, bid = c.fetchone()
        if coins < 1000:
            bot.edit_message_text("Недостаточно средств", call.message.chat.id, call.message.message_id, reply_markup=None)
            del LOCKS[msg_id]
            return
        c.execute("UPDATE Users SET coins = coins - 1000, bot_name = ? WHERE real_id = ?", (name, owner_id))
        conn.commit()
    link = f'<a href="tg://user?id={owner_id}">#{bid}</a>'
    bot.edit_message_text(f"🏷️{link} купил себе имя <b>{name}</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=None)
    del LOCKS[msg_id]



@bot.message_handler(func=lambda message: message.text and message.from_user.id in CHATS and message.text.lower().split()[0] in ["+вид", "+еда"], imc=True)
def admin_food_manage_cmd(message):
    uid = message.from_user.id
    lines = message.text.split("\n")
    first_line_tokens = lines[0].split(maxsplit=1)
    cmd = first_line_tokens[0].lower()
    check(uid)
    if cmd == "+вид" and len(lines) == 2 and len(first_line_tokens) == 2:
        name = first_line_tokens[1].strip()
        sticker = lines[1].strip()
        if not name or not sticker:
            return
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO FoodTypes (food_sticker, food_name) VALUES (?, ?)", (sticker, name))
            ftype_id = c.lastrowid
            conn.commit()
        bot.send_message(message.chat.id, f"Новый вид создан. Айди: {ftype_id}")
    elif cmd == "+еда" and len(lines) == 3 and len(first_line_tokens) == 2:
        if not first_line_tokens[1].isdigit() or not lines[1].strip().isdigit() or not lines[2].strip().isdigit():
            return
        ftype = int(first_line_tokens[1])
        price = int(lines[1].strip())
        points = int(lines[2].strip())
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM FoodTypes WHERE food_type = ?", (ftype,))
            if not c.fetchone():
                return
            c.execute("INSERT INTO Inventory (real_id, food_type, food_price, food_points) VALUES (?, ?, ?, ?)", (uid, ftype, price, points))
            food_id = c.lastrowid
            c.execute("UPDATE Users SET food = food + 1 WHERE real_id = ?", (uid,))
            conn.commit()
        bot.send_message(message.chat.id, f"Еда #{food_id} создана")



def get_inv_page(uid, target_uid, page, msg_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT bot_id, bot_name, food FROM Users WHERE real_id = ?", (target_uid,))
        res_user = c.fetchone()
        if not res_user:
            return "Пользователь не найден", None
        bid, name, total_food = res_user
        c.execute("""
            SELECT i.food_id, t.food_name 
            FROM Inventory i 
            JOIN FoodTypes t ON i.food_type = t.food_type 
            WHERE i.real_id = ? 
            ORDER BY i.food_id ASC
        """, (target_uid,))
        items = c.fetchall()
    pages_cnt = max(1, math.ceil(len(items) / 30))
    if page < 1: page = 1
    if page > pages_cnt: page = pages_cnt
    disp = name if name else f"#{bid}"
    link = f'<a href="tg://user?id={target_uid}">{disp}</a>'
    text = f"<b>📋Инвентарь {link}</b>\n\n"
    start = (page - 1) * 30
    end = start + 30
    for i, (f_id, f_name) in enumerate(items[start:end], start + 1):
        text += f"{i}. #{f_id} {f_name}\n"
    text += f"\nВсего еды: {total_food} шт.\nСтр. {page}/{pages_cnt}"
    if pages_cnt == 1:
        return text, None
    kb = InlineKeyboardMarkup()
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅️", callback_data=f"inv_{uid}_{target_uid}_{page-1}_{msg_id}"))
    if page < pages_cnt:
        buttons.append(InlineKeyboardButton("➡️", callback_data=f"inv_{uid}_{target_uid}_{page+1}_{msg_id}"))
    kb.row(*buttons)
    return text, kb



@bot.message_handler(func=lambda message: message.text and message.text.lower().split()[0] in ["инвентарь", "инв"], imc=True)
def inventory_cmd(message):
    uid = message.from_user.id
    tokens = message.text.split(maxsplit=1)
    arg = tokens[1] if len(tokens) > 1 else None
    target_uid = uid
    if message.reply_to_message and not arg:
        target_uid = message.reply_to_message.from_user.id
    elif arg:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            if arg.isdigit():
                c.execute("SELECT real_id FROM Users WHERE bot_id = ?", (int(arg),))
            else:
                c.execute("SELECT real_id FROM Users WHERE bot_name = ?", (arg,))
            res = c.fetchone()
        if not res:
            bot.send_message(message.chat.id, "Пользователь не найден")
            return
        target_uid = res[0]
    check(target_uid)
    text, kb = get_inv_page(uid, target_uid, 1, message.message_id)
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=kb)



@bot.callback_query_handler(func=lambda call: call.data.startswith("inv_"))
def inventory_callback(call):
    _, owner_id, target_uid, page, msg_id = call.data.split("_")
    owner_id, target_uid, page, msg_id = int(owner_id), int(target_uid), int(page), int(msg_id)
    if call.from_user.id != owner_id:
        bot.answer_callback_query(call.id, "Это не твое меню!", show_alert=True)
        return
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM Inventory WHERE real_id = ?", (target_uid,))
        items_cnt = c.fetchone()[0]
    pages_cnt = max(1, math.ceil(items_cnt / 30))
    if page < 1 or page > pages_cnt:
        bot.answer_callback_query(call.id)
        return
    if msg_id in LOCKS:
        bot.answer_callback_query(call.id)
        return
    LOCKS[msg_id] = True
    text, kb = get_inv_page(owner_id, target_uid, page, msg_id)
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=kb)
    del LOCKS[msg_id]



@bot.message_handler(func=lambda message: message.text and message.text.lower().startswith("продать "), imc=True)
def sell_food_cmd(message):
    uid = message.from_user.id
    tokens = message.text.split()
    if len(tokens) < 2 or not tokens[1].isdigit():
        return
    fid = int(tokens[1])
    check(uid)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT food_price FROM Inventory WHERE food_id = ? AND real_id = ?", (fid, uid))
        res = c.fetchone()
    if not res:
        bot.send_message(message.chat.id, "Данный продукт не существует или не принадлежит вам")
        return
    price = res[0]
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("✅Подтвердить", callback_data=f"sell_{uid}_{message.message_id}_{fid}_{price}"))
    bot.send_message(message.chat.id, f"Вы уверены, что хотите продать #{fid} за {price} Ж?", reply_markup=kb)



@bot.callback_query_handler(func=lambda call: call.data.startswith("sell_"))
def sell_food_callback(call):
    _, owner_id, msg_id, fid, price = call.data.split("_")
    owner_id, msg_id, fid, price = int(owner_id), int(msg_id), int(fid), int(price)
    if call.from_user.id != owner_id:
        bot.answer_callback_query(call.id, "Это не твое меню!", show_alert=True)
        return
    if msg_id in LOCKS:
        bot.answer_callback_query(call.id)
        return
    LOCKS[msg_id] = True
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM Inventory WHERE food_id = ? AND real_id = ?", (fid, owner_id))
        if not c.fetchone():
            bot.edit_message_text("Данный продукт не существует или не принадлежит вам", call.message.chat.id, call.message.message_id, reply_markup=None)
            del LOCKS[msg_id]
            return
        c.execute("DELETE FROM Inventory WHERE food_id = ?", (fid,))
        c.execute("UPDATE Users SET coins = coins + ?, food = max(0, food - 1) WHERE real_id = ?", (price, owner_id))
        conn.commit()
    bot.edit_message_text(f"Продукт #{fid} был продан за {price} Ж", call.message.chat.id, call.message.message_id, reply_markup=None)
    del LOCKS[msg_id]



@bot.message_handler(func=lambda message: message.text and message.text.lower() == "еда", imc=True)
def get_food_cmd(message):
    uid = message.from_user.id
    check(uid)
    now = int(time.time())
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT time_kd, bot_id, bot_name FROM Users WHERE real_id = ?", (uid,))
        kd, bid, name = c.fetchone()
        if now < kd:
            rem = kd - now
            hours = rem // 3600
            mins = (rem % 3600) // 60
            secs = rem % 60
            time_str = f"{hours} ч. {mins} мин. {secs} сек." if hours > 0 else f"{mins} мин. {secs} сек."
            bot.send_message(message.chat.id, f"⏳Не спеши! Подожди ещё:\n{time_str}")
            return
        c.execute("SELECT food_type, food_name FROM FoodTypes")
        all_types = c.fetchall()
        if not all_types:
            return
        
        lines = []
        for _ in range(3):
            ftype, fname = random.choice(all_types)
            price = random.randint(5, 50)
            points = random.randint(1, 5)
            c.execute("INSERT INTO Inventory (real_id, food_type, food_price, food_points) VALUES (?, ?, ?, ?)", (uid, ftype, price, points))
            fid = c.lastrowid
            lines.append(f"🆔 {fid}. <b>{fname}</b>")
            
        c.execute("UPDATE Users SET food = food + 3, time_kd = ? WHERE real_id = ?", (now + 5400, uid))
        conn.commit()
        
    disp = name if name else f"#{bid}"
    link = f'<a href="tg://user?id={uid}">{disp}</a>'
    txt = f"🤲{link}, Высшие Силы даровали вам:\n" + "\n".join(lines)
    bot.send_message(message.chat.id, txt, parse_mode="HTML")



@bot.message_handler(func=lambda message: message.text and message.from_user.id in CHATS and message.text.lower().split()[0] in ["-вид"], imc=True)
def admin_del_type_cmd(message):
    uid = message.from_user.id
    tokens = message.text.split()
    if len(tokens) < 2 or not tokens[1].isdigit():
        return
    ftype = int(tokens[1])
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT food_name FROM FoodTypes WHERE food_type = ?", (ftype,))
        res = c.fetchone()
    if not res:
        return
    fname = res[0]
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("💥Подтвердить", callback_data=f"deltype_{uid}_{message.message_id}_{ftype}"))
    bot.send_message(message.chat.id, f"Вы уверены, что хотите удалить вид еды <b>{fname}</b> (Айди: {ftype})? Это уничтожит все такие продукты у игроков", reply_markup=kb, parse_mode="HTML")



@bot.callback_query_handler(func=lambda call: call.data.startswith("deltype_"))
def admin_del_type_callback(call):
    _, owner_id, msg_id, ftype = call.data.split("_")
    owner_id, msg_id, ftype = int(owner_id), int(msg_id), int(ftype)
    if call.from_user.id != owner_id:
        bot.answer_callback_query(call.id, "Это не твое меню!", show_alert=True)
        return
    if msg_id in LOCKS:
        bot.answer_callback_query(call.id)
        return
    LOCKS[msg_id] = True
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT food_name FROM FoodTypes WHERE food_type = ?", (ftype,))
        res = c.fetchone()
        if not res:
            bot.edit_message_text("Этот вид еды уже не существует", call.message.chat.id, call.message.message_id, reply_markup=None)
            del LOCKS[msg_id]
            return
        fname = res
        c.execute("DELETE FROM Inventory WHERE food_type = ?", (ftype,))
        c.execute("DELETE FROM FoodTypes WHERE food_type = ?", (ftype,))
        c.execute("""
            UPDATE Users 
            SET food = (SELECT COUNT(*) FROM Inventory WHERE Inventory.real_id = Users.real_id)
        """)
        conn.commit()
    bot.edit_message_text(f"Вид еды <b>{fname}</b> (Айди: {ftype}) и все связанные продукты успешно удалены", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=None)
    del LOCKS[msg_id]



@bot.message_handler(func=lambda message: message.text and message.text.lower().startswith(("съесть ", "сьесть ")), imc=True)
def eat_food_cmd(message):
    uid = message.from_user.id
    tokens = message.text.split()
    if len(tokens) < 2 or not tokens[1].isdigit():
        return
    fid = int(tokens[1])
    check(uid)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT i.food_points, t.food_name 
            FROM Inventory i 
            JOIN FoodTypes t ON i.food_type = t.food_type 
            WHERE i.food_id = ? AND i.real_id = ?
        """, (fid, uid))
        res = c.fetchone()
        if not res:
            bot.send_message(message.chat.id, "Данного продукта не существует или он вам не принадлежит")
            return
        points, fname = res
        c.execute("DELETE FROM Inventory WHERE food_id = ?", (fid,))
        c.execute("UPDATE Users SET eat = eat + ?, food = max(0, food - 1) WHERE real_id = ?", (points, uid))
        conn.commit()
    bot.send_message(message.chat.id, f"👄Вы съели <b>{fname}</b> (#{fid}) и набрали +{points} ОС", parse_mode="HTML")



@bot.message_handler(func=lambda message: message.text and message.text.lower().split()[0] in ["дать"], imc=True)
def give_cmd(message):
    uid = message.from_user.id
    tokens = message.text.split()
    check(uid)
    if len(tokens) == 1:
        txt = "<b>Формат передачи</b>\n\nДать [число / #номер] [айди]\nПримеры:\n- Дать #5 1\n- Дать 500 1"
        bot.send_message(message.chat.id, txt, parse_mode="HTML")
        return
    if len(tokens) < 2:
        bot.send_message(message.chat.id, "Неверный формат")
        return
    raw_val = tokens[1]
    is_food = raw_val.startswith("#")
    clean_val = raw_val[1:] if is_food else raw_val
    if not clean_val.isdigit():
        bot.send_message(message.chat.id, "Неверный формат")
        return
    val = int(clean_val)
    target_uid = None
    if len(tokens) >= 3:
        raw_target = tokens[2]
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            if raw_target.isdigit():
                c.execute("SELECT real_id FROM Users WHERE bot_id = ?", (int(raw_target),))
            else:
                c.execute("SELECT real_id FROM Users WHERE bot_name = ?", (raw_target,))
            res = c.fetchone()
        if not res:
            bot.send_message(message.chat.id, "Пользователь не найден")
            return
        target_uid = res[0]
    elif message.reply_to_message:
        target_uid = message.reply_to_message.from_user.id
    else:
        bot.send_message(message.chat.id, "Неверный формат")
        return
    if target_uid == uid:
        return
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT bot_id, bot_name FROM Users WHERE real_id = ?", (target_uid,))
        t_res = c.fetchone()
        if not t_res:
            bot.send_message(message.chat.id, "Пользователь не найден")
            return
        t_bid, t_name = t_res
        if is_food:
            c.execute("SELECT 1 FROM Inventory WHERE food_id = ? AND real_id = ?", (val, uid))
            if not c.fetchone():
                bot.send_message(message.chat.id, "Данный продукт не существует или не принадлежит вам")
                return
            label, mode = f"продукт #{val}", f"food_{val}"
        else:
            c.execute("SELECT coins FROM Users WHERE real_id = ?", (uid,))
            res_coins = c.fetchone()
            if not res_coins or res_coins[0] < val:
                bot.send_message(message.chat.id, "Недостаточно средств")
                return
            label, mode = f"{val} Ж", f"coins_{val}"
    t_disp = t_name if t_name else f"#{t_bid}"
    t_link = f'<a href="tg://user?id={target_uid}">{t_disp}</a>'
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("✅Подтвердить", callback_data=f"give_{uid}_{message.message_id}_{target_uid}_{mode}"))
    bot.send_message(message.chat.id, f"Вы уверены, что хотите передать {label} на {t_link}?", reply_markup=kb, parse_mode="HTML")



@bot.callback_query_handler(func=lambda call: call.data.startswith("give_"))
def give_callback(call):
    _, owner_id, msg_id, t_uid, mode_type, mode_val = call.data.split("_")
    owner_id, msg_id, t_uid, mode_val = int(owner_id), int(msg_id), int(t_uid), int(mode_val)
    if call.from_user.id != owner_id:
        bot.answer_callback_query(call.id, "Это не твое меню!", show_alert=True)
        return
    if msg_id in LOCKS:
        bot.answer_callback_query(call.id)
        return
    LOCKS[msg_id] = True
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT bot_id, bot_name FROM Users WHERE real_id = ?", (owner_id,))
        bid1, name1 = c.fetchone()
        c.execute("SELECT bot_id, bot_name FROM Users WHERE real_id = ?", (t_uid,))
        bid2, name2 = c.fetchone()
        if mode_type == "food":
            c.execute("SELECT 1 FROM Inventory WHERE food_id = ? AND real_id = ?", (mode_val, owner_id))
            if not c.fetchone():
                bot.edit_message_text("Данный продукт не существует или не принадлежит вам", call.message.chat.id, call.message.message_id, reply_markup=None)
                del LOCKS[msg_id]
                return
            c.execute("UPDATE Inventory SET real_id = ? WHERE food_id = ?", (t_uid, mode_val))
            c.execute("UPDATE Users SET food = max(0, food - 1) WHERE real_id = ?", (owner_id,))
            c.execute("UPDATE Users SET food = food + 1 WHERE real_id = ?", (t_uid,))
            label = f"продукт #{mode_val}"
        else:
            c.execute("SELECT coins FROM Users WHERE real_id = ?", (owner_id,))
            res_coins = c.fetchone()
            if not res_coins or res_coins[0] < mode_val:
                bot.edit_message_text("Недостаточно средств", call.message.chat.id, call.message.message_id, reply_markup=None)
                del LOCKS[msg_id]
                return
            c.execute("UPDATE Users SET coins = coins - ? WHERE real_id = ?", (mode_val, owner_id))
            c.execute("UPDATE Users SET coins = coins + ? WHERE real_id = ?", (mode_val, t_uid))
            label = f"{mode_val} Ж"
        conn.commit()
    link1 = f'<a href="tg://user?id={owner_id}">{name1 if name1 else f"#{bid1}"}</a>'
    link2 = f'<a href="tg://user?id={t_uid}">{name2 if name2 else f"#{bid2}"}</a>'
    bot.edit_message_text(f"🔄{link1} передал {label} на {link2}", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=None)
    del LOCKS[msg_id]



def get_types_page(uid, page, msg_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM FoodTypes")
        total_types = c.fetchone()[0]
        c.execute("SELECT food_type, food_name FROM FoodTypes ORDER BY food_type ASC")
        items = c.fetchall()
    pages_cnt = max(1, math.ceil(len(items) / 30))
    if page < 1: page = 1
    if page > pages_cnt: page = pages_cnt
    text = "<b>📋Виды еды</b>\n\n"
    start = (page - 1) * 30
    end = start + 30
    for i, (f_type, f_name) in enumerate(items[start:end], start + 1):
        text += f"{i}. #{f_type} {f_name}\n"
    text += f"\nВсего видов: {total_types} шт.\nСтр. {page}/{pages_cnt}"
    if pages_cnt == 1:
        return text, None
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("⬅️", callback_data=f"types_{uid}_{page-1}_{msg_id}"),
        InlineKeyboardButton("➡️", callback_data=f"types_{uid}_{page+1}_{msg_id}")
    )
    return text, kb



@bot.message_handler(func=lambda message: message.text and message.from_user.id in CHATS and message.text.lower() == "список видов", imc=True)
def list_types_cmd(message):
    uid = message.from_user.id
    text, kb = get_types_page(uid, 1, message.message_id)
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=kb)



@bot.callback_query_handler(func=lambda call: call.data.startswith("types_"))
def list_types_callback(call):
    _, owner_id, page, msg_id = call.data.split("_")
    owner_id, page, msg_id = int(owner_id), int(page), int(msg_id)
    if call.from_user.id != owner_id:
        bot.answer_callback_query(call.id, "Это не твое меню!", show_alert=True)
        return
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM FoodTypes")
        items_cnt = c.fetchone()[0]
    pages_cnt = max(1, math.ceil(items_cnt / 30))
    if page < 1 or page > pages_cnt:
        bot.answer_callback_query(call.id)
        return
    if msg_id in LOCKS:
        bot.answer_callback_query(call.id)
        return
    LOCKS[msg_id] = True
    text, kb = get_types_page(owner_id, page, msg_id)
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=kb)
    del LOCKS[msg_id]



@bot.message_handler(func=lambda message: message.text and message.text.lower().startswith("см "), imc=True)
def view_food_cmd(message):
    tokens = message.text.split(maxsplit=1)
    if len(tokens) < 2 or not tokens[1].isdigit():
        return
    fid = int(tokens[1])
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT t.food_sticker, t.food_name, i.food_price, i.food_points, u.real_id, u.bot_id, u.bot_name
            FROM Inventory i 
            JOIN FoodTypes t ON i.food_type = t.food_type 
            JOIN Users u ON i.real_id = u.real_id
            WHERE i.food_id = ?
        """, (fid,))
        res = c.fetchone()
    if not res:
        bot.send_message(message.chat.id, "Продукт не найден")
        return
    sticker, name, price, points, r_id, b_id, b_name = res
    bot.send_sticker(message.chat.id, sticker)
    
    disp = b_name if b_name else f"#{b_id}"
    profile = f'<a href="tg://user?id={r_id}">\u200b{disp}</a>'
    
    txt = f"<b>{name}</b>\n🆔 {fid}\n💰 {price} Ж\n✨ {points} ОС\n👤 {profile}"
    bot.send_message(message.chat.id, txt, parse_mode="HTML")



@bot.message_handler(func=lambda message: message.text and message.from_user.id in CHATS and message.text.lower().startswith("смвид "), imc=True)
def view_food_type_cmd(message):
    tokens = message.text.split(maxsplit=1)
    if len(tokens) < 2 or not tokens[1].isdigit():
        return
    ftype = int(tokens[1])
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT food_sticker, food_name FROM FoodTypes WHERE food_type = ?", (ftype,))
        res = c.fetchone()
    if not res:
        bot.send_message(message.chat.id, "Вид еды не найден")
        return
    sticker, name = res
    bot.send_sticker(message.chat.id, sticker)
    txt = f"<b>{name}</b>\n🆔 {ftype}"
    bot.send_message(message.chat.id, txt, parse_mode="HTML")



@bot.message_handler(func=lambda message: message.text and message.from_user.id in CHATS and message.text.lower() == "-кд", imc=True)
def reset_kd_cmd(message):
    uid = message.from_user.id
    check(uid)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET time_kd = 0 WHERE real_id = ?", (uid,))
        conn.commit()
    bot.send_message(message.chat.id, "Ваш КД успешно сброшен")



@bot.message_handler(func=lambda message: message.text and message.text.lower() == "-имя", imc=True)
def remove_name_cmd(message):
    uid = message.from_user.id
    check(uid)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT bot_name FROM Users WHERE real_id = ?", (uid,))
        res = c.fetchone()
    if not res or not res[0]:
        bot.send_message(message.chat.id, "У вас и так нет имени")
        return
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("✅Подтвердить", callback_data=f"delname_{uid}_{message.message_id}"))
    bot.send_message(message.chat.id, "Вы уверены, что хотите удалить своё имя?", reply_markup=kb)



@bot.callback_query_handler(func=lambda call: call.data.startswith("delname_"))
def remove_name_callback(call):
    _, owner_id, msg_id = call.data.split("_")
    owner_id, msg_id = int(owner_id), int(msg_id)
    if call.from_user.id != owner_id:
        bot.answer_callback_query(call.id, "Это не твое меню!", show_alert=True)
        return
    if msg_id in LOCKS:
        bot.answer_callback_query(call.id)
        return
    LOCKS[msg_id] = True
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET bot_name = '' WHERE real_id = ?", (owner_id,))
        c.execute("SELECT bot_id FROM Users WHERE real_id = ?", (owner_id,))
        bid = c.fetchone()[0]
        conn.commit()
    link = f'<a href="tg://user?id={owner_id}">#{bid}</a>'
    bot.edit_message_text(f"🗑️{link} удалил своё имя", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=None)
    del LOCKS[msg_id]



@bot.message_handler(func=lambda message: message.text and message.text.strip().lower() in ["инфо", "инфа", "/info", "/info@shittycircusbot"], imc=True)
def info_cmd(message):
    txt = (
        "<b>ℹ️Информация о боте</b>\n\n"
        "Основная валюта — это жетоны (Ж). Они предназначены пока что лишь для покупки имени.\n\n<b>☎️Основные команды</b>\n"
        "<blockquote expandable>• Б — баланс\n\n• Дать [число / #номер] — передача жетонов или продуктов\n\n• Еда — ежечасное получение продуктов\n\n• См [номер] — информация о продукте\n\n• Лидер — список топов\n\n• +Имя — покупка имени за 1000 Ж\n\n• -Имя — удаление имени\n\n• Инв — инвентарь</blockquote>\n\n"
        "Имеется 3 способа указания пользователя: указание нужного игрового айди или игрового имени в конце сообщения, а также отправка команды ответом на чужое сообщение нужного пользователя.\n\n<b>По любым вопросам —</b> @yamexa"
    )
    bot.send_message(message.chat.id, txt, parse_mode="HTML")



init_db()
print("есть")
bot.infinity_polling()