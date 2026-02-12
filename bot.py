import os
import sys
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Set, Optional, Tuple, Union

# Настройка event loop для Render
try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        print("Loop already running")
except:
    print("Creating new event loop")
    asyncio.set_event_loop(asyncio.new_event_loop())

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, User
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
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
blacklist: Dict[str, Tuple[str, datetime]] = {}  # username или user_id -> (причина, дата)
notification_recipients: Set[Union[str, int]] = set()  # username или user_id
kontr_allowed: Set[int] = set()  # user_id
givekontr_allowed: Set[int] = set()  # кто может выдавать kontr
delkontr_allowed: Set[int] = set()  # кто может забирать kontr
user_purchases: Dict[int, int] = {}

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def is_banned(identifier: Union[str, int]) -> Tuple[bool, str]:
    """Проверка бана по username или user_id"""
    str_id = str(identifier)
    if str_id in blacklist:
        reason, _ = blacklist[str_id]
        return True, reason
    if isinstance(identifier, int) and str(identifier) in blacklist:
        reason, _ = blacklist[str(identifier)]
        return True, reason
    return False, ""

def format_datetime(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y")

async def get_user_by_identifier(context: ContextTypes.DEFAULT_TYPE, identifier: str) -> Optional[User]:
    """Получить объект User по username или ID"""
    identifier = identifier.strip().lstrip('@')
    
    # Если это число - пробуем как user_id
    if identifier.isdigit():
        try:
            user_id = int(identifier)
            return await context.bot.get_chat(user_id)
        except:
            pass
    else:
        # Пробуем как username
        try:
            return await context.bot.get_chat(f"@{identifier}")
        except:
            pass
    return None

# ---------- КОМАНДА /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username
    
    # Проверка бана
    banned, reason = is_banned(username) or is_banned(user_id)
    if banned:
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
    username = user.username or f"id{user.id}"
    user_id = user.id
    
    # Проверка бана
    banned, reason = is_banned(username) or is_banned(user_id)
    if banned:
        await query.edit_message_text(f"❌ Вы забанены. Причина: {reason}")
        return

    data = query.data
    button_num = data.split("_")[1]
    button_name = catalog_buttons.get(button_num, "Билет")

    if user_id in user_purchases and user_purchases[user_id] >= 2:
        await query.edit_message_text("❌ Вы уже купили максимум 2 билета на сегодня.")
        return

    user_purchases[user_id] = user_purchases.get(user_id, 0) + 1
    bought = user_purchases[user_id]

    notify_text = f"🆕 Новый заказ: {button_name}\n👤 @{user.username or 'нет username'} (ID: {user_id})\n🎟 Куплено: {bought}/2"
    
    # Уведомление админу
    try:
        await context.bot.send_message(ADMIN_ID, notify_text)
    except:
        pass
    
    # Уведомления получателям
    for recip in notification_recipients:
        try:
            if isinstance(recip, int):
                await context.bot.send_message(recip, notify_text)
            else:
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
        [InlineKeyboardButton("🔄 Обновить кнопку каталога", callback_data="admin_edit_catalog")],
        [InlineKeyboardButton("📝 Выдать /newkontr", callback_data="admin_give_kontr")],
        [InlineKeyboardButton("❌ Забрать /newkontr", callback_data="admin_del_kontr")],
        [InlineKeyboardButton("📋 Список допущенных", callback_data="admin_list_kontr")]
    ]
    await update.message.reply_text("🛠 Админ-панель:", reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- ОБРАБОТЧИКИ АДМИН-КНОПОК ----------
async def admin_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📢 Введите username или ID пользователя для выдачи/удаления уведомлений:\n"
        "Примеры: `durov` или `123456789`"
    )
    context.user_data['admin_action'] = 'toggle_notify'

async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🚫 Введите username/ID, причину и Да/Нет в формате:\n"
        "`durov Спам Да` — забанить\n"
        "`123456789 Нарушение Нет` — разбанить"
    )
    context.user_data['admin_action'] = 'ban'

async def admin_edit_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not catalog_buttons:
        text = "📭 Каталог пуст. Введите номер и название для новой кнопки:\n`1 Экскурсионный`"
    else:
        text = "📋 Текущие кнопки:\n"
        for num, name in catalog_buttons.items():
            text += f"{num}: {name}\n"
        text += "\n✏️ Введите номер и новое название для замены или добавления:\n`2 Городской`"
    await query.edit_message_text(text)
    context.user_data['admin_action'] = 'edit_catalog'

