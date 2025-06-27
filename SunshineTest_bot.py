import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio
from datetime import datetime, timedelta

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальные переменные
players = {}
game_state = "LOBBY"
registration_msg = None
night_actions = {}
night_end_time = None
day_number = 0
night_number = 0
group_chat_id = None
special_roles = {
    "Мафия": "🤵🏼 Мафия",
    "Дон": "🤵🏻 Дон",
    "Доктор": "👨🏼‍⚕️ Доктор",
    "Комиссар": "🕵🏼 Комиссар",
    "Мирный житель": "👨🏼 Мирный Житель"
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    global game_state
    
    if len(players) < 4:
        await update.message.reply_text("❌ Недостаточно игроков (нужно 4+)")
        return
    
    game_state = "GAME"
    await start_game(update, context)

async def game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает регистрацию"""
    global game_state, registration_msg, group_chat_id
    
    group_chat_id = update.effective_chat.id  # Сохраняем ID группового чата
    
    if game_state == "GAME":
        await update.message.reply_text("Игра уже идет!")
        return
    
    if registration_msg:
        try:
            await registration_msg.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")
    
    game_state = "REGISTRATION"
    registration_msg = await update.message.reply_text(
        "🎮 Регистрация на игру:\n\n" + get_players_list(),
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
        players[user.id] = {
            "name": user.first_name,
            "role": None,
            "alive": True,
            "protected": False
        }
        
        await registration_msg.edit_text(
            text="🎮 Регистрация на игру:\n\n" + get_players_list(),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Присоединиться", callback_data="join")]
            ])
        )
        
        await context.bot.send_message(
            chat_id=user.id,
            text="✅ Вы успешно зарегистрировались в игре!"
        )
        
        if len(players) >= 4:
            await start_game(update, context)
    else:
        await query.edit_message_text("⚠️ Вы уже зарегистрированы!")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает игру"""
    global game_state, registration_msg, night_number, day_number
    
    game_state = "GAME"
    night_number = 1
    day_number = 0
    
    if registration_msg:
        try:
            await registration_msg.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления: {e}")
        registration_msg = None
    
    assign_roles()
    
    # Отправляем роли в ЛС игрокам
    for user_id, data in players.items():
        try:
            role_display = special_roles.get(data['role'], data['role'])
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎭 Ваша роль: {role_display}\nНе показывайте её никому!"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки роли {user_id}: {e}")

    # Отправляем стартовое сообщение в чат
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🎮 Игра началась! Участники: {', '.join(p['name'] for p in players.values())}"
    )
    
    await start_night(update, context)

async def start_night(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает ночную фазу"""
    global game_state, night_actions, night_end_time, night_number
    
    game_state = "NIGHT"
    night_actions = {}
    night_end_time = datetime.now() + timedelta(seconds=60)
    
    # Формируем список живых игроков
    alive_players = [p for p in players.values() if p['alive']]
    player_list = "\n".join(f"{i+1}. {p['name']}" for i, p in enumerate(alive_players))
    
    # Формируем список ролей (без привязки к игрокам)
    roles_present = {}
    for p in players.values():
        if p['alive']:
            role = special_roles.get(p['role'], p['role'])
            roles_present[role] = roles_present.get(role, 0) + 1
    
    roles_text = []
    for role, count in roles_present.items():
        if count > 1:
            roles_text.append(f"{role} - {count}")
        else:
            roles_text.append(role)
    
    # Отправляем в чат
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🌙 Ночь {night_number}\n\n"
             f"Живые игроки:\n{player_list}\n\n"
             f"Из них: {', '.join(roles_text)}\n"
             f"Всего: {len(alive_players)}\n\n"
             "Специальные роли просыпаются..."
    )
    
    # Отправляем действия ролям
    for user_id, data in players.items():
        if not data['alive']:
            continue
            
        if data['role'] in ["Мафия", "Дон"]:
            await send_mafia_action(user_id, context)
        elif data['role'] == "Доктор":
            await send_doctor_action(user_id, context)
        elif data['role'] == "Комиссар":
            await send_commissioner_action(user_id, context)
    
    # Запускаем таймер ночи
    context.job_queue.run_once(end_night, 60, data=update)

async def send_mafia_action(user_id, context):
    """Отправляет действие мафии"""
    targets = [uid for uid, data in players.items() 
              if data['alive'] and data['role'] not in ["Мафия", "Дон"]]
    
    keyboard = [[InlineKeyboardButton(players[uid]['name'], callback_data=f"mafia_kill_{uid}")] for uid in targets]
    
    await context.bot.send_message(
        chat_id=user_id,
        text="🔪 Выберите, кого убить:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def send_doctor_action(user_id, context):
    """Отправляет действие доктора"""
    targets = [uid for uid, data in players.items() if data['alive']]
    
    keyboard = [[InlineKeyboardButton(players[uid]['name'], callback_data=f"doctor_heal_{uid}")] for uid in targets]
    
    await context.bot.send_message(
        chat_id=user_id,
        text="💊 Кого вы хотите вылечить?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def send_commissioner_action(user_id, context):
    """Отправляет действие комиссара"""
    await context.bot.send_message(
        chat_id=user_id,
        text="🕵️ Выберите действие:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Проверить игрока", callback_data="com_check")],
            [InlineKeyboardButton("Убить игрока", callback_data="com_kill")]
        ])
    )

async def handle_night_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ночные действия и отправляет уведомления в групповой чат"""
    global group_chat_id, night_actions
    
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    # Получаем роль игрока для уведомлений
    role = special_roles.get(players[user_id]['role'], players[user_id]['role'])
    
    if data.startswith("mafia_kill_"):
        # Обработка выбора мафии
        target_id = int(data.split("_")[2])
        night_actions["mafia"] = {"target_id": target_id}
        
        await query.edit_message_text("✅ Выбор сделан (ваше решение отправлено в чат)")
        await context.bot.send_message(
            chat_id=group_chat_id,
            text=f"{role} выбрал жертву... 👁️"
        )
    
    elif data.startswith("doctor_heal_"):
        # Обработка выбора доктора
        target_id = int(data.split("_")[2])
        night_actions["doctor"] = {"target_id": target_id}
        
        await query.edit_message_text("✅ Выбор сделан (ваше решение отправлено в чат)")
        await context.bot.send_message(
            chat_id=group_chat_id,
            text=f"{role} вышел на ночную смену... 💉"
        )
    
    elif data == "com_check":
        # Обработка проверки комиссара
        targets = [uid for uid, data in players.items() 
                 if data['alive'] and data['role'] not in ["Мафия", "Дон"]]
        
        keyboard = [[InlineKeyboardButton(players[uid]['name'], callback_data=f"com_check_{uid}")] 
                  for uid in targets]
        
        await query.edit_message_text(
            text="🔍 Выберите игрока для проверки:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )  # Закрывающие скобки для edit_message_text
    
    elif data == "com_kill":
        # Обработка убийства комиссаром
        targets = [uid for uid, data in players.items() 
                 if data['alive'] and data['role'] not in ["Мафия", "Дон"]]
        
        keyboard = [[InlineKeyboardButton(players[uid]['name'], callback_data=f"com_kill_{uid}")] 
                  for uid in targets]
        
        await query.edit_message_text(
            text="🔫 Выберите игрока для убийства:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )  # Закрывающие скобки для edit_message_text
    
    elif data.startswith("com_check_"):
        # Подтверждение проверки комиссара
        target_id = int(data.split("_")[2])
        night_actions["commissioner"] = {"action": "check", "target_id": target_id}
        
        await query.edit_message_text("✅ Проверка начата (результат придет вам лично)")
        await context.bot.send_message(
            chat_id=group_chat_id,
            text=f"{role} начал проверку... 🔎"
        )
    
    elif data.startswith("com_kill_"):
        # Подтверждение убийства комиссаром
        target_id = int(data.split("_")[2])
        night_actions["commissioner"] = {"action": "kill", "target_id": target_id}
        
        await query.edit_message_text("✅ Приказ на устранение отдан (результат будет в чате)")
        await context.bot.send_message(
            chat_id=group_chat_id,
            text=f"{role} приготовил пистолет... 🔫"
        )

async def end_night(context: ContextTypes.DEFAULT_TYPE):
    """Завершает ночную фазу и публикует результаты в чат"""
    global game_state, night_number, day_number, group_chat_id
    
    update = context.job.data
    
    # Обработка действий
    killed_id = night_actions.get("mafia", {}).get("target_id")
    protected_id = night_actions.get("doctor", {}).get("target_id")
    com_action = night_actions.get("commissioner", {})
    
    # Сообщение о смерти
    death_messages = []
    
    # Обработка убийства мафии
    if killed_id and killed_id != protected_id:
        players[killed_id]['alive'] = False
        killer_role = next((p['role'] for p in players.values() if p['role'] in ["Мафия", "Дон"]), "неизвестно")
        death_messages.append(
            f"☠️ Ночью был убит {players[killed_id]['name']}\n"
            f"Говорят, это сделала {special_roles.get(killer_role, killer_role)}"
        )
    
    # Обработка убийства комиссаром
    if com_action.get("action") == "kill":
        target_id = com_action["target_id"]
        if players[target_id]['alive']:  # Проверяем, не защищен ли цель доктором
            players[target_id]['alive'] = False
            death_messages.append(
                f"🔫 Комиссар ликвидировал {players[target_id]['name']}\n"
                "Город стал немного безопаснее..."
            )
    
    # Обработка проверки комиссара
    if com_action.get("action") == "check":
        target_id = com_action["target_id"]
        target_role = players[target_id]['role']
        commissioner_id = next((uid for uid, data in players.items() if data['role'] == "Комиссар"), None)
        if commissioner_id:
            await context.bot.send_message(
                chat_id=commissioner_id,
                text=f"🔍 Результат проверки: {players[target_id]['name']} - {special_roles.get(target_role, target_role)}"
            )
    
    # Формируем утреннее сообщение
    day_number += 1
    alive_players = [p['name'] for p in players.values() if p['alive']]
    
    morning_message = (
        f"🌞 Утро {day_number}\n"
        "Солнце восходит, подсушивая на тротуарах пролитую ночью кровь...\n\n"
    )
    
    if death_messages:
        morning_message += "\n".join(death_messages) + "\n\n"
    else:
        morning_message += "Этой ночью никто не погиб.\n\n"
    
    morning_message += f"🏘 Живые игроки ({len(alive_players)}):\n" + "\n".join(f"▫️ {name}" for name in alive_players)
    
    # Отправляем результаты в групповой чат
    await context.bot.send_message(
        chat_id=group_chat_id,
        text=morning_message
    )
    
    # Проверяем конец игры
    await check_game_over(update, context)

async def check_game_over(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет условия окончания игры"""
    mafia_count = sum(1 for data in players.values() if data['role'] in ["Мафия", "Дон"] and data['alive'])
    civilians_count = sum(1 for data in players.values() if data['role'] not in ["Мафия", "Дон"] and data['alive'])
    
    if mafia_count == 0:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🎉 Мирные жители победили! Мафия уничтожена!"
        )
        await stop_game(update, context)
    elif mafia_count >= civilians_count:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="😈 Мафия победила! Мирные жители проиграли!"
        )
        await stop_game(update, context)
    else:
        game_state = "DAY"

async def stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбрасывает игру"""
    global players, game_state, registration_msg, night_actions, day_number, night_number
    
    players = {}
    game_state = "LOBBY"
    registration_msg = None
    night_actions = {}
    day_number = 0
    night_number = 0
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🛑 Игра остановлена, все данные сброшены."
    )

def assign_roles():
    """Распределяет только базовые роли"""
    player_ids = list(players.keys())
    random.shuffle(player_ids)
    
    # Базовые роли
    roles = ["Мафия", "Доктор", "Комиссар"]
    
    # Добавляем Дона если игроков достаточно (6+)
    if len(player_ids) >= 6:
        roles.append("Дон")
    
    # Остальные - мирные жители
    roles += ["Мирный житель"] * (len(player_ids) - len(roles))
    random.shuffle(roles)
    
    for i, user_id in enumerate(player_ids):
        players[user_id]['role'] = roles[i]

def get_players_list():
    """Возвращает список игроков через запятую"""
    return ", ".join(p['name'] for p in players.values()) if players else "пока никого"

def main():
    """Запуск бота"""
    application = Application.builder().token("7595238354:AAEA1NIUS5w7-eWT1qLf8Cjq9UlcND9HwxY").build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("game", game))
    application.add_handler(CommandHandler("stop", stop_game))
    application.add_handler(CallbackQueryHandler(join, pattern="^join$"))
    application.add_handler(CallbackQueryHandler(handle_night_action))
    
    application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
