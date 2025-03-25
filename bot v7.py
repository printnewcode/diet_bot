import logging
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
import requests
import asyncio
import dotenv
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler

dotenv.load_dotenv()
API_KEY=os.getenv("API_KEY")
API_URL=os.getenv("API_URL")
BOT_TOKEN=os.getenv("BOT_TOKEN")


DAILY_LIMIT = 5

request_counter = DAILY_LIMIT
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


logging.basicConfig(level=logging.INFO)
router = Router()

class UserStates(StatesGroup):
    WAITING_AGE = State()
    WAITING_CALORIES = State()
    WAITING_GOAL = State()
    WAITING_WEIGHT = State()

def reset_counter():
    global request_counter
    request_counter = DAILY_LIMIT
    logging.info(f"Счетчик сброшен. Текущее значение: {request_counter}")

async def get_diet_plan(age: int, calories: int, goal: str, weight: float) -> str:
    prompt = (
        f"Ты ассистент помощник в телеграмм боте разаботанный учениками J-GET. Будь вежлив. При форматирование текста:\n"
        f"используй только *жирный*, _курсив_, три обратных апострофа для программного code. Не используй #\n"
        f"Создай персональное меню питания для человека с параметрами:\n"
        f"- Возраст: {age}\n"
        f"- Суточная норма калорий: {calories}\n"
        f"- Цель: {goal}\n"
        f"- Вес: {weight} кг\n\n"
        f"Формат вывода: красиво оформленное меню с блюдами на день, без технических деталей"
    )
    
    try:
        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return "⚠️ Не удалось сгенерировать меню, попробуйте позже"
    
    except Exception as e:
        logging.error(f"API error: {str(e)}")
        return "⚠️ Ошибка соединения с сервером"

@router.message(F.text == "/start")
async def cmd_start(message: types.Message, state: FSMContext):
    global request_counter
    if request_counter <= 0:
        await message.answer("Дневной лимит исчерпан ⛔️\nПовторите попытку завтра ☺️")
        return
    await state.set_state(UserStates.WAITING_AGE)
    await message.answer(
        "Привет! Я - бот, который поможет тебе создать твой рацион питания. "
        "Для этого напиши мне свой возраст."
    )

@router.message(UserStates.WAITING_AGE)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введите возраст числом!")
    await state.update_data(age=int(message.text))
    await state.set_state(UserStates.WAITING_CALORIES)
    await message.answer("Теперь напиши количество калорий в день.")

@router.message(UserStates.WAITING_CALORIES)
async def process_calories(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введите калории числом!")
    await state.update_data(calories=int(message.text))
    await state.set_state(UserStates.WAITING_GOAL)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="Сбросить вес", callback_data="lose_weight"),
        types.InlineKeyboardButton(text="Правильно питаться", callback_data="eat_healthy"),
        types.InlineKeyboardButton(text="Набрать вес", callback_data="gain_weight")
    )
    await message.answer("Выбери цель:", reply_markup=builder.as_markup())

@router.callback_query(UserStates.WAITING_GOAL)
async def process_goal(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(goal=callback.data)
    await state.set_state(UserStates.WAITING_WEIGHT)
    await callback.message.answer("Напиши свой вес")
    await callback.answer()

@router.message(UserStates.WAITING_WEIGHT)
async def process_weight(message: types.Message, state: FSMContext):
    global request_counter
    if not message.text.replace('.', '').isdigit():
        return await message.answer("Введите вес числом!")
    
    request_counter -= 1
    loading_msg = await message.answer("👩‍🔬 Диетолог уже составляет рацион питания")
    
    user_data = await state.get_data()
    diet_plan = await get_diet_plan(
        user_data['age'],
        user_data['calories'],
        user_data['goal'],
        float(message.text)
    )
    
    await loading_msg.delete()

    try:
        await message.answer(
            f"Ок, держи примерное меню:\n\n{diet_plan}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Markdown formatting error: {str(e)}")
        await message.answer(
            f"Ок, держи примерное меню:\n\n{diet_plan}"
        )
    
    await state.clear()

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    scheduler.add_job(reset_counter, 'cron', hour=0, minute=0)
    scheduler.start()
    
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
