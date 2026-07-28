import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, ADMIN_ID, PRICE_PER_STAR, CARD_NUMBER, SUPPORT_USERNAME

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
        "Привет! Этот бот создан для быстрой покупки Telegram Stars.\n"
        "Нажми кнопку ниже, чтобы начать.",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "buy_stars")
async def process_buy(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите количество звезд, которое хотите купить (например: 50):")
    await state.set_state(BuyStarsState.waiting_for_amount)
    await callback.answer()


@router.message(BuyStarsState.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число (количество звезд).")
        return

    amount = int(message.text)
    if amount <= 0:
        await message.answer("Количество звезд должно быть больше нуля.")
        return

    total_price = amount * PRICE_PER_STAR

    await state.update_data(stars_amount=amount, total_price=total_price)

    text = (
        f"🛒 Вы выбрали: <b>{amount} ⭐</b>\n"
        f"💵 К оплате: <b>{total_price:.2f} грн</b>\n\n"
        f"💳 Переведите сумму на карту:\n<code>{CARD_NUMBER}</code>\n\n"
        f"📸 После оплаты отправьте в этот чат <b>скриншот или квитанцию</b> об оплате.\n\n"
        f"💬 По всем вопросам: @{SUPPORT_USERNAME}"
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
        f"👤 Покупатель: {user.full_name} ({username}) | ID: <code>{user.id}</code>\n"
        f"⭐ Количество: {stars} звезд\n"
        f"💵 Сумма: {price:.2f} грн\n"
    )

    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_file_id,
        caption=admin_text,
        parse_mode="HTML",
        reply_markup=admin_keyboard
    )

    await message.answer("✅ Скриншот успешно отправлен на проверку! Ожидайте зачисления звезд.")
    await state.clear()


@router.message(BuyStarsState.waiting_for_screenshot, ~F.photo)
async def not_a_photo(message: Message):
    await message.answer("Пожалуйста, отправьте именно <b>изображение (скриншот)</b> чека.", parse_mode="HTML")


@router.callback_query(F.data.startswith("approve_"))
async def admin_approve(callback: CallbackQuery, bot: Bot):
    _, user_id, stars = callback.data.split("_")
    await bot.send_message(
        chat_id=int(user_id),
        text=f"✅ Ваша оплата подтверждена! Вам начислено {stars} ⭐. Спасибо за покупку!"
    )
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n<b>[СТАТУС: ОДОБРЕНО]</b>", parse_mode="HTML")
    await callback.answer("Заказ одобрен.")


@router.callback_query(F.data.startswith("decline_"))
async def admin_decline(callback: CallbackQuery, bot: Bot):
    _, user_id = callback.data.split("_")
    await bot.send_message(
        chat_id=int(user_id),
        text="❌ К сожалению, ваша оплата не была подтверждена или чек недействителен. Обратитесь в поддержку."
    )
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n<b>[СТАТУС: ОТКЛОНЕН]</b>", parse_mode="HTML")
    await callback.answer("Заказ отклонен.")


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот успешно запущен и ждет пользователей...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
