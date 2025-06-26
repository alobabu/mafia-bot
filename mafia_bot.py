import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from mafia_game import MafiaGame

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class MafiaBot:
    def __init__(self, token):
        self.application = ApplicationBuilder().token(token).build()
        self.games = {}  # {chat_id: MafiaGame}
        self.player_choices = {}  # Для временного хранения выборов игроков
        
        # Регистрация обработчиков команд
        self.application.add_handler(CommandHandler('start', self.start))
        self.application.add_handler(CommandHandler('newgame', self.new_game))
        self.application.add_handler(CommandHandler('join', self.join))
        self.application.add_handler(CommandHandler('startgame', self.start_game))
        self.application.add_handler(CallbackQueryHandler(self.button))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            'Добро пожаловать в Мафию! Создайте новую игру командой /newgame'
        )

    async def new_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat.id
        if chat_id in self.games:
            await update.message.reply_text('Игра уже создана! Используйте /join чтобы присоединиться')
            return
        
        creator = update.message.from_user
        self.games[chat_id] = {
            'creator': creator,
            'players': [creator],
            'game': None,
            'state': 'LOBBY'
        }
        
        max_players = int(context.args[0]) if context.args and context.args[0].isdigit() else "?"
        await update.message.reply_text(
            f'Новая игра создана! Игроки могут присоединиться командой /join\n'
            f'Создатель: {creator.first_name}\n'
            f'Игроков: 1/{max_players}'
        )

    async def join(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat.id
        if chat_id not in self.games:
            await update.message.reply_text('Нет активной игры. Создайте новую командой /newgame')
            return
        
        player = update.message.from_user
        if player in self.games[chat_id]['players']:
            await update.message.reply_text('Вы уже в игре!')
            return
        
        self.games[chat_id]['players'].append(player)
        await update.message.reply_text(
            f'{player.first_name} присоединился к игре!\n'
            f'Игроков: {len(self.games[chat_id]["players"])}'
        )

    async def start_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat.id
        if chat_id not in self.games:
            await update.message.reply_text('Нет активной игры. Создайте новую командой /newgame')
            return
        
        game_data = self.games[chat_id]
        if len(game_data['players']) < 4:
            await update.message.reply_text('Недостаточно игроков (минимум 4)')
            return
        
        player_names = [p.first_name for p in game_data['players']]
        game_data['game'] = MafiaGame(player_names)
        game_data['state'] = 'NIGHT'
        
        # Отправляем роли в личные сообщения
        for player, name in zip(game_data['players'], player_names):
            try:
                role = next(p.role for p in game_data['game'].players if p.name == name)
                await context.bot.send_message(
                    chat_id=player.id,
                    text=f'Ваша роль: {role}\n\nИгра начинается!'
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения {player.id}: {e}")
        
        await self.start_night_phase(chat_id, context)

    async def start_night_phase(self, chat_id, context: ContextTypes.DEFAULT_TYPE):
        game = self.games[chat_id]['game']
        game.night_phase()
        
        # Уведомление о начале ночи
        await context.bot.send_message(
            chat_id=chat_id,
            text="🌙 Ночь наступила! Все закрывают глаза..."
        )
        
        # Организация действий игроков
        await self.organize_night_actions(chat_id, context)

    async def organize_night_actions(self, chat_id, context: ContextTypes.DEFAULT_TYPE):
        game = self.games[chat_id]['game']
        players = self.games[chat_id]['players']
        
        for player, game_player in zip(players, game.players):
            if not game_player.alive:
                continue
                
            if game_player.role == "Доктор":
                await self.request_doctor_action(player.id, game, context)
            elif game_player.role == "Мафия":
                await self.request_mafia_action(player.id, game, context)
            # ... аналогично для других ролей

    async def request_doctor_action(self, user_id, game, context: ContextTypes.DEFAULT_TYPE):
        alive_players = [p for p in game.players if p.alive]
        keyboard = []
        
        for i, p in enumerate(alive_players):
            keyboard.append([InlineKeyboardButton(p.name, callback_data=f"doctor_{i}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=user_id,
            text="Доктор, кого вы хотите вылечить сегодня ночью?",
            reply_markup=reply_markup
        )

    async def button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        if data.startswith("doctor_"):
            await self.handle_doctor_choice(user_id, int(data.split("_")[1]), context)
        # ... обработка других callback'ов

    async def handle_doctor_choice(self, user_id, choice_idx, context: ContextTypes.DEFAULT_TYPE):
        # Найти игру, где этот игрок - доктор
        for chat_id, game_data in self.games.items():
            game = game_data['game']
            if not game:
                continue
                
            doctor = next((p for p in game.players if p.name == next(
                u.first_name for u in game_data['players'] if u.id == user_id
            )), None)
            
            if doctor and doctor.role == "Доктор":
                alive_players = [p for p in game.players if p.alive]
                target = alive_players[choice_idx]
                target.protected = True
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Вы защитили {target.name}!"
                )
                break

    def run(self):
        self.application.run_polling()

if __name__ == '__main__':
    TOKEN = '8126476935:AAHtavtEbT-7jH412MaSRw8nr4LciEYGKkk'  # Замените на ваш токен
    bot = MafiaBot(TOKEN)
    bot.run()
