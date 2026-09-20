import telebot, os

token=os.getenv("BOT_TOKEN")

bot=telebot.TeleBot(token)

@bot.message_handler(func=lambda message: message.text.lower()=="hi")
def hi(message):
	bot.reply_to(message, "hello")

bot.infinity_polling()