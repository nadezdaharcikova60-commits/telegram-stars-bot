import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from config import BOT_TOKEN, ADMIN_ID, PRICE_PER_STAR, CARD_NUMBER, SUPPORT_USERNAME

# Настройки для Webhook на Render
# Render автоматически выдает переменную окружения RENDER_EXTERNAL_URL
import os
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")  # Например: https://stars-bot-2yhp.onrender.com
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# Порт для веб-сервера (Render требует слушать порт из переменной PORT)
PORT = int(os.getenv("PORT", 8080))

router = Router()

class BuyStarsState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_screenshot = State()


@router.message(Command("start"))
async def cmd_start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Купить звезды", callback_data="buy_stars")]
    ])
    await message.answer(
        "✨ <b>Добро пожаловать в наш магазин Telegram Stars!</b> ✨\n\n"
        "Здесь вы можете быстро и безопасно приобрести звёзды по выгодной цене.\n"
        "Нажмите кнопку ниже, чтобы оформить заказ 👇",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "buy_stars")
async def process_buy(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🔢 Введите количество звезд, которое хотите приобрести (например: <code>50</code>):", parse_mode="HTML")
    await state.set_state(BuyStarsState.waiting_for_amount)
    await callback.answer()


@router.message(BuyStarsState.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Пожалуйста, введите корректное число (только цифры).")
        return

    amount = int(message.text)
    if amount <= 0:
        await message.answer("⚠️ Количество звезд должно быть больше нуля.")
        return

    total_price = amount * PRICE_PER_STAR

    await state.update_data(stars_amount=amount, total_price=total_price)

    text = (
        f"🛒 <b>Ваш заказ:</b> {amount} ⭐\n"
        f"💵 <b>К оплате:</b> <code>{total_price:.2f} грн</code>\n\n"
        f"💳 <b>Реквизиты для оплаты (карты):</b>\n"
        f"<code>{CARD_NUMBER}</code>\n\n"
        f"⏳ <i>После перевода отправьте в этот чат скриншот или квитанцию об оплате.</i>\n\n"
        f"💬 Возникли вопросы? Пишите: @{SUPPORT_USERNAME}"
    )

    await message.answer(text, parse_mode="HTML")
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
            InlineKeyboardButton(text="✅ Выдать звезды", callback_data=f"approve_{user.id}_{stars}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_{user.id}")
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
        parse_mode="HTML"
    )
    await state.clear()


@router.message(BuyStarsState.waiting_for_screenshot, ~F.photo)
async def not_a_photo(message: Message):
    await message.answer("⚠️ Пожалуйста, отправьте именно <b>изображение (скриншот)</b> чека.", parse_mode="HTML")


@router.callback_query(F.data.startswith("approve_"))
async def admin_approve(callback: CallbackQuery, bot: Bot):
    _, user_id, stars = callback.data.split("_")
    
    # Красивое сообщение пользователю после подтверждения
    success_text = (
        f"🎉 <b>Оплата успешно подтверждена!</b> ✨\n\n"
        f"📦 Ваша заявка принята в обработку, звёзды ({stars} ⭐) уже летят к вам!\n"
        f"<i>Обычно зачисление занимает от 1 до 5 минут. Спасибо, что выбрали нас!</i> 💙"
    )
    
    await bot.send_message(
        chat_id=int(user_id),
        text=success_text,
        parse_mode="HTML"
    )
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
    
    await bot.send_message(
        chat_id=int(user_id),
        text=decline_text,
        parse_mode="HTML"
    )
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n<b>[СТАТУС: ❌ ОТКЛОНЕН]</b>", parse_mode="HTML")
    await callback.answer("Заказ отклонен.")


async def on_startup(bot: Bot):
    # Установка вебхука при старте
    if RENDER_URL:
        await bot.set_webhook(f"{RENDER_URL}{WEBHOOK_PATH}")
        logging.info(f"Webhook установлен: {RENDER_URL}{WEBHOOK_PATH}")
    else:
        logging.warning("RENDER_EXTERNAL_URL не найдена, вебхук может работать некорректно локально.")


def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # Регистрируем событие запуска для установки вебхука
    dp.startup.register(on_startup)

    # Создаем aiohttp приложение для приема вебхуков от Telegram
    app = aiohttp_app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # Запускаем веб-сервер на нужном для Render порту
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
