import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальные переменные
players = {}  # {user_id: username}
game_state = "LOBBY"  # LOBBY, REGISTRATION, GAME
registration_msg = None  # Сообщение с регистрацией

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start - принудительно начинает игру"""
    global game_state
    
    if len(players) < 4:
        await update.message.reply_text("❌ Недостаточно игроков (нужно 4+)")
        return
    
    game_state = "GAME"
    await start_game(update, context)

async def game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /game - начинает/обновляет регистрацию"""
    global game_state, registration_msg
    
    if game_state == "GAME":
        await update.message.reply_text("Игра уже идет!")
        return
    
    # Удаляем старое сообщение с регистрацией, если оно есть
    if registration_msg:
        try:
            await registration_msg.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")
    
    game_state = "REGISTRATION"
    registration_msg = await update.message.reply_text(
        get_registration_text(),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Присоединиться", callback_data="join")]
        ])
    )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки присоединиться"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    if user.id not in players:
        players[user.id] = user.first_name
        
        # Обновляем сообщение с регистрацией
        try:
            await registration_msg.edit_text(
                text=get_registration_text(),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Присоединиться", callback_data="join")]
                ])
            )
        except Exception as e:
            logger.error(f"Ошибка обновления: {e}")
        
        # Автозапуск игры при 4+ игроках
        if len(players) >= 4:
            await start_game(update, context)
            return
            
        # Отправляем ЛС
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text="✅ Вы успешно зарегистрировались в игре!"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки ЛС: {e}")
    else:
        await query.edit_message_text("⚠️ Вы уже зарегистрированы!")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает игру"""
    global game_state, registration_msg
    
    game_state = "GAME"
    
    # Удаляем сообщение с регистрацией
    if registration_msg:
        try:
            await registration_msg.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления: {e}")
        registration_msg = None
    
    # Распределяем роли
    roles_assignment = assign_roles()
    
    # Отправляем роли в ЛС
    for user_id, role in roles_assignment.items():
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎭 Ваша роль: {role}\nНе показывайте её никому!"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки роли {user_id}: {e}")
    
    # Сообщение в чат
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🎮 Игра началась! Участники: {', '.join(players.values())}\n\nРоли распределены!"
    )

def assign_roles():
    """Распределяет роли между игроками"""
    player_ids = list(players.keys())
    random.shuffle(player_ids)
    
    # Создаем сбалансированный список ролей
    roles = ["Мафия", "Комиссар", "Доктор"]
    roles += ["Мирный житель"] * (len(player_ids) - 3)
    random.shuffle(roles)
    
    return {pid: roles[i] for i, pid in enumerate(player_ids)}

def get_registration_text():
    """Формирует текст сообщения с регистрацией"""
    player_list = ", ".join(players.values()) if players else "пока никого"
    return f"🎮 Регистрация на игру\n\nЗарегистрировались: {player_list}\nИтого: {len(players)} чел."

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбрасывает игру"""
    global players, game_state, registration_msg
    
    players = {}
    game_state = "LOBBY"
    
    # Удаляем сообщение с регистрацией
    if registration_msg:
        try:
            await registration_msg.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления: {e}")
        registration_msg = None
    
    await update.message.reply_text("🛑 Игра остановлена, все данные сброшены.")

def main():
    """Запуск бота"""
    application = Application.builder().token("7595238354:AAEA1NIUS5w7-eWT1qLf8Cjq9UlcND9HwxY").build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("game", game))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CallbackQueryHandler(join, pattern="^join$"))
    
    application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
