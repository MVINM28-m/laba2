# main.py (исправленная версия)

import asyncio
import logging
import sqlite3
import os
import sys
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

# Получаем токен и ID администратора
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None

if not BOT_TOKEN:
    logger.error("BOT_TOKEN не найден в .env файле")
    sys.exit(1)

if not ADMIN_ID:
    logger.error("ADMIN_ID не найден в .env файле")
    sys.exit(1)

logger.info(f"✅ Конфигурация загружена успешно")
logger.info(f"👑 ID администратора: {ADMIN_ID}")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Определение состояний для FSM
class HabitStates(StatesGroup):
    waiting_for_habit_name = State()
    waiting_for_habit_description = State()


# Состояние для рассылки
class BroadcastStates(StatesGroup):
    waiting_for_message = State()


# Класс для работы с базой данных
class Database:
    def __init__(self, db_name="habits.db"):
        self.db_name = db_name
        self.init_db()
        logger.info(f"✅ База данных инициализирована: {db_name}")

    def get_connection(self):
        return sqlite3.connect(self.db_name)

    def init_db(self):
        """Инициализация таблиц базы данных"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Таблица пользователей
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        registered_date TEXT,
                        is_admin INTEGER DEFAULT 0
                    )
                """
                )

                # Таблица привычек
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS habits (
                        habit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        habit_name TEXT,
                        habit_description TEXT,
                        created_date TEXT,
                        is_active INTEGER DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                """
                )

                # Таблица выполнения привычек
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS habit_tracking (
                        tracking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        habit_id INTEGER,
                        track_date TEXT,
                        status TEXT,  -- 'completed', 'missed'
                        FOREIGN KEY (habit_id) REFERENCES habits (habit_id),
                        UNIQUE(habit_id, track_date)
                    )
                """
                )

                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка при инициализации БД: {e}")
            raise

    def add_user(self, user_id, username, first_name, last_name):
        """Добавление нового пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Проверяем, является ли пользователь администратором
                is_admin = 1 if user_id == ADMIN_ID else 0

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, registered_date, is_admin)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (user_id, username, first_name, last_name, date.today().isoformat(), is_admin),
                )

                # Если пользователь уже существует, обновляем его статус администратора
                cursor.execute(
                    """
                    UPDATE users SET 
                        username = ?,
                        first_name = ?,
                        last_name = ?,
                        is_admin = ?
                    WHERE user_id = ?
                    """,
                    (username, first_name, last_name, is_admin, user_id)
                )

                conn.commit()
                logger.info(f"👤 Новый пользователь: {first_name} (ID: {user_id})")
        except Exception as e:
            logger.error(f"Ошибка при добавлении пользователя: {e}")

    def get_user(self, user_id):
        """Получение информации о пользователе"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Ошибка при получении пользователя: {e}")
            return None

    def add_habit(self, user_id, habit_name, habit_description):
        """Добавление новой привычки"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO habits (user_id, habit_name, habit_description, created_date)
                    VALUES (?, ?, ?, ?)
                """,
                    (user_id, habit_name, habit_description, date.today().isoformat()),
                )
                conn.commit()
                habit_id = cursor.lastrowid
                logger.info(f"📝 Новая привычка: {habit_name} (ID: {habit_id}) для пользователя {user_id}")
                return habit_id
        except Exception as e:
            logger.error(f"Ошибка при добавлении привычки: {e}")
            return None

    def get_user_habits(self, user_id):
        """Получение всех привычек пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT habit_id, habit_name, habit_description, created_date, is_active
                    FROM habits
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY created_date DESC
                """,
                    (user_id,),
                )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка при получении привычек: {e}")
            return []

    def get_habit(self, habit_id):
        """Получение информации о привычке"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM habits WHERE habit_id = ?", (habit_id,)
                )
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Ошибка при получении привычки: {e}")
            return None

    def track_habit(self, habit_id, status):
        """Отметка выполнения привычки"""
        today = date.today().isoformat()
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        """
                        INSERT INTO habit_tracking (habit_id, track_date, status)
                        VALUES (?, ?, ?)
                    """,
                        (habit_id, today, status),
                    )
                    conn.commit()
                    logger.info(f"✅ Привычка {habit_id} отмечена как {status} за {today}")
                    return True
                except sqlite3.IntegrityError:
                    # Обновляем существующую запись за сегодня
                    cursor.execute(
                        """
                        UPDATE habit_tracking
                        SET status = ?
                        WHERE habit_id = ? AND track_date = ?
                    """,
                        (status, habit_id, today),
                    )
                    conn.commit()
                    logger.info(f"🔄 Привычка {habit_id} обновлена на {status} за {today}")
                    return False
        except Exception as e:
            logger.error(f"Ошибка при отметке привычки: {e}")
            return False

    def get_today_status(self, habit_id):
        """Проверка, отмечал ли пользователь привычку сегодня"""
        today = date.today().isoformat()
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT status FROM habit_tracking
                    WHERE habit_id = ? AND track_date = ?
                """,
                    (habit_id, today),
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка при получении статуса: {e}")
            return None

    def get_streak(self, habit_id):
        """Подсчет непрерывной серии выполнения привычки"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT track_date, status FROM habit_tracking
                    WHERE habit_id = ?
                    ORDER BY track_date DESC
                """,
                    (habit_id,),
                )
                records = cursor.fetchall()

                if not records:
                    return 0

                streak = 0
                current_date = date.today()

                for record in records:
                    record_date = date.fromisoformat(record[0])
                    status = record[1]

                    if record_date == current_date and status == "completed":
                        streak += 1
                        current_date = current_date - timedelta(days=1)
                    elif status == "completed" and record_date == current_date:
                        streak += 1
                        current_date = current_date - timedelta(days=1)
                    else:
                        break

                return streak
        except Exception as e:
            logger.error(f"Ошибка при подсчете серии: {e}")
            return 0

    def get_all_users(self):
        """Получение всех пользователей (для админа)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id, first_name, username, is_admin, registered_date 
                    FROM users 
                    ORDER BY registered_date DESC
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка при получении списка пользователей: {e}")
            return []

    def get_habit_stats(self, habit_id):
        """Получение статистики по привычке"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT 
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_count,
                        COUNT(CASE WHEN status = 'missed' THEN 1 END) as missed_count,
                        MIN(track_date) as first_track,
                        MAX(track_date) as last_track
                    FROM habit_tracking
                    WHERE habit_id = ?
                """,
                    (habit_id,),
                )
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            return None


# Инициализация базы данных
db = Database()


# Проверка на администратора
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# Клавиатуры
def get_main_keyboard(user_id: int = None):
    """Основная клавиатура с инлайн кнопками"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="📋 Мои привычки", callback_data="my_habits"),
        InlineKeyboardButton(text="➕ Новая привычка", callback_data="new_habit")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
        InlineKeyboardButton(text="❓ Помощь", callback_data="help")
    )

    if user_id and is_admin(user_id):
        builder.row(
            InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel")
        )

    return builder.as_markup()


