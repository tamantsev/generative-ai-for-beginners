"""Telegram bot entry point for the training diary."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import get_settings
from .database import get_session, init_db
from .models import TimeOfDay
from .services import TrainingDiaryService, infer_time_of_day

(
    CHOOSE_ACTION,
    CHOOSE_EXERCISE,
    ENTER_NEW_EXERCISE,
    ENTER_DATE,
    ENTER_TIME_OF_DAY,
    ENTER_WEIGHT,
    ENTER_REPS,
    AFTER_SET,
) = range(8)


_TIME_OF_DAY_MAP = {
    "утро": TimeOfDay.MORNING,
    "morning": TimeOfDay.MORNING,
    "день": TimeOfDay.AFTERNOON,
    "day": TimeOfDay.AFTERNOON,
    "вечер": TimeOfDay.EVENING,
    "evening": TimeOfDay.EVENING,
}


def _format_workout_summary(service: TrainingDiaryService, user, workout_id: int) -> str:
    workout = service.get_workout(user, workout_id)
    if not workout:
        return "Нет данных о тренировке."
    lines = [f"Упражнение: {workout.exercise.name}"]
    for training_set in workout.sets:
        lines.append(
            f"Подход {training_set.order}: {training_set.reps} × {float(training_set.weight):g} кг = {training_set.load}"
        )
    lines.append(f"Итоговая нагрузка: {workout.total_load}")
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user:
        return ConversationHandler.END

    with get_session() as session:
        service = TrainingDiaryService(session)
        u = update.effective_user
        service.ensure_user(u.id, u.username, u.first_name, u.last_name)

    keyboard = [
        [InlineKeyboardButton("🏋️ Записать тренировку", callback_data="log_workout")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📤 Mini App", callback_data="open_webapp")],
    ]
    await update.message.reply_text(
        "Привет! Это дневник силовых тренировок. Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    context.user_data.clear()
    return CHOOSE_ACTION


async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "log_workout":
        return await prompt_exercise(query, context)

    settings = get_settings()
    if action == "stats":
        text = "Откройте mini app, чтобы посмотреть графики нагрузки."
        if settings.webapp_base_url:
            text = f"Откройте статистику в mini app: {settings.webapp_base_url.rstrip('/')}"
        await query.edit_message_text(text)
        return CHOOSE_ACTION

    if action == "open_webapp":
        if settings.webapp_base_url:
            await query.edit_message_text(
                f"Mini app доступно по ссылке: {settings.webapp_base_url.rstrip('/')}"
            )
        else:
            await query.edit_message_text("Переменная WEBAPP_BASE_URL не настроена.")
        return CHOOSE_ACTION

    await query.edit_message_text("Неизвестная команда. Отправьте /start")
    return ConversationHandler.END


async def prompt_exercise(target, context: ContextTypes.DEFAULT_TYPE) -> int:
    await target.edit_message_text("Выберите упражнение или добавьте новое.")

    with get_session() as session:
        service = TrainingDiaryService(session)
        tg_user = target.from_user
        user = service.ensure_user(tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
        exercises = service.list_exercises(user)

    keyboard_rows = [
        [InlineKeyboardButton(exercise.name, callback_data=f"exercise:{exercise.id}")]
        for exercise in exercises[:10]
    ]
    keyboard_rows.append([InlineKeyboardButton("➕ Новое упражнение", callback_data="exercise:new")])
    await target.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard_rows))
    return CHOOSE_EXERCISE


async def select_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "exercise:new":
        await query.edit_message_text("Введите название упражнения.")
        return ENTER_NEW_EXERCISE

    _, exercise_id = data.split(":", 1)
    context.user_data["exercise_id"] = int(exercise_id)
    context.user_data.pop("workout_id", None)
    context.user_data["sets"] = []
    return await ask_date(query, context)


async def store_new_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Название не может быть пустым. Попробуйте снова.")
        return ENTER_NEW_EXERCISE

    with get_session() as session:
        service = TrainingDiaryService(session)
        tg_user = update.effective_user
        user = service.ensure_user(tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
        exercise = service.upsert_exercise(user, name)
        context.user_data["exercise_id"] = exercise.id
        context.user_data["sets"] = []

    return await ask_date(update, context)


async def ask_date(update_or_query, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (
        f"Дата тренировки по умолчанию {date.today():%Y-%m-%d}.\n"
        "Введите другую дату (ГГГГ-ММ-ДД) или отправьте /today."
    )
    if hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text(text)
    else:
        await update_or_query.message.reply_text(text)
    return ENTER_DATE


async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw.lower() in {"/today", "today"}:
        workout_date = date.today()
    else:
        try:
            workout_date = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            await update.message.reply_text("Неверный формат даты. Используйте 2024-01-31.")
            return ENTER_DATE
    context.user_data["workout_date"] = workout_date
    return await ask_time_of_day(update, context)


async def ask_time_of_day(update_or_query, context: ContextTypes.DEFAULT_TYPE) -> int:
    default_tod = infer_time_of_day(datetime.now())
    text = (
        f"Время суток по умолчанию: {default_tod.value}.\n"
        "Отправьте утро/день/вечер или /auto для выбора по времени."
    )
    if hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text(text)
    else:
        await update_or_query.message.reply_text(text)
    return ENTER_TIME_OF_DAY


async def handle_time_of_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip().lower()
    if raw in {"/auto", "auto"}:
        context.user_data["time_of_day"] = infer_time_of_day(datetime.now())
    else:
        tod = _TIME_OF_DAY_MAP.get(raw)
        if not tod:
            await update.message.reply_text("Введите: утро, день или вечер.")
            return ENTER_TIME_OF_DAY
        context.user_data["time_of_day"] = tod
    await update.message.reply_text("Введите вес снаряда в килограммах (например 42.5).")
    return ENTER_WEIGHT


async def handle_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.replace(",", ".").strip()
    try:
        weight = float(raw)
    except ValueError:
        await update.message.reply_text("Вес должен быть числом. Попробуйте снова.")
        return ENTER_WEIGHT
    if weight <= 0:
        await update.message.reply_text("Вес должен быть больше нуля.")
        return ENTER_WEIGHT
    context.user_data["weight"] = weight
    await update.message.reply_text("Сколько повторов выполнено?")
    return ENTER_REPS


async def handle_reps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if not raw.isdigit():
        await update.message.reply_text("Повторы должны быть целым числом.")
        return ENTER_REPS
    reps = int(raw)
    if reps <= 0:
        await update.message.reply_text("Повторы должны быть больше нуля.")
        return ENTER_REPS

    weight = context.user_data.get("weight")
    exercise_id = context.user_data.get("exercise_id")
    workout_date = context.user_data.get("workout_date", date.today())
    time_of_day = context.user_data.get("time_of_day", infer_time_of_day(datetime.now()))

    with get_session() as session:
        service = TrainingDiaryService(session)
        tg_user = update.effective_user
        user = service.ensure_user(tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
        exercise = service.get_exercise(user, exercise_id)
        if not exercise:
            await update.message.reply_text("Упражнение не найдено. Начните заново командой /start.")
            return ConversationHandler.END

        workout_id: Optional[int] = context.user_data.get("workout_id")
        workout = service.get_workout(user, workout_id) if workout_id else None
        if not workout:
            workout = service.find_or_create_workout(user, exercise, workout_date, time_of_day)
            workout_id = workout.id
            context.user_data["workout_id"] = workout_id

        new_set = service.add_training_set(workout, weight, reps)
        context.user_data.setdefault("sets", []).append(new_set.id)
        summary = _format_workout_summary(service, user, workout_id)

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Ещё подход", callback_data="set:add")],
            [InlineKeyboardButton("↩️ Отменить последний", callback_data="set:undo")],
            [InlineKeyboardButton("➡️ Новое упражнение", callback_data="set:next")],
            [InlineKeyboardButton("✅ Завершить", callback_data="set:finish")],
        ]
    )
    await update.message.reply_text(f"Подход сохранён!\n{summary}", reply_markup=keyboard)
    return AFTER_SET


async def handle_after_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "set:add":
        await query.edit_message_text("Введите вес следующего подхода (кг).")
        return ENTER_WEIGHT

    if action == "set:undo":
        last_set_id = context.user_data.get("sets", [])[-1] if context.user_data.get("sets") else None
        if not last_set_id:
            await query.edit_message_text("Нет подходов для удаления.")
            return AFTER_SET
        with get_session() as session:
            service = TrainingDiaryService(session)
            tg_user = query.from_user
            user = service.ensure_user(tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
            removed = service.delete_training_set(last_set_id, user)
            if removed:
                context.user_data["sets"].pop()
                workout_id = context.user_data.get("workout_id")
                if workout_id:
                    workout = service.get_workout(user, workout_id)
                    if workout and not workout.sets:
                        service.cleanup_workout(workout)
                        context.user_data.pop("workout_id", None)
                        await query.edit_message_text("Последний подход удалён. Укажите вес нового подхода.")
                        return ENTER_WEIGHT
                    summary = _format_workout_summary(service, user, workout_id)
                    await query.edit_message_text(f"Последний подход удалён.\n{summary}")
                    return AFTER_SET
        await query.edit_message_text("Не удалось удалить подход. Попробуйте снова.")
        return AFTER_SET

    if action == "set:next":
        context.user_data.pop("workout_id", None)
        context.user_data.pop("sets", None)
        return await prompt_exercise(query, context)

    if action == "set:finish":
        with get_session() as session:
            service = TrainingDiaryService(session)
            tg_user = query.from_user
            user = service.ensure_user(tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
            workout_id = context.user_data.get("workout_id")
            message = "Тренировка завершена."
            if workout_id:
                summary = _format_workout_summary(service, user, workout_id)
                message = f"Тренировка завершена!\n{summary}"
        await query.edit_message_text(message)
        return ConversationHandler.END

    await query.edit_message_text("Команда не распознана. Отправьте /start")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Диалог завершён. Используйте /start для начала заново.")
    return ConversationHandler.END


def build_application():
    settings = get_settings()
    init_db()
    application = ApplicationBuilder().token(settings.telegram_bot_token).build()

    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_ACTION: [CallbackQueryHandler(handle_action)],
            CHOOSE_EXERCISE: [CallbackQueryHandler(select_exercise)],
            ENTER_NEW_EXERCISE: [MessageHandler(filters.TEXT & ~filters.COMMAND, store_new_exercise)],
            ENTER_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date)],
            ENTER_TIME_OF_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_of_day)],
            ENTER_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_weight)],
            ENTER_REPS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reps)],
            AFTER_SET: [CallbackQueryHandler(handle_after_set)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    application.add_handler(conversation)
    return application


def main() -> None:
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
