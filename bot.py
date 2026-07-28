import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from config import BOT_TOKEN, ADMIN_ID, PRICE_PER_STAR, CARD_NUMBER, SUPPORT_USERNAME

# Настройки для Webhook на Render
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
PORT = int(os.getenv("PORT", 8080))

router = Router()

class BuyStarsState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_screenshot = State()

class CalculatorState(StatesGroup):
    waiting_for_calc_amount = State()


# --- КЛАВИАТУРЫ ---

def get_main_menu_keyboard():
    """Главное меню в 3 колонки (как ты просил) + кнопка перезапуска/меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ Купить", callback_data="menu_buy"),
            InlineKeyboardButton(text="🧮 Калькулятор", callback_data="menu_calc"),
            InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")
        ],
        [
            InlineKeyboardButton(text="🔄 Главное меню", callback_data="menu_home")
        ]
    ])

def get_back_to_menu_keyboard():
    """Кнопка возврата в меню для подменю"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu_home")]
    ])


# --- ОБРАБОТЧИКИ СТАРТА И МЕНЮ ---

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "✨ <b>Добро пожаловать в наш магазин Durov soset star!</b> ✨\n\n"
        "Выберите нужный раздел в меню ниже 👇",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "menu_home")
async def process_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🏠 <b>Главное меню:</b>\n\n"
        "Выберите нужный раздел ниже 👇",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# --- РАЗДЕЛ 1: ПОКУПКА ЗВЕЗД ---

@router.callback_query(F.data == "menu_buy")
async def process_buy_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BuyStarsState.waiting_for_amount)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu_home")]
    ])
    
    await callback.message.edit_text(
        "🛒 <b>Покупка Telegram Stars</b>\n\n"
        "🔢 Введите количество звезд, которое хотите приобрести (например: <code>50</code>):",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(BuyStarsState.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Пожалуйста, введите корректное число (только цифры).", reply_markup=get_back_to_menu_keyboard())
        return

    amount = int(message.text)
    if amount <= 0:
        await message.answer("⚠️ Количество звезд должно быть больше нуля.", reply_markup=get_back_to_menu_keyboard())
        return

    total_price = amount * PRICE_PER_STAR
    await state.update_data(stars_amount=amount, total_price=total_price)

    text = (
        f"🛒 <b>Ваш заказ:</b> {amount} ⭐\n"
        f"💵 <b>К оплате:</b> <code>{total_price:.2f} грн</code>\n\n"
        f"💳 <b>Реквизиты для оплаты (карта):</b>\n"
        f"<code>{CARD_NUMBER}</code>\n\n"
        f"⏳ <i>После перевода отправьте в этот чат скриншот или квитанцию об оплате.</i>\n\n"
        f"💬 По вопросам: @{SUPPORT_USERNAME}"
    )

    await message.answer(text, reply_markup=get_back_to_menu_keyboard(), parse_mode="HTML")
    await state.set_state(BuyStarsState.waiting_for_screenshot)


@router.message(BuyStarsState.waiting_for_screenshot, F.photo)
async def process_screenshot(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    stars = data.get("stars_amount")
    price = data.get("total_price")
    
    photo_file_id = message.photo[-1].file_id
    user = message.from_user
    username = f"@{user.username}" if user.username else "нет юзернейма"

    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выдать звезды(стать багатым)", callback_data=f"approve_{user.id}_{stars}"),
            InlineKeyboardButton(text="❌ Отклонить(грызть говно)", callback_data=f"decline_{user.id}")
        ]
    ])

    admin_text = (
        f"🔔 <b>Новый заказ на звезды!</b>\n\n"
        f"👤 <b>Покупатель:</b> {user.full_name} ({username})\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"⭐ <b>Количество:</b> {stars} звезд\n"
        f"💵 <b>Сумма:</b> {price:.2f} грн\n"
    )

    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_file_id,
        caption=admin_text,
        parse_mode="HTML",
        reply_markup=admin_keyboard
    )

    await message.answer(
        "🔄 <b>Скриншот успешно отправлен на проверку!</b>\n\n"
        "Ожидайте, администратор проверяет поступление средств.",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )
    await state.clear()


@router.message(BuyStarsState.waiting_for_screenshot, ~F.photo)
async def not_a_photo(message: Message):
    await message.answer("⚠️ Пожалуйста, отправьте именно <b>изображение (скриншот)</b> чека.", reply_markup=get_back_to_menu_keyboard(), parse_mode="HTML")