def get_habit_action_keyboard(habit_id: int, today_status: str = None):
    """Клавиатура действий с привычкой"""
    builder = InlineKeyboardBuilder()

    # Кнопки отметки выполнения
    if today_status != "completed":
        builder.row(
            InlineKeyboardButton(text="✅ Выполнено", callback_data=f"complete_{habit_id}")
        )
    if today_status != "missed":
        builder.row(
            InlineKeyboardButton(text="❌ Пропущено", callback_data=f"miss_{habit_id}")
        )

    builder.row(
        InlineKeyboardButton(text="📊 Статистика привычки", callback_data=f"habit_stats_{habit_id}")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад к списку", callback_data="my_habits")
    )

    return builder.as_markup()


def get_admin_keyboard():
    """Клавиатура для администратора"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_users"),
        InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin_stats")
    )
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
    )
    return builder.as_markup()


# Обработчики команд
@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    """Обработчик команды /start"""
    user = message.from_user

    # Добавляем пользователя в базу данных
    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    # Приветствие с обращением по имени
    greeting = (
        f"👋 Привет, {user.first_name}!\n\n"
        f"Я бот-трекер привычек. Помогу тебе отслеживать выполнение ежедневных задач и формировать полезные привычки.\n\n"
        f"Выбери действие с помощью кнопок ниже:"
    )

    await message.answer(
        greeting,
        reply_markup=get_main_keyboard(user.id)
    )


@dp.message(Command("help"))
async def command_help_handler(message: types.Message) -> None:
    """Обработчик команды /help"""
    help_text = (
        "📚 <b>Справка по использованию бота</b>\n\n"
        "Команды:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать это сообщение\n"
        "/stop - Остановить бота (завершить сессию)\n"
        "/menu - Главное меню\n\n"
        "Как пользоваться:\n"
        "• Создайте новую привычку через кнопку '➕ Новая привычка'\n"
        "• Ежедневно отмечайте выполнение или пропуск привычки\n"
        "• Следите за своей статистикой и серией выполнений\n"
        "• Формируйте полезные привычки!"
    )
    await message.answer(help_text, parse_mode="HTML")


@dp.message(Command("stop"))
async def command_stop_handler(message: types.Message, state: FSMContext) -> None:
    """Обработчик команды /stop"""
    await state.clear()
    await message.answer(
        "👋 Сессия завершена. Чтобы начать заново, нажми /start",
        reply_markup=ReplyKeyboardRemove()
    )


@dp.message(Command("menu"))
async def command_menu_handler(message: types.Message) -> None:
    """Обработчик команды /menu"""
    await message.answer(
        "Главное меню:",
        reply_markup=get_main_keyboard(message.from_user.id)
    )


# Обработчики callback-запросов - ВАЖНО: порядок имеет значение!
# Сначала идут более конкретные обработчики, потом общие

@dp.callback_query(F.data == "my_habits")
async def callback_my_habits(callback: types.CallbackQuery):
    """Показать список привычек пользователя"""
    user_id = callback.from_user.id
    habits = db.get_user_habits(user_id)

    if not habits:
        await callback.message.edit_text(
            "📭 У вас пока нет созданных привычек.\n\n"
            "Создайте первую привычку через кнопку '➕ Новая привычка'",
            reply_markup=get_main_keyboard(user_id)
        )
    else:
        text = "📋 <b>Ваши привычки:</b>\n\n"
        builder = InlineKeyboardBuilder()

        for habit in habits:
            habit_id, habit_name, habit_desc, created_date, is_active = habit
            today_status = db.get_today_status(habit_id)
            status_emoji = "✅" if today_status == "completed" else "❌" if today_status == "missed" else "⚪️"

            text += f"{status_emoji} <b>{habit_name}</b>\n"
            text += f"   📝 {habit_desc[:50]}...\n"
            text += f"   📅 Создана: {created_date}\n\n"

            builder.row(
                InlineKeyboardButton(
                    text=f"{status_emoji} {habit_name}",
                    callback_data=f"habit_{habit_id}"
                )
            )

        builder.row(
            InlineKeyboardButton(text="➕ Новая привычка", callback_data="new_habit"),
            InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
        )

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )

    await callback.answer()


@dp.callback_query(F.data == "new_habit")
async def callback_new_habit(callback: types.CallbackQuery, state: FSMContext):
    """Начать создание новой привычки"""
    await callback.message.edit_text(
        "📝 Введите название новой привычки:"
    )
    await state.set_state(HabitStates.waiting_for_habit_name)
    await callback.answer()


@dp.callback_query(F.data == "stats")
async def callback_stats(callback: types.CallbackQuery):
    """Показать общую статистику пользователя"""
    user_id = callback.from_user.id
    habits = db.get_user_habits(user_id)

    if not habits:
        await callback.message.edit_text(
            "📭 У вас нет привычек для отображения статистики.",
            reply_markup=get_main_keyboard(user_id)
        )
    else:
        text = "📊 <b>Общая статистика:</b>\n\n"
        total_habits = len(habits)
        active_habits = 0
        total_streak = 0

        for habit in habits:
            habit_id, habit_name, _, _, _ = habit
            streak = db.get_streak(habit_id)
            if streak > 0:
                active_habits += 1
                total_streak += streak

        text += f"Всего привычек: {total_habits}\n"
        text += f"Активных сегодня: {active_habits}\n"
        text += f"Общая серия выполнений: {total_streak} дней\n\n"

        # Статистика по каждой привычке
        text += "📈 <b>Детальная статистика:</b>\n"
        for habit in habits:
            habit_id, habit_name, _, _, _ = habit
            streak = db.get_streak(habit_id)
            stats = db.get_habit_stats(habit_id)

            if stats and stats[0]:
                text += f"• {habit_name}: {streak} дней подряд (всего выполнено: {stats[0]})\n"
            else:
                text += f"• {habit_name}: пока нет данных\n"

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_main_keyboard(user_id)
        )

    await callback.answer()


@dp.callback_query(F.data == "help")
async def callback_help(callback: types.CallbackQuery):
    """Показать справку"""
    help_text = (
        "📚 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ Создайте привычку через кнопку '➕ Новая привычка'\n"
        "2️⃣ Каждый день отмечайте выполнение или пропуск\n"
        "3️⃣ Следите за серией выполнений в статистике\n"
        "4️⃣ Чем длиннее серия, тем лучше привычка закрепляется!\n\n"
        "<b>Совет:</b> Начинайте с одной привычки и постепенно добавляйте новые"
    )
    await callback.message.edit_text(
        help_text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(callback.from_user.id)
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_main")
async def callback_back_to_main(callback: types.CallbackQuery):
    """Вернуться в главное меню"""
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=get_main_keyboard(callback.from_user.id)
    )
    await callback.answer()


# Обработчики для привычек - ВАЖНО: сначала более специфичные
@dp.callback_query(F.data.startswith("habit_stats_"))
async def callback_habit_stats(callback: types.CallbackQuery):
    """Показать статистику по конкретной привычке"""
    try:
        habit_id = int(callback.data.split("_")[2])
        habit = db.get_habit(habit_id)
        stats = db.get_habit_stats(habit_id)
        streak = db.get_streak(habit_id)

        if not habit:
            await callback.answer("Привычка не найдена", show_alert=True)
            return

        text = f"<b>📊 Статистика: {habit[2]}</b>\n\n"

        if stats and stats[0] is not None:
            text += f"✅ Выполнено: {stats[0]} раз\n"
            text += f"❌ Пропущено: {stats[1]} раз\n"
            text += f"🔥 Текущая серия: {streak} дней\n"
            text += f"📅 Первое выполнение: {stats[2]}\n"
            text += f"📅 Последнее выполнение: {stats[3]}\n\n"

            # Процент выполнения
            total = stats[0] + stats[1]
            if total > 0:
                percent = (stats[0] / total) * 100
                text += f"📈 Процент выполнения: {percent:.1f}%"
        else:
            text += "Пока нет данных для статистики"

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад к привычке", callback_data=f"habit_{habit_id}")],
                    [InlineKeyboardButton(text="◀️ К списку привычек", callback_data="my_habits")]
                ]
            )
        )
    except Exception as e:
        logger.error(f"Ошибка в статистике привычки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("complete_"))
async def callback_complete_habit(callback: types.CallbackQuery):
    """Отметить привычку как выполненную"""
    try:
        habit_id = int(callback.data.split("_")[1])
        is_new = db.track_habit(habit_id, "completed")

        if is_new:
            message = "✅ Отлично! Привычка отмечена как выполненная!"
        else:
            message = "✅ Статус обновлен на 'Выполнено'"

        # Обновляем статистику
        streak = db.get_streak(habit_id)

        await callback.answer(message, show_alert=False)

        # Обновляем сообщение
        habit = db.get_habit(habit_id)
        text = (
            f"<b>{habit[2]}</b>\n\n"
            f"✅ Отмечено как выполненное!\n"
            f"🔥 Текущая серия: {streak} дней"
        )

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_habit_action_keyboard(habit_id, "completed")
        )
    except Exception as e:
        logger.error(f"Ошибка при отметке выполнения: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@dp.callback_query(F.data.startswith("miss_"))
async def callback_miss_habit(callback: types.CallbackQuery):
    """Отметить привычку как пропущенную"""
    try:
        habit_id = int(callback.data.split("_")[1])
        is_new = db.track_habit(habit_id, "missed")

        if is_new:
            message = "❌ Привычка отмечена как пропущенная. Не расстраивайтесь, завтра получится!"
        else:
            message = "❌ Статус обновлен на 'Пропущено'"

        await callback.answer(message, show_alert=False)

        # Обновляем сообщение
        habit = db.get_habit(habit_id)
        streak = db.get_streak(habit_id)

        text = (
            f"<b>{habit[2]}</b>\n\n"
            f"❌ Отмечено как пропущенное\n"
            f"🔥 Текущая серия: {streak} дней"
        )

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_habit_action_keyboard(habit_id, "missed")
        )
    except Exception as e:
        logger.error(f"Ошибка при отметке пропуска: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@dp.callback_query(F.data.startswith("habit_"))
async def callback_habit_detail(callback: types.CallbackQuery):
    """Показать детальную информацию о привычке"""
    try:
        # Проверяем, что это не habit_stats
        parts = callback.data.split("_")
        if len(parts) == 2 and parts[0] == "habit":
            habit_id = int(parts[1])
        else:
            return  # Игнорируем, если это не чистый habit_ID

        habit = db.get_habit(habit_id)

        if not habit:
            await callback.answer("Привычка не найдена", show_alert=True)
            return

        _, user_id, habit_name, habit_desc, created_date, is_active = habit
        today_status = db.get_today_status(habit_id)
        streak = db.get_streak(habit_id)

        status_text = {
            "completed": "✅ Выполнено сегодня",
            "missed": "❌ Пропущено сегодня",
            None: "⚪️ Ещё не отмечали сегодня"
        }

        text = (
            f"<b>{habit_name}</b>\n\n"
            f"📝 {habit_desc}\n"
            f"📅 Создана: {created_date}\n"
            f"🔥 Текущая серия: {streak} дней\n"
            f"📊 {status_text.get(today_status, '⚪️ Ещё не отмечали сегодня')}\n\n"
            f"Выберите действие:"
        )

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_habit_action_keyboard(habit_id, today_status)
        )
    except ValueError:
        # Если не удалось преобразовать в int, игнорируем
        pass
    except Exception as e:
        logger.error(f"Ошибка в деталях привычки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    await callback.answer()


# Админские обработчики
@dp.callback_query(F.data == "admin_panel")
async def callback_admin_panel(callback: types.CallbackQuery):
    """Панель администратора"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав администратора", show_alert=True)
        return

    await callback.message.edit_text(
        "👑 <b>Панель администратора</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_users")
