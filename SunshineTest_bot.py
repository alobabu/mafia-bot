import logging
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
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
day_votes = {}
day_discussion_end_time = None
voting_msg = None
revote_msg = None
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

class GameTimer:
    def __init__(self):
        self._task = None
    
    async def start(self, duration, callback, data=None):
        self.cancel()
        self._task = asyncio.create_task(self._run(duration, callback, data))
    
    async def _run(self, duration, callback, data):
        try:
            await asyncio.sleep(duration)
            await callback(data)
        except Exception as e:
            logger.error(f"Timer error: {e}")
    
    def cancel(self):
        if self._task and not self._task.done():
            self._task.cancel()

game_timer = GameTimer()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_state
    if len(players) < 4:
        await update.message.reply_text("❌ Недостаточно игроков (нужно 4+)")
        return
    game_state = "GAME"
    await start_game(update, context)

async def game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_state, registration_msg, group_chat_id
    group_chat_id = update.effective_chat.id
    
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
    
    for user_id, data in players.items():
        try:
            role_display = special_roles.get(data['role'], data['role'])
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎭 Ваша роль: {role_display}\nНе показывайте её никому!"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки роли {user_id}: {e}")

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🎮 Игра началась! Участники: {', '.join(p['name'] for p in players.values())}"
    )
    
    await start_night(update, context)

async def start_night(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_state, night_actions, night_end_time, night_number
    game_state = "NIGHT"
    night_actions = {}
    night_end_time = datetime.now() + timedelta(seconds=60)
    
    alive_players = [p for p in players.values() if p['alive']]
    player_list = "\n".join(f"{i+1}. {p['name']}" for i, p in enumerate(alive_players))
    
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
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🌙 Ночь {night_number}\n\n"
             f"Живые игроки:\n{player_list}\n\n"
             f"Из них: {', '.join(roles_text)}\n"
             f"Всего: {len(alive_players)}\n\n"
             "Специальные роли просыпаются..."
    )
    
    for user_id, data in players.items():
        if not data['alive']:
            continue
            
        if data['role'] in ["Мафия", "Дон"]:
            await send_mafia_action(user_id, context)
        elif data['role'] == "Доктор":
            await send_doctor_action(user_id, context)
        elif data['role'] == "Комиссар":
            await send_commissioner_action(user_id, context)
    
    await game_timer.start(60, end_night_wrapper, context)

async def end_night_wrapper(context):
    try:
        await end_night(context)
    except Exception as e:
        logger.error(f"End night error: {e}")
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
    """Обрабатывает ночные действия и отправляет уведомления в чат"""
    global group_chat_id, night_actions
    
    query = update.callback_query
    await query.answer()
    
    # Проверка что игра в нужной фазе
    if game_state != "NIGHT":
        await query.edit_message_text("⚠️ Сейчас не время ночных действий!")
        return
    
    user_id = query.from_user.id
    data = query.data
    
    # Проверка что игрок жив
    if not players.get(user_id, {}).get('alive', False):
        await query.edit_message_text("💀 Вы мертвы и не можете действовать!")
        return
    
    # Получаем роль с иконкой
    role = special_roles.get(players[user_id]['role'], players[user_id]['role'])
    
    try:
        if data.startswith("mafia_kill_"):
            # Обработка выбора мафии
            target_id = int(data.split("_")[2])
            if not players.get(target_id, {}).get('alive', False):
                await query.edit_message_text("⚠️ Этот игрок уже мертв!")
                return
                
            night_actions["mafia"] = {"target_id": target_id, "by": user_id}
            await query.edit_message_text("✅ Выбор сохранен (убийство)")
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=f"{role} сделал выбор... 👁️"
            )
        
        elif data.startswith("doctor_heal_"):
            # Обработка выбора доктора
            target_id = int(data.split("_")[2])
            night_actions["doctor"] = {"target_id": target_id}
            await query.edit_message_text("✅ Выбор сохранен (лечение)")
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=f"{role} готовится к ночному дежурству... 💉"
            )
        
        elif data == "com_check":
            # Обработка проверки комиссара
            targets = [
                uid for uid, data in players.items() 
                if data['alive'] and uid != user_id  # Не может проверить себя
            ]
            
            if not targets:
                await query.edit_message_text("⚠️ Нет игроков для проверки!")
                return
                
            keyboard = [
                [InlineKeyboardButton(players[uid]['name'], callback_data=f"com_check_{uid}")] 
                for uid in targets
            ]
            
            await query.edit_message_text(
                text="🔍 Кого будем проверять сегодня?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif data == "com_kill":
            # Обработка убийства комиссаром
            targets = [
                uid for uid, data in players.items() 
                if data['alive'] and data['role'] not in ["Мафия", "Дон"]
            ]
            
            if not targets:
                await query.edit_message_text("⚠️ Нет допустимых целей!")
                return
                
            keyboard = [
                [InlineKeyboardButton(players[uid]['name'], callback_data=f"com_kill_{uid}")] 
                for uid in targets
            ]
            
            await query.edit_message_text(
                text="🔫 Выберите цель для ликвидации:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif data.startswith("com_check_"):
            # Подтверждение проверки
            target_id = int(data.split("_")[2])
            night_actions["commissioner"] = {
                "action": "check", 
                "target_id": target_id,
                "by": user_id
            }
            await query.edit_message_text("🕵️ Проверка начата...")
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=f"{role} скрытно наблюдает за игроком... 🔎"
            )
        
        elif data.startswith("com_kill_"):
            # Подтверждение убийства
            target_id = int(data.split("_")[2])
            night_actions["commissioner"] = {
                "action": "kill", 
                "target_id": target_id,
                "by": user_id
            }
            await query.edit_message_text("💀 Приказ принят!")
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=f"{role} заряжает оружие... 🔫"
            )
            
        # Проверяем все ли сделали выбор
        await check_night_actions_completion(context)
            
    except Exception as e:
        logger.error(f"Ошибка в handle_night_action: {e}")
        await query.edit_message_text("❌ Произошла ошибка, попробуйте еще раз")