async def admin_give_kontr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 Введите username или ID пользователя для выдачи команды /newkontr:"
    )
    context.user_data['admin_action'] = 'give_kontr'

async def admin_del_kontr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "❌ Введите username или ID пользователя для забора команды /newkontr:"
    )
    context.user_data['admin_action'] = 'del_kontr'

async def admin_list_kontr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not kontr_allowed:
        await query.edit_message_text("📭 Нет пользователей с доступом к /newkontr")
        return
    
    text = "📋 Пользователи с доступом к /newkontr:\n"
    for user_id in kontr_allowed:
        try:
            user = await context.bot.get_chat(user_id)
            text += f"• {user.full_name} (@{user.username}) - ID: {user_id}\n"
        except:
            text += f"• ID: {user_id}\n"
    await query.edit_message_text(text)

# ---------- ОБРАБОТКА ТЕКСТА ОТ АДМИНА ----------
async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    action = context.user_data.get('admin_action')
    if not action:
        return

    text = update.message.text.strip()
    
    # ---------- УВЕДОМЛЕНИЯ ----------
    if action == 'toggle_notify':
        identifier = text.lstrip('@')
        
        # Пробуем получить пользователя
        user = await get_user_by_identifier(context, identifier)
        
        if not user:
            # Если не нашли, сохраняем как строку
            if identifier in notification_recipients or int(identifier) in notification_recipients:
                notification_recipients.discard(identifier)
                notification_recipients.discard(int(identifier))
                await update.message.reply_text(f"❌ Уведомления убраны у {identifier}")
            else:
                notification_recipients.add(identifier)
                await update.message.reply_text(f"✅ Уведомления выданы {identifier}")
        else:
            user_id = user.id
            if user_id in notification_recipients:
                notification_recipients.discard(user_id)
                await update.message.reply_text(f"❌ Уведомления убраны у {user.full_name} (ID: {user_id})")
            else:
                notification_recipients.add(user_id)
                await update.message.reply_text(f"✅ Уведомления выданы {user.full_name} (ID: {user_id})")
        
        context.user_data.pop('admin_action')
        return
    
    # ---------- БАН ----------
    if action == 'ban':
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await update.message.reply_text("❌ Неверный формат. Нужно: username причина Да/Нет")
            return
        
        identifier, reason, decision = parts
        identifier = identifier.lstrip('@')
        decision = decision.lower()
        
        # Пробуем получить пользователя
        user = await get_user_by_identifier(context, identifier)
        
        if decision == 'да':
            if user:
                ban_key = str(user.id)
                blacklist[ban_key] = (reason, datetime.now())
                await update.message.reply_text(f"🚫 {user.full_name} (ID: {user.id}) забанен.\nПричина: {reason}")
                
                # Уведомление пользователю
                try:
                    await context.bot.send_message(
                        user.id,
                        f"❌ Вы забанены в боте.\nПричина: {reason}\nСрок: навсегда"
                    )
                except:
                    pass
            else:
                blacklist[identifier] = (reason, datetime.now())
                await update.message.reply_text(f"🚫 {identifier} забанен.\nПричина: {reason}")
        else:
            if user:
                ban_key = str(user.id)
                blacklist.pop(ban_key, None)
                await update.message.reply_text(f"✅ {user.full_name} (ID: {user.id}) разбанен.")
                
                # Уведомление пользователю
                try:
                    await context.bot.send_message(
                        user.id,
                        "✅ Вы разбанены в боте."
                    )
                except:
                    pass
            else:
                blacklist.pop(identifier, None)
                blacklist.pop(str(identifier), None)
                await update.message.reply_text(f"✅ {identifier} разбанен.")
        
        context.user_data.pop('admin_action')
        return
    
    # ---------- РЕДАКТИРОВАНИЕ КАТАЛОГА ----------
    if action == 'edit_catalog':
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            await update.message.reply_text("❌ Введите номер и название через пробел.")
            return
        num, name = parts
        catalog_buttons[num] = name
        await update.message.reply_text(f"✅ Кнопка {num}: «{name}» сохранена.")
        context.user_data.pop('admin_action')
        return
    
    # ---------- ВЫДАТЬ /newkontr ----------
    if action == 'give_kontr':
        identifier = text.lstrip('@')
        user = await get_user_by_identifier(context, identifier)
        
        if user:
            user_id = user.id
            kontr_allowed.add(user_id)
            await update.message.reply_text(f"✅ Команда /newkontr выдана {user.full_name} (ID: {user_id})")
            
            try:
                await context.bot.send_message(
                    user_id,
                    "✅ Вам выдали команду /newkontr\n"
                    "Формат: /newkontr [С кем] [Текст] [ДД.ММ.ГГГГ] [ДД.ММ.ГГГГ, опционально]"
                )
            except:
                pass
        else:
            await update.message.reply_text("❌ Пользователь не найден")
        
        context.user_data.pop('admin_action')
        return
    
    # ---------- ЗАБРАТЬ /newkontr ----------
    if action == 'del_kontr':
        identifier = text.lstrip('@')
        user = await get_user_by_identifier(context, identifier)
        
        if user:
            user_id = user.id
            kontr_allowed.discard(user_id)
            await update.message.reply_text(f"❌ Команда /newkontr забрана у {user.full_name} (ID: {user_id})")
            
            try:
                await context.bot.send_message(
                    user_id,
                    "❌ У вас забрали команду /newkontr"
                )
            except:
                pass
        else:
            await update.message.reply_text("❌ Пользователь не найден")
        
        context.user_data.pop('admin_action')
        return