async def callback_admin_users(callback: types.CallbackQuery):
    """Список пользователей (для админа)"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return

    users = db.get_all_users()
    text = "👥 <b>Список пользователей:</b>\n\n"

    for i, user in enumerate(users, 1):
        user_id, first_name, username, is_admin_val, reg_date = user
        username_text = f" (@{username})" if username else ""
        admin_star = " 👑" if is_admin_val else ""
        text += f"{i}. {first_name}{username_text} (ID: {user_id}){admin_star}\n"
        text += f"   📅 Зарегистрирован: {reg_date}\n\n"

    text += f"\nВсего пользователей: {len(users)}"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_panel")],
                [InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_main")]
            ]
        )
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_stats")
async def callback_admin_stats(callback: types.CallbackQuery):
    """Общая статистика для админа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Общее количество пользователей
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            # Общее количество привычек
            cursor.execute("SELECT COUNT(*) FROM habits WHERE is_active = 1")
            total_habits = cursor.fetchone()[0]

            # Количество выполнений сегодня
            today = date.today().isoformat()
            cursor.execute(
                "SELECT COUNT(*) FROM habit_tracking WHERE track_date = ? AND status = 'completed'",
                (today,)
            )
            today_completed = cursor.fetchone()[0]

            # Количество активных пользователей сегодня
            cursor.execute(
                """
                SELECT COUNT(DISTINCT user_id) 
                FROM habit_tracking ht
                JOIN habits h ON ht.habit_id = h.habit_id
                WHERE ht.track_date = ?
                """,
                (today,)
            )
            active_users = cursor.fetchone()[0]

        text = (
            "📊 <b>Общая статистика бота:</b>\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"📋 Активных привычек: {total_habits}\n"
            f"✅ Выполнено сегодня: {today_completed}\n"
            f"👤 Активных пользователей сегодня: {active_users}\n"
        )

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_panel")],
                    [InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_main")]
                ]
            )
        )
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при получении статистики",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")]
                ]
            )
        )
    await callback.answer()


@dp.callback_query(F.data == "admin_broadcast")
async def callback_admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    """Рассылка сообщений пользователям"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return

    await callback.message.edit_text(
        "📢 <b>Создание рассылки</b>\n\n"
        "Введите сообщение, которое хотите отправить всем пользователям бота.\n"
        "Можно использовать форматирование (жирный, курсив и т.д.).\n\n"
        "Для отмены введите /cancel",
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_for_message)
    await callback.answer()


@dp.message(BroadcastStates.waiting_for_message)
async def process_broadcast_message(message: types.Message, state: FSMContext):
    """Обработка сообщения для рассылки"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для этого действия")
        await state.clear()
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer(
            "❌ Рассылка отменена",
            reply_markup=get_main_keyboard(message.from_user.id)
        )
        return

    # Получаем всех пользователей
    users = db.get_all_users()
    total_users = len(users)
    success_count = 0
    fail_count = 0

    status_message = await message.answer(
        f"📤 Начинаю рассылку...\n"
        f"Всего получателей: {total_users}\n"
        f"Прогресс: 0/{total_users}"
    )

    # Отправляем сообщение каждому пользователю
    for i, (user_id, _, _, _, _) in enumerate(users, 1):
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                caption=message.caption,
                parse_mode="HTML"
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
            fail_count += 1

        # Обновляем статус каждые 10 сообщений
        if i % 10 == 0:
            await status_message.edit_text(
                f"📤 Рассылка в процессе...\n"
                f"Всего получателей: {total_users}\n"
                f"Прогресс: {i}/{total_users}\n"
                f"✅ Успешно: {success_count}\n"
                f"❌ Ошибок: {fail_count}"
            )

    await status_message.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📊 Статистика:\n"
        f"• Всего получателей: {total_users}\n"
        f"• ✅ Успешно доставлено: {success_count}\n"
        f"• ❌ Не доставлено: {fail_count}\n"
        f"• 📈 Процент доставки: {(success_count / total_users * 100):.1f}%",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

    await state.clear()