async def check_night_actions_completion(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет все ли роли сделали выбор"""
    alive_players = {
        uid: data for uid, data in players.items() 
        if data['alive'] and data['role'] in special_roles
    }
    
    completed = 0
    required = 0
    
    # Мафия/Дон
    if any(p['role'] in ["Мафия", "Дон"] for p in alive_players.values()):
        required += 1
        if "mafia" in night_actions:
            completed += 1
    
    # Доктор
    if any(p['role'] == "Доктор" for p in alive_players.values()):
        required += 1
        if "doctor" in night_actions:
            completed += 1
    
    # Комиссар
    if any(p['role'] == "Комиссар" for p in alive_players.values()):
        required += 1
        if "commissioner" in night_actions:
            completed += 1
    
    # Если все сделали выбор - завершаем ночь досрочно
    if completed >= required and required > 0:
        await context.bot.send_message(
            chat_id=group_chat_id,
            text="🌃 Все ночные действия завершены! Ночь окончена."
        )
        await end_night(context)

async def end_night(context: ContextTypes.DEFAULT_TYPE):
    global game_state, night_number, day_number, day_votes
    
    if game_state != "NIGHT":
        logger.warning(f"Некорректный вызов end_night из состояния {game_state}")
        return
    
    day_votes = {}
    
    killed_id = night_actions.get("mafia", {}).get("target_id")
    protected_id = night_actions.get("doctor", {}).get("target_id")
    com_action = night_actions.get("commissioner", {})
    
    death_messages = []
    
    if killed_id and killed_id != protected_id:
        players[killed_id]['alive'] = False
        killer_role = next((p['role'] for p in players.values() if p['role'] in ["Мафия", "Дон"]), "неизвестно")
        death_messages.append(
            f"☠️ Ночью был убит {players[killed_id]['name']}\n"
            f"Говорят, это сделала {special_roles.get(killer_role, killer_role)}"
        )
    
    if com_action.get("action") == "kill":
        target_id = com_action["target_id"]
        if players[target_id]['alive']:
            players[target_id]['alive'] = False
            death_messages.append(
                f"🔫 Комиссар ликвидировал {players[target_id]['name']}\n"
                "Город стал немного безопаснее..."
            )
    
    if com_action.get("action") == "check":
        target_id = com_action["target_id"]
        target_role = players[target_id]['role']
        commissioner_id = next((uid for uid, data in players.items() if data['role'] == "Комиссар"), None)
        if commissioner_id:
            await context.bot.send_message(
                chat_id=commissioner_id,
                text=f"🔍 Результат проверки: {players[target_id]['name']} - {special_roles.get(target_role, target_role)}"
            )
    
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
    
    await context.bot.send_message(
        chat_id=group_chat_id,
        text=morning_message
    )
    
    await check_game_over(None, context)
    if game_state == "GAME":
        await start_day_discussion(None, context)

async def start_day_discussion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_state, day_discussion_end_time
    
    if game_state != "NIGHT":
        logger.warning(f"Некорректный вызов start_day_discussion из состояния {game_state}")
        return
    
    game_state = "DAY_DISCUSSION"
    day_discussion_end_time = datetime.now() + timedelta(seconds=60)
    
    alive_players = [p for p in players.values() if p['alive']]
    roles_present = {}
    for p in players.values():
        if p['alive']:
            role = special_roles.get(p['role'], p['role'])
            roles_present[role] = roles_present.get(role, 0) + 1
    
    roles_text = ", ".join(f"{role} - {count}" if count > 1 else role 
                          for role, count in roles_present.items())
    
    await context.bot.send_message(
        chat_id=group_chat_id,
        text=f"🌇 День {day_number}\n\n"
             f"Живые игроки ({len(alive_players)}):\n" + 
             "\n".join(f"▫️ {p['name']}" for p in alive_players) + 
             f"\n\nОставшиеся роли: {roles_text}\n\n"
             "У вас есть 60 секунд на обсуждение..."
    )
    
    await game_timer.start(60, start_voting_wrapper, context)

async def start_voting_wrapper(context):
    try:
        await start_voting(context)
    except Exception as e:
        logger.error(f"Start voting error: {e}")

async def start_voting(context: ContextTypes.DEFAULT_TYPE):
    global game_state, voting_msg
    
    if game_state != "DAY_DISCUSSION":
        logger.warning(f"Некорректный вызов start_voting из состояния {game_state}")
        return
    
    game_state = "VOTING"
    
    alive_players = [p for p in players.values() if p['alive']]
    
    voting_msg = await context.bot.send_message(
        chat_id=group_chat_id,
        text="🕒 Время обсуждения истекло! Начинаем голосование.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Проголосовать", callback_data="start_voting")]
        ])
    )
    
    await game_timer.start(60, end_voting_wrapper, context)

async def end_voting_wrapper(context):
    try:
        await end_voting(context)
    except Exception as e:
        logger.error(f"End voting error: {e}")

async def end_voting(context: ContextTypes.DEFAULT_TYPE):
    global game_state, voting_msg, revote_msg
    
    if game_state != "VOTING":
        logger.warning(f"Некорректный вызов end_voting из состояния {game_state}")
        return
    
    vote_count = {}
    for target_id in day_votes.values():
        if target_id is not None:
            vote_count[target_id] = vote_count.get(target_id, 0) + 1
    
    if not vote_count:
        await context.bot.send_message(
            chat_id=group_chat_id,
            text="🕒 Голосование окончено\n\n"
                 "Мнения жителей разошлись... Разошлись и сами жители, так никого и не повесив..."
        )
        await start_night(None, context)
        return
    
    max_votes = max(vote_count.values())
    candidates = [uid for uid, count in vote_count.items() if count == max_votes]
    
    if len(candidates) > 1:
        await context.bot.send_message(
            chat_id=group_chat_id,
            text="🕒 Голосование окончено\n\n"
                 "Мнения жителей разошлись... Разошлись и сами жители, так никого и не повесив..."
        )
        await start_night(None, context)
        return
    
    target_id = candidates[0]
    target_name = players[target_id]['name']
    
    revote_msg = await context.bot.send_message(
        chat_id=group_chat_id,
        text=f"🔎 Вы точно уверены, что хотите линчевать {target_name}?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👍 Да", callback_data=f"revote_yes_{target_id}"),
             InlineKeyboardButton("👎 Нет", callback_data="revote_no")]
        ])
    )
    
    await game_timer.start(30, finalize_voting_wrapper, (None, target_id))

async def finalize_voting_wrapper(data):
    try:
        await finalize_voting(data)
    except Exception as e:
        logger.error(f"Finalize voting error: {e}")

async def finalize_voting(context: ContextTypes.DEFAULT_TYPE):
    update, target_id = context
    
    if revote_msg:
        try:
            await revote_msg.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")
    
    await context.bot.send_message(
        chat_id=group_chat_id,
        text="🕒 Время на подтверждение истекло, голосование отменено"
    )
    await start_night(update, context)

async def handle_voting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == "start_voting":
        alive_players = [uid for uid, data in players.items() if data['alive']]
        
        keyboard = [
            [InlineKeyboardButton(players[uid]['name'], callback_data=f"vote_{uid}")] 
            for uid in alive_players
        ]
        keyboard.append([InlineKeyboardButton("Пропустить", callback_data="vote_skip")])
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="🗳 Выберите, кого линчевать:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await query.edit_message_text("✅ Вы перешли к голосованию")
        except Exception as e:
            logger.error(f"Ошибка отправки голосования {user_id}: {e}")
    
    elif query.data.startswith("vote_"):
        target = query.data.split("_")[1]
        player_name = players[user_id]['name']
        
        if target == "skip":
            day_votes[user_id] = None
            await query.edit_message_text("✅ Вы пропустили голосование")
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=f"🗳 {player_name} пропустил(а) голосование"
            )
        else:
            target_id = int(target)
            target_name = players[target_id]['name']
            day_votes[user_id] = target_id
            await query.edit_message_text(f"✅ Вы проголосовали за {target_name}")
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=f"🗳 {player_name} проголосовал(а) за: {target_name}"
            )

async def handle_revote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("revote_yes_"):
        target_id = int(query.data.split("_")[2])
        target_name = players[target_id]['name']
        target_role = players[target_id]['role']
        role_display = special_roles.get(target_role, target_role)
        
        players[target_id]['alive'] = False
        
        await context.bot.send_message(
            chat_id=group_chat_id,
            text=f"💀 {target_name} был повешен! Его роль: {role_display}"
        )
        
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"💀 Вы были повешены! Ваша роль: {role_display}"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения повешенному {target_id}: {e}")
        
        await check_game_over(update, context)
        if game_state == "GAME":
            await start_night(update, context)
        
    elif query.data == "revote_no":
        await query.edit_message_text("🕒 Голосование отменено")
        await context.bot.send_message(
            chat_id=group_chat_id,
            text="🕒 Голосование окончено\n\n"
                 "Мнения жителей разошлись... Разошлись и сами жители, так никого и не повесив..."
        )
        await start_night(update, context)

async def check_game_over(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_state
    
    mafia_count = sum(1 for data in players.values() if data['role'] in ["Мафия", "Дон"] and data['alive'])
    civilians_count = sum(1 for data in players.values() if data['role'] not in ["Мафия", "Дон"] and data['alive'])
    
    if mafia_count == 0:
        await context.bot.send_message(
            chat_id=group_chat_id,
            text="🎉 Мирные жители победили! Мафия уничтожена!"
        )
        await stop_game(update, context)
    elif mafia_count >= civilians_count:
        await context.bot.send_message(
            chat_id=group_chat_id,
            text="😈 Мафия победила! Мирные жители проиграли!"
        )
        await stop_game(update, context)

async def stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global players, game_state, registration_msg, night_actions, day_number, night_number
    
    # Определяем победителей
    mafia_alive = any(data['alive'] and data['role'] in ["Мафия", "Дон"] for data in players.values())
    
    winners = []
    losers = []
    
    for user_id, data in players.items():
        role_display = special_roles.get(data['role'], data['role'])
        player_info = f"{data['name']} - {role_display}"
        
        if mafia_alive:  # Победила мафия
            if data['role'] in ["Мафия", "Дон"]:
                winners.append(player_info)
            else:
                losers.append(player_info)
        else:  # Победили мирные
            if data['role'] not in ["Мафия", "Дон"]:
                winners.append(player_info)
            else:
                losers.append(player_info)
    
    # Формируем итоговое сообщение
    result_message = "🏆 Игра окончена! 🏆\n\n"
    result_message += "🎉 ПОБЕДИТЕЛИ:\n" + "\n".join(f"▫️ {winner}" for winner in winners) + "\n\n"
    result_message += "😞 ОСТАЛЬНЫЕ ИГРОКИ:\n" + "\n".join(f"▫️ {loser}" for loser in losers)
    
    # Отправляем результаты
    await context.bot.send_message(
        chat_id=group_chat_id,
        text=result_message
    )
    
    # Сбрасываем состояние игры
    game_timer.cancel()
    players = {}
    game_state = "LOBBY"
    registration_msg = None
    night_actions = {}
    day_number = 0
    night_number = 0

def assign_roles():
    player_ids = list(players.keys())
    random.shuffle(player_ids)
    
    roles = ["Мафия", "Доктор", "Комиссар"]
    
    if len(player_ids) >= 6:
        roles.append("Дон")
    
    roles += ["Мирный житель"] * (len(player_ids) - len(roles))
    random.shuffle(roles)
    
    for i, user_id in enumerate(player_ids):
        players[user_id]['role'] = roles[i]

def get_players_list():
    return ", ".join(p['name'] for p in players.values()) if players else "пока никого"

def main():
    application = Application.builder().token("7595238354:AAEA1NIUS5w7-eWT1qLf8Cjq9UlcND9HwxY").build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("game", game))
    application.add_handler(CommandHandler("stop", stop_game))
    application.add_handler(CallbackQueryHandler(join, pattern="^join$"))
    application.add_handler(CallbackQueryHandler(handle_night_action))
    application.add_handler(CallbackQueryHandler(handle_voting, pattern="^(start_voting|vote_)"))
    application.add_handler(CallbackQueryHandler(handle_revote, pattern="^revote_"))
    
    application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