# --- РАЗДЕЛ 2: КАЛЬКУЛЯТОР ЗВЕЗД ---

@router.callback_query(F.data == "menu_calc")
async def process_calc_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CalculatorState.waiting_for_calc_amount)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu_home")]
    ])
    
    await callback.message.edit_text(
        "🧮 <b>Калькулятор стоимости звезд</b>\n\n"
        "Введите количество звезд, чтобы узнать итоговую цену:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(CalculatorState.waiting_for_calc_amount)
async def process_calc_result(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Введите корректное число (только цифры).", reply_markup=get_back_to_menu_keyboard())
        return

    amount = int(message.text)
    if amount <= 0:
        await message.answer("⚠️ Количество должно быть больше нуля.", reply_markup=get_back_to_menu_keyboard())
        return

    total_price = amount * PRICE_PER_STAR

    text = (
        f"🧮 <b>Результат расчета:</b>\n\n"
        f"⭐ Количество: <b>{amount} звезд</b>\n"
        f"💵 Стоимость: <b>{total_price:.2f} грн</b>\n"
        f"<i>(Цена за 1 шт: {PRICE_PER_STAR} грн)</i>"
    )

    # Клавиатура под результатом: купить сразу или вернуться в меню
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Купить это количество", callback_data="menu_buy")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu_home")]
    ])

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()


# --- РАЗДЕЛ 3: ПОДДЕРЖКА И КАНАЛЫ ---

@router.callback_query(F.data == "menu_support")
async def process_support_menu(callback: CallbackQuery):
    # Твои каналы можешь прописать прямо здесь, заменив ссылки и текст
    text = (
        f"💬 <b>Поддержка и полезные каналы</b>\n\n"
        f"👤 <b>Администратор / Поддержка:</b> @{SUPPORT_USERNAME}\n\n"
        f"📢 <b>Наши каналы и проекты:</b>\n"
        f"• <a href='https://t.me/+eSkRr0gqvTRmNjJk'>Наш главный канал</a>\n"
        f"• <a href='https://t.me/durovvReviews'>Отзывы клиентов</a>\n\n"
        f"<i>Если у вас возникли вопросы по оплате или зачислению — смело пишите в поддержку!</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu_home")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()


# --- ДЕЙСТВИЯ АДМИНА ---

@router.callback_query(F.data.startswith("approve_"))
async def admin_approve(callback: CallbackQuery, bot: Bot):
    _, user_id, stars = callback.data.split("_")
    
    success_text = (
        f"🎉 <b>Оплата успешно подтверждена!</b> ✨\n\n"
        f"📦 Ваша заявка принята в обработку, звёзды ({stars} ⭐) уже летят к вам!\n"
        f"<i>Обычно зачисление занимает от 1 до 5 минут. Спасибо, что выбрали нас!</i> 💙"
    )
    
    await bot.send_message(chat_id=int(user_id), text=success_text, parse_mode="HTML")
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n<b>[СТАТУС: ✅ ОДОБРЕНО И ВЫДАНО]</b>", parse_mode="HTML")
    await callback.answer("Заказ успешно одобрен!")


@router.callback_query(F.data.startswith("decline_"))
async def admin_decline(callback: CallbackQuery, bot: Bot):
    _, user_id = callback.data.split("_")
    
    decline_text = (
        f"❌ <b>К сожалению, ваша заявка была отклонена.</b>\n\n"
        f"Возникла ошибка с чеком или средства не поступили на счет.\n"
        f"Если это ошибка, пожалуйста, обратитесь в поддержку: @{SUPPORT_USERNAME}"
    )
    
    await bot.send_message(chat_id=int(user_id), text=decline_text, parse_mode="HTML")
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n<b>[СТАТУС: ❌ ОТКЛОНЕН]</b>", parse_mode="HTML")
    await callback.answer("Заказ отклонен.")


# --- ЗАПУСК БОТА ---

async def on_startup(bot: Bot):
    if RENDER_URL:
        await bot.set_webhook(f"{RENDER_URL}{WEBHOOK_PATH}")
        logging.info(f"Webhook установлен: {RENDER_URL}{WEBHOOK_PATH}")

def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    dp.startup.register(on_startup)

    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