# Обработчики состояний
@dp.message(HabitStates.waiting_for_habit_name)
async def process_habit_name(message: types.Message, state: FSMContext):
    """Обработка названия привычки"""
    habit_name = message.text.strip()

    if len(habit_name) > 100:
        await message.answer(
            "❌ Название слишком длинное. Пожалуйста, введите название короче 100 символов:"
        )
        return

    if len(habit_name) < 3:
        await message.answer(
            "❌ Название слишком короткое. Пожалуйста, введите название длиннее 3 символов:"
        )
        return

    await state.update_data(habit_name=habit_name)
    await state.set_state(HabitStates.waiting_for_habit_description)
    await message.answer(
        f"Отличное название! Теперь введите описание привычки "
        f"(или отправьте /skip чтобы пропустить):"
    )


@dp.message(HabitStates.waiting_for_habit_description)
async def process_habit_description(message: types.Message, state: FSMContext):
    """Обработка описания привычки"""
    if message.text == "/skip":
        habit_description = "Без описания"
    else:
        habit_description = message.text.strip()
        if len(habit_description) > 500:
            await message.answer(
                "❌ Описание слишком длинное. Пожалуйста, введите описание короче 500 символов "
                "(или отправьте /skip чтобы пропустить):"
            )
            return

    user_data = await state.get_data()
    habit_name = user_data.get("habit_name")

    # Сохраняем привычку в базу данных
    habit_id = db.add_habit(
        user_id=message.from_user.id,
        habit_name=habit_name,
        habit_description=habit_description,
    )

    if habit_id:
        await state.clear()
        await message.answer(
            f"✅ Привычка <b>«{habit_name}»</b> успешно создана!\n\n"
            f"Теперь вы можете отмечать её выполнение каждый день.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(message.from_user.id)
        )
    else:
        await message.answer(
            "❌ Произошла ошибка при создании привычки. Попробуйте позже.",
            reply_markup=get_main_keyboard(message.from_user.id)
        )


# Обработчик обычных сообщений
@dp.message()
async def handle_unknown_message(message: types.Message):
    """Обработчик неизвестных команд"""
    await message.answer(
        "Я не понимаю эту команду. Пожалуйста, используйте кнопки меню или /help для справки.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )


# Запуск бота
async def main() -> None:
    """Главная функция запуска бота"""
    try:
        # Пропускаем накопившиеся апдейты и запускаем бота
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("🚀 Бот запущен и готов к работе!")
        logger.info(f"👑 Администратор: {ADMIN_ID}")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Необработанная ошибка: {e}")