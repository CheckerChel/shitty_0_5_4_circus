import os
import sqlite3
import random
import telebot
from telebot import apihelper

apihelper.ENABLE_MIDDLEWARE = True
bot = telebot.TeleBot(os.getenv("BOT_TOKEN"))
CHATS = [-1003724538567, 7163427034, -1004243458835]
BLACKLIST = [8638079016, 5443619563]
DB_PATH = "data/very_db.db"
os.makedirs("data", exist_ok=True)

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS Users (
                bot_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                real_id INTEGER UNIQUE, 
                roses INTEGER DEFAULT 0
            )"""
        )

def check(uid):
    with sqlite3.connect(DB_PATH) as conn:
        if not conn.execute("SELECT 1 FROM Users WHERE real_id = ?", (uid,)).fetchone():
            conn.execute("INSERT INTO Users (real_id, roses) VALUES (?, 0)", (uid,))

class Filter(telebot.SimpleCustomFilter):
    key = "imc"
    def check(self, obj):
        c_id = obj.chat.id if hasattr(obj, "chat") else getattr(obj.message, "chat").id
        return c_id in CHATS or obj.from_user.id in CHATS

bot.add_custom_filter(Filter())



@bot.middleware_handler(update_types=["message"])
def active_middleware(bot_instance, m):
    if m.chat.id in CHATS or m.from_user.id in CHATS:
        if m.from_user and not m.from_user.is_bot:
            uid = m.from_user.id
            if uid in BLACKLIST:
                return
            check(uid)
            if random.random() < 0.5:
                r = random.randint(1, 3)
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("UPDATE Users SET roses = roses + ? WHERE real_id = ?", (r, uid))
                    b_id = conn.execute("SELECT bot_id FROM Users WHERE real_id = ?", (uid,)).fetchone()[0]
                try:
                    bot.send_message(m.chat.id, f"🎪<a href='tg://user?id={uid}'>#{b_id}</a>, цирк заметил твою активность! Вы получили {r}🌹", parse_mode="HTML", reply_to_message_id=m.message_id)
                except:
                    pass



@bot.message_handler(func=lambda m: m.text and m.text.strip().lower().startswith("дать"), imc=True)
def give_roses_cmd(m):
    uid = m.from_user.id
    p = m.text.strip().split()
    if len(p) < 2: 
        return bot.reply_to(m, "Формат: дать [сумма] [айди/реплай]")
    try:
        amt = int(p[1])
        if amt <= 0: return
    except: 
        return
    t_uid = None
    if m.reply_to_message:
        t_uid = m.reply_to_message.from_user.id
        check(t_uid)
    elif len(p) == 3:
        try:
            t_bid = int(p[2])
            with sqlite3.connect(DB_PATH) as conn:
                res = conn.execute("SELECT real_id FROM Users WHERE bot_id = ?", (t_bid,)).fetchone()
                if res: t_uid = res[0]
        except: 
            return
    if not t_uid or uid == t_uid: return
    with sqlite3.connect(DB_PATH) as conn:
        s_res = conn.execute("SELECT roses FROM Users WHERE real_id = ?", (uid,)).fetchone()
        t_res = conn.execute("SELECT bot_id FROM Users WHERE real_id = ?", (t_uid,)).fetchone()
        if not s_res or s_res[0] < amt or not t_res: 
            return bot.reply_to(m, "Недостаточно мини-роз или пользователь не найден")
        t_bid = t_res[0]
        s_bid = conn.execute("SELECT bot_id FROM Users WHERE real_id = ?", (uid,)).fetchone()[0]
        conn.execute("UPDATE Users SET roses = roses - ? WHERE real_id = ?", (amt, uid))
        conn.execute("UPDATE Users SET roses = roses + ? WHERE real_id = ?", (amt, t_uid))
    bot.send_message(m.chat.id, f"🔄<a href='tg://user?id={uid}'>#{s_bid}</a> передал {amt}🌹 на <a href='tg://user?id={t_uid}'>#{t_bid}</a>", parse_mode="HTML")



@bot.message_handler(func=lambda m: m.text and m.text.strip().lower().startswith("+розы"), imc=True)
def add_roses_admin_cmd(m):
    uid = m.from_user.id
    if uid not in CHATS: return
    p = m.text.strip().split()
    if len(p) < 2: return
    try:
        amt = int(p[1])
        if amt <= 0: return
        target_uid = m.reply_to_message.from_user.id if m.reply_to_message else uid
        check(target_uid)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE Users SET roses = roses + ? WHERE real_id = ?", (amt, target_uid))
            b_id = conn.execute("SELECT bot_id FROM Users WHERE real_id = ?", (target_uid,)).fetchone()[0]
        if target_uid == uid:
            bot.reply_to(m, f"🎩<a href='tg://user?id={uid}'>#{b_id}</a> выдал себе {amt}🌹", parse_mode="HTML")
        else:
            bot.reply_to(m, f"🎩Админ выдал {amt}🌹 пользователю <a href='tg://user?id={target_uid}'>#{b_id}</a>", parse_mode="HTML")
    except: 
        pass



@bot.message_handler(func=lambda m: m.text and m.text.strip().lower().startswith("-розы"), imc=True)
def remove_roses_admin_cmd(m):
    uid = m.from_user.id
    if uid not in CHATS: return
    p = m.text.strip().split()
    if len(p) < 2: return
    try:
        amt = int(p[1])
        if amt <= 0: return
        target_uid = m.reply_to_message.from_user.id if m.reply_to_message else uid
        check(target_uid)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE Users SET roses = CASE WHEN roses - ? < 0 THEN 0 ELSE roses - ? END WHERE real_id = ?", (amt, amt, target_uid))
            b_id = conn.execute("SELECT bot_id FROM Users WHERE real_id = ?", (target_uid,)).fetchone()[0]
        if target_uid == uid:
            bot.reply_to(m, f"🎩<a href='tg://user?id={uid}'>#{b_id}</a> снёс свои {amt}🌹", parse_mode="HTML")
        else:
            bot.reply_to(m, f"🎩Админ забрал {amt}🌹 у пользователя <a href='tg://user?id={target_uid}'>#{b_id}</a>", parse_mode="HTML")
    except: 
        pass



@bot.message_handler(func=lambda m: m.text and m.text.strip().lower() in ["б"], imc=True)
def balance_cmd(m):
    uid = m.from_user.id
    p = m.text.strip().split()
    t_uid = None
    if m.reply_to_message:
        t_uid = m.reply_to_message.from_user.id
        check(t_uid)
    elif len(p) >= 2:
        try:
            t_bid = int(p[1])
            with sqlite3.connect(DB_PATH) as conn:
                res = conn.execute("SELECT real_id FROM Users WHERE bot_id = ?", (t_bid,)).fetchone()
                if res: t_uid = res[0]
                else: return bot.reply_to(m, "Пользователь не найден")
        except ValueError: 
            return bot.reply_to(m, "Формат: б [айди]")
    else:
        t_uid = uid
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT bot_id, roses FROM Users WHERE real_id = ?", (t_uid,)).fetchone()
    if not res: 
        return bot.reply_to(m, "Пользователь не найден")
    b_id, roses = res
    txt = f"👤<a href='tg://user?id={t_uid}'>#{b_id}</a>\nМини-роз: {roses}🌹"
    bot.reply_to(m, txt, parse_mode="HTML")



@bot.message_handler(func=lambda message: message.text and message.text.strip().lower() in ["инфо", "инфа", "/info"], imc=True)
def info_cmd(message):
    txt = "<b>🎪Информация о боте цирка</b>\n\nЗа общение рандомно выдаются мини-розы — главная валюта бота. В обмен на 100 таких мини-роз вы можете получить подарок ТГ-подарок <b>Роза</b>. Это маленький бонус, так что даже не пытайтесь выпрашивать мини-розы у админа.\n<b>Команды</b>:\n• Б — просмотр баланса\n• Дать [сумма] — передача мини-роз\n\n<b>По любым вопросам —</b> @yamexa"
    bot.send_message(message.chat.id, txt, parse_mode="HTML")



if __name__ == "__main__":
    print("Есть")
    init_db()
    bot.infinity_polling()