import os
import sys
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Set, Optional, Tuple

# Настройка event loop для Render
try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        print("Loop already running")
except:
    print("Creating new event loop")
    asyncio.set_event_loop(asyncio.new_event_loop())

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

# ---------- НАСТРОЙКИ ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8223338991:AAFcRy3QWcjd2wm2KXrF_W9IkgFoJ0j2IBA")
ADMIN_ID = 7352226640
GROUP_ID = -1003868647705
TOPIC_CATALOG = 24      # тема, где кнопка заказа
TOPIC_NEWS = 3          # тема с расписанием/новостями
TOPIC_ANNOUNCE = 1      # тема для уведомлений о новостях
TOPIC_CONTRACT = 6      # тема для контрактов

# ---------- ХРАНИЛИЩЕ (in memory) ----------
catalog_buttons: Dict[str, str] = {}
blacklist: Dict[str, Tuple[str, datetime]] = {}
notification_recipients: Set[str] = set()
kontr_allowed: Set[int] = set()
user_purchases: Dict[int, int] = {}

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def is_banned(username: str) -> Tuple[bool, str]:
    if username in blacklist:
        reason, _ = blacklist[username]
        return True, reason
    return False, ""

def format_datetime(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y")

# ---------- КОМАНДА /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username
    if username and is_banned(username)[0]:
        banned, reason = is_banned(username)
        await update.message.reply_text(f"❌ Вы не можете пользоваться ботом по причине:\n{reason}")
        return

    text = "🚃 Привет! Хочешь купить билетик на трамвай? Выбирай себе свой!"
    keyboard = [[InlineKeyboardButton("📋 Каталог", callback_data="catalog")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- КАТАЛОГ ----------
async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not catalog_buttons:
        await query.edit_message_text("📭 Каталог пока пуст.")
        return

    text = "📅 Актуальный каталог на завтра:"
    keyboard = []
    row = []
    for num, name in sorted(catalog_buttons.items()):
        row.append(InlineKeyboardButton(name, callback_data=f"buy_{num}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("◀ Назад", callback_data="back_to_start")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- ПОКУПКА ----------
async def buy_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    username = user.username or "без username"
    user_id = user.id

    data = query.data
    button_num = data.split("_")[1]
    button_name = catalog_buttons.get(button_num, "Билет")

    if user_id in user_purchases and user_purchases[user_id] >= 2:
        await query.edit_message_text("❌ Вы уже купили максимум 2 билета на сегодня.")
        return

    user_purchases[user_id] = user_purchases.get(user_id, 0) + 1
    bought = user_purchases[user_id]

    notify_text = f"🆕 Новый заказ: {button_name} @{username} купил {bought}/2"
    
    try:
        await context.bot.send_message(ADMIN_ID, notify_text)
    except:
        pass
    
    for recip in notification_recipients:
        try:
            await context.bot.send_message(username=recip, text=notify_text)
        except:
            pass

    await query.edit_message_text(f"✅ Заказ оформлен!\n{button_name} — {bought}/2 билетов.\nСпасибо за покупку! 😊")

# ---------- НАЗАД В СТАРТ ----------
async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🚃 Привет! Хочешь купить билетик на трамвай? Выбирай себе свой!"
    keyboard = [[InlineKeyboardButton("📋 Каталог", callback_data="catalog")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- АДМИН-ПАНЕЛЬ ----------
async def apanel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    keyboard = [
        [InlineKeyboardButton("📢 Выдать уведомления", callback_data="admin_notify")],
        [InlineKeyboardButton("🚫 ЧС (бан/разбан)", callback_data="admin_ban")],
        [InlineKeyboardButton("🔄 Обновить кнопку каталога", callback_data="admin_edit_catalog")]
    ]
    await update.message.reply_text("🛠 Админ-панель:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Введите username пользователя (без @), которому выдавать уведомления о заказах.\n"
        "Если уже есть в списке — повторный ввод уберёт его."
    )
    context.user_data['admin_action'] = 'toggle_notify'

async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Введите username, причину и Да/Нет в формате:\n"
        "`username причина Да` — забанить\n"
        "`username причина Нет` — разбанить"
    )
    context.user_data['admin_action'] = 'ban'

async def admin_edit_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not catalog_buttons:
        text = "Каталог пуст. Введите номер и название для новой кнопки:\n`1 Название`"
    else:
        text = "Текущие кнопки:\n"
        for num, name in catalog_buttons.items():
            text += f"{num}: {name}\n"
        text += "\nВведите номер и новое название для замены, или новый номер+название для добавления.\nПример: `2 Экскурсионный`"
    await query.edit_message_text(text)
    context.user_data['admin_action'] = 'edit_catalog'

# ---------- ОБРАБОТКА ТЕКСТА ОТ АДМИНА ----------
async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    action = context.user_data.get('admin_action')
    if not action:
        return

    text = update.message.text.strip()

    if action == 'toggle_notify':
        target = text.lstrip('@')
        if target in notification_recipients:
            notification_recipients.remove(target)
            await update.message.reply_text(f"❌ Уведомления убраны у @{target}")
        else:
            notification_recipients.add(target)
            await update.message.reply_text(f"✅ Уведомления выданы @{target}")
        context.user_data.pop('admin_action')
        return

    if action == 'ban':
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await update.message.reply_text("Неверный формат. Нужно: username причина Да/Нет")
            return
        target, reason, decision = parts
        target = target.lstrip('@')
        if decision.lower() == 'да':
            blacklist[target] = (reason, datetime.now())
            await update.message.reply_text(f"🚫 @{target} забанен. Причина: {reason}")
        else:
            blacklist.pop(target, None)
            await update.message.reply_text(f"✅ @{target} разбанен.")
        context.user_data.pop('admin_action')
        return

    if action == 'edit_catalog':
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            await update.message.reply_text("Введите номер и название через пробел.")
            return
        num, name = parts
        catalog_buttons[num] = name
        await update.message.reply_text(f"✅ Кнопка {num}: «{name}» сохранена.")
        context.user_data.pop('admin_action')
        return

# ---------- КОМАНДЫ КОНТРАКТОВ ----------
async def newkontr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID and user_id not in kontr_allowed:
        return
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("Формат: /newkontr [С кем] [Текст] [Дата начала] [Дата конца, опционально]")
        return
    who = args[0]
    text_contract = args[1]
    start_date_str = args[2]
    end_date_str = args[3] if len(args) > 3 else None

    try:
        start_date = datetime.strptime(start_date_str, "%d.%m.%Y")
        if end_date_str:
            end_date = datetime.strptime(end_date_str, "%d.%m.%Y")
        else:
            end_date = start_date + timedelta(days=365)
    except:
        await update.message.reply_text("Ошибка в формате даты. Используйте ДД.ММ.ГГГГ")
        return

    msg = (
        f"📄 Новый контракт: {who} — ИП ФОГ.\n"
        f"{text_contract}\n"
        f"Дата заключения: {format_datetime(start_date)}\n"
        f"Дата окончания: {format_datetime(end_date)}"
    )
    try:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=TOPIC_CONTRACT,
            text=msg
        )
        await update.message.reply_text("✅ Контракт опубликован.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка отправки в группу: {e}")

async def givekontr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        return
    try:
        user_id = int(context.args[0])
        kontr_allowed.add(user_id)
        await context.bot.send_message(user_id, "✅ Вам выдали команду /newkontr")
        await update.message.reply_text("✅ Выдано.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def delkontr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        return
    try:
        user_id = int(context.args[0])
        kontr_allowed.discard(user_id)
        await context.bot.send_message(user_id, "❌ У вас забрали команду /newkontr")
        await update.message.reply_text("✅ Забрано.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ---------- ГРУППОВАЯ ЛОГИКА ----------
async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, есть ли message_thread_id (это тема)
    if not update.effective_message.message_thread_id:
        return
        
    # Если сообщение в теме 3 (новости) -> уведомление в тему 1 и 24
    if update.effective_message.message_thread_id == TOPIC_NEWS:
        text = "📢 Новый билет или новость в теме «Расписание»!"
        # тема 1
        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=TOPIC_ANNOUNCE,
                text=text
            )
        except:
            pass
        # тема 24
        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=TOPIC_CATALOG,
                text=text
            )
        except:
            pass
        return

    # Если сообщение в теме 24 — добавить кнопку заказа
    if update.effective_message.message_thread_id == TOPIC_CATALOG:
        keyboard = [[InlineKeyboardButton("🎟 Заказать билет", callback_data="catalog")]]
        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=TOPIC_CATALOG,
                text="🚃 Хотите билетик?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass

# ---------- MAIN ----------
def main():
    print("Запуск бота...")
    
    # Создаем приложение
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("apanel", apanel))
    application.add_handler(CommandHandler("newkontr", newkontr))
    application.add_handler(CommandHandler("givekontr", givekontr))
    application.add_handler(CommandHandler("delkontr", delkontr))

    # Callback-и
    application.add_handler(CallbackQueryHandler(show_catalog, pattern="^catalog$"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(buy_ticket, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(admin_notify, pattern="^admin_notify$"))
    application.add_handler(CallbackQueryHandler(admin_ban, pattern="^admin_ban$"))
    application.add_handler(CallbackQueryHandler(admin_edit_catalog, pattern="^admin_edit_catalog$"))

    # Текст от админа
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & filters.User(user_id=ADMIN_ID), 
        handle_admin_text
    ))

    # Групповые сообщения
    application.add_handler(MessageHandler(
        filters.Chat(chat_id=GROUP_ID) & (~filters.COMMAND), 
        group_message_handler
    ))

    # Запуск с очисткой старых запросов
    print("Бот запущен и готов к работе!")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
