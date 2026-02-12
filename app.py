import os
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram import Update

print("🚀 СТАРТ МИНИМАЛЬНОГО БОТА")
token = os.environ.get("BOT_TOKEN")
print(f"Токен загружен: {token[:15] if token else 'НЕТ ТОКЕНА!'}...")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Минимальный бот работает!")

if __name__ == "__main__":
    print("🔄 Запуск polling...")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()