# ---------- КОМАНДЫ КОНТРАКТОВ ----------
async def newkontr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверка доступа
    if user_id != ADMIN_ID and user_id not in kontr_allowed:
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
    
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "📝 Формат: /newkontr [С кем] [Текст] [Дата начала] [Дата конца, опционально]\n"
            "Пример: /newkontr ООО Ромашка Поставка 15.05.2026 15.05.2027"
        )
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
        await update.message.reply_text("❌ Ошибка в формате даты. Используйте ДД.ММ.ГГГГ")
        return

    user = update.effective_user
    author = f"{user.full_name} (@{user.username})" if user.username else user.full_name
    
    msg = (
        f"📄 **Новый контракт**\n"
        f"👤 Автор: {author}\n"
        f"🏢 Контрагент: {who}\n"
        f"📝 Содержание: {text_contract}\n"
        f"📅 Дата заключения: {format_datetime(start_date)}\n"
        f"📅 Дата окончания: {format_datetime(end_date)}"
    )
    
    try:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=TOPIC_CONTRACT,
            text=msg,
            parse_mode=ParseMode.MARKDOWN
        )
        await update.message.reply_text("✅ Контракт опубликован в теме #6.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка отправки в группу: {e}")

# ---------- ГРУППОВАЯ ЛОГИКА ----------
async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, есть ли message_thread_id (это тема)
    if not update.effective_message.message_thread_id:
        return
        
    # Если сообщение в теме 3 (новости) -> уведомление в тему 1 и 24
    if update.effective_message.message_thread_id == TOPIC_NEWS:
        text = "📢 **Новый билет или новость в теме «Расписание»!**"
        
        # тема 1
        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=TOPIC_ANNOUNCE,
                text=text,
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
        
        # тема 24
        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=TOPIC_CATALOG,
                text=text,
                parse_mode=ParseMode.MARKDOWN
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

    # Callback-и админки
    application.add_handler(CallbackQueryHandler(show_catalog, pattern="^catalog$"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(buy_ticket, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(admin_notify, pattern="^admin_notify$"))
    application.add_handler(CallbackQueryHandler(admin_ban, pattern="^admin_ban$"))
    application.add_handler(CallbackQueryHandler(admin_edit_catalog, pattern="^admin_edit_catalog$"))
    application.add_handler(CallbackQueryHandler(admin_give_kontr, pattern="^admin_give_kontr$"))
    application.add_handler(CallbackQueryHandler(admin_del_kontr, pattern="^admin_del_kontr$"))
    application.add_handler(CallbackQueryHandler(admin_list_kontr, pattern="^admin_list_kontr$"))

    # Текст от админа
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & filters.User(user_id=ADMIN_ID), 
        handle_admin_text
    ))

    
