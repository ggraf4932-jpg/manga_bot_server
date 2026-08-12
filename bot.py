import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

import config
import database

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# --- Middleware ---
import time
from aiogram import BaseMiddleware
from typing import Any, Awaitable, Callable, Dict

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 3.0):
        self.limit = limit
        self.users = {}

    async def __call__(
        self,
        handler: Callable[[types.Message, Dict[str, Any]], Awaitable[Any]],
        event: types.Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        now = time.time()
        if user_id in self.users:
            if now - self.users[user_id] < self.limit:
                return
        self.users[user_id] = now
        return await handler(event, data)

dp.message.middleware(ThrottlingMiddleware())

class AdminStates(StatesGroup):
    waiting_for_channel_id = State()
    waiting_for_channel_url = State()
    
    waiting_for_manga_post = State()
    waiting_for_manga_code = State()
    waiting_for_manga_image = State()
    waiting_for_manga_caption = State()
    
    waiting_for_old_manga_code = State()
    waiting_for_old_manga_image = State()
    waiting_for_old_manga_caption = State()

class UserStates(StatesGroup):
    waiting_for_anon_message = State()

# --- Yordamchi funksiyalar ---
async def check_subscriptions(user_id: int) -> bool:
    channels = await database.get_channels()
    for ch_id, _ in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception as e:
            logging.error(f"Obunani tekshirishda xatolik (Kanal: {ch_id}): {e}")
            return False # Bot kanalga admin bo'lmasa xato beradi
    return True

def get_sub_keyboard(channels, code: str = None):
    kb = []
    for i, (ch_id, url) in enumerate(channels, 1):
        kb.append([InlineKeyboardButton(text=f"{i}-Kanalga obuna bo'lish", url=url)])
    
    # Tekshirish tugmasi. Agar kod bo'lsa, uni callback ichiga yashiramiz
    callback_data = f"check_sub:{code}" if code else "check_sub:none"
    kb.append([InlineKeyboardButton(text="✅ Tasdiqlash (Tekshirish)", callback_data=callback_data)])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ==================================================
# Foydalanuvchi qismi
# ==================================================

main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="👤 Admin bilan bog'lanish"), KeyboardButton(text="👻 Anonim so'rov yuborish")],
    [KeyboardButton(text="ℹ️ Yordam")]
], resize_keyboard=True)

@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    await database.add_user(message.from_user.id)
    
    # command.args - bu deep-link kodi. Masalan: t.me/bot?start=solo15 => command.args = 'solo15'
    code = command.args 
    
    is_subbed = await check_subscriptions(message.from_user.id)
    
    if not is_subbed:
        channels = await database.get_channels()
        if channels:
            await message.answer(
                "Botdan to'liq foydalanish uchun quyidagi kanallarga a'zo bo'ling:",
                reply_markup=get_sub_keyboard(channels, code)
            )
            return
    
    # Agar a'zo bo'lsa yoki kanallar yo'q bo'lsa
    if code:
        await send_manga_by_code(message, code)
    else:
        welcome_text = (
            "👋 *Assalomu alaykum! iNEMO Manga botiga xush kelibsiz!*\n\n"
            "Bu bot orqali siz sevimli mangalaringizni sifatli PDF formatida, o'zbek tilida yuklab olishingiz mumkin.\n\n"
            "📖 *Qisqacha qo'llanma:*\n"
            "• Mangani yuklash uchun kanalimizdagi maxsus havolani bosing.\n"
            "• Barcha PDF fayllar himoyalangan. Parol: `@inemo_manga`\n"
            "• Yangi qismlarni o'tkazib yubormaslik uchun ularni ❤️ Sevimlilarga qo'shishni unutmang.\n\n"
            "👇 Quyidagi menyudan kerakli bo'limni tanlang:"
        )
        await message.answer(welcome_text, parse_mode="Markdown", reply_markup=main_menu)

@dp.callback_query(F.data.startswith("check_sub:"))
async def check_sub_handler(callback: CallbackQuery):
    code = callback.data.split(":")[1]
    code = None if code == "none" else code
    
    is_subbed = await check_subscriptions(callback.from_user.id)
    
    if is_subbed:
        await callback.message.delete()
        if code:
            await send_manga_by_code(callback.message, code)
        else:
            welcome_text = (
                "✅ *Obuna tasdiqlandi! iNEMO Manga botiga xush kelibsiz.*\n\n"
                "📖 Barcha PDF fayllar himoyalangan. Parol: `@inemo_manga`\n\n"
                "👇 Quyidagi menyudan kerakli bo'limni tanlang:"
            )
            await callback.message.answer(welcome_text, parse_mode="Markdown", reply_markup=main_menu)
    else:
        await callback.answer("Hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)

@dp.message(F.text == "👤 Admin bilan bog'lanish")
async def contact_admin(message: types.Message):
    admin_id = config.ADMIN_IDS[0]
    await message.answer(f"Admin bilan bog'lanish uchun quyidagi profilga yozing:\n👉 [Admin profiliga o'tish](tg://user?id={admin_id})", parse_mode="Markdown")

@dp.message(F.text == "ℹ️ Yordam")
async def help_cmd(message: types.Message):
    text = (
        "📚 *Botdan foydalanish qo'llanmasi:*\n\n"
        "1. *Manga o'qish:* Asosiy kanaldan yuborilgan maxsus havolani bosing. Bot sizga mangani PDF formatida tashlab beradi.\n"
        "2. *Qulfni ochish:* Barcha PDF fayllar himoyalangan. Parol har doim: `@inemo_manga`.\n"
        "3. *Sevimlilarga qo'shish:* Mangani qabul qilib olgach, tagidagi ❤️ tugmani bossangiz, shu manganing yangi qismi chiqqanda bot sizga avtomatik xabar beradi.\n"
        "4. *Admin bilan aloqa:* Pastki menyudan foydalaning."
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "👻 Anonim so'rov yuborish")
async def anonim_request_start(message: types.Message, state: FSMContext):
    await message.answer("📝 Manga nomini, buyurtmani yoki xabaringizni yozib yuboring.\n\n_Admin sizning kimligingizni (profilingizni) ko'rmaydi, faqat xabaringiz yetib boradi._", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    await state.set_state(UserStates.waiting_for_anon_message)

@dp.message(UserStates.waiting_for_anon_message)
async def anonim_request_send(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Iltimos, faqat matnli xabar yuboring.")
        return
        
    admin_id = config.ADMIN_IDS[0]
    await bot.send_message(
        chat_id=admin_id,
        text=f"👻 <b>Yangi anonim so'rov keldi:</b>\n\n<i>{message.text}</i>",
        parse_mode="HTML"
    )
    await message.answer("✅ Xabaringiz adminga anonim tarzda yuborildi!", reply_markup=main_menu)
    await state.clear()

async def send_manga_by_code(message: types.Message, code: str):
    msg_id = await database.get_manga(code)
    if msg_id:
        try:
            # Faylni yopiq kanaldan foydalanuvchiga nusxalab berish (forward qilsa "Yopiq kanal" yozuvi chiqib qolishi mumkin, copy qilingani yaxshi)
            await bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=config.PRIVATE_CHANNEL_ID,
                message_id=msg_id,
                protect_content=True
            )
            series_code = code.split('_')[0] if '_' in code else code
            is_fav = await database.is_favorite(message.chat.id, series_code)
            
            fav_text = "💔 Sevimlilardan olib tashlash" if is_fav else "❤️ Sevimlilarga qo'shish"
            fav_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=fav_text, callback_data=f"fav:{series_code}")]
            ])
            
            await message.answer("🔒 Ushbu PDF fayl qulflangan!\nUni ochish uchun parol: `@inemo_manga`\n_(Parol ustiga bossangiz nusxa oladi)_", parse_mode="Markdown", reply_markup=fav_kb)
        except Exception as e:
            await message.answer("Faylni yuborishda xatolik yuz berdi. Balki u yopiq kanaldan o'chirilgan bo'lishi mumkin.")
            logging.error(f"Copy message error: {e}")
    else:
        await message.answer("Kechirasiz, bunday kodga ega manga topilmadi.")

@dp.callback_query(F.data.startswith("fav:"))
async def toggle_favorite(callback: CallbackQuery):
    series_code = callback.data.split(":")[1]
    is_fav = await database.is_favorite(callback.from_user.id, series_code)
    
    if is_fav:
        await database.remove_favorite(callback.from_user.id, series_code)
        await callback.answer("Sevimlilardan olib tashlandi!", show_alert=True)
        fav_text = "❤️ Sevimlilarga qo'shish"
    else:
        await database.add_favorite(callback.from_user.id, series_code)
        await callback.answer("Sevimlilarga qo'shildi! Yangi qism chiqqanda xabar beramiz.", show_alert=True)
        fav_text = "💔 Sevimlilardan olib tashlash"
        
    fav_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fav_text, callback_data=f"fav:{series_code}")]
    ])
    await callback.message.edit_reply_markup(reply_markup=fav_kb)

# ==================================================
# Admin qismi
# ==================================================
def is_admin(user_id: int):
    return user_id in config.ADMIN_IDS

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish (Majburiy)", callback_data="admin:add_channel")],
        [InlineKeyboardButton(text="➖ Kanallarni ko'rish/o'chirish", callback_data="admin:list_channels")],
        [InlineKeyboardButton(text="📚 Yangi manga (havola) qo'shish", callback_data="admin:add_manga")],
        [InlineKeyboardButton(text="🖼 Eski manga uchun post yaratish", callback_data="admin:old_manga_post")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar soni", callback_data="admin:stats")]
    ])
    await message.answer("Admin paneliga xush kelibsiz. Nima qilamiz?", reply_markup=kb)

@dp.callback_query(F.data.startswith("admin:"))
async def admin_callbacks(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    
    action = callback.data.split(":")[1]
    
    if action == "add_channel":
        await callback.message.answer("Qo'shmoqchi bo'lgan kanalingizning ID raqamini (yoki username) kiriting. Misol: -100123456 yoki @mening_kanalim")
        await state.set_state(AdminStates.waiting_for_channel_id)
        
    elif action == "list_channels":
        channels = await database.get_channels()
        if not channels:
            await callback.message.answer("Majburiy kanallar ro'yxati bo'sh.")
            return
        
        kb = []
        text = "Majburiy kanallar:\n"
        for i, (ch_id, url) in enumerate(channels, 1):
            text += f"{i}. ID: {ch_id} | URL: {url}\n"
            kb.append([InlineKeyboardButton(text=f"O'chirish: {ch_id}", callback_data=f"del_ch:{ch_id}")])
            
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        
    elif action == "add_manga":
        await callback.message.answer("Yopiq kanaldagi postni shu yerga FORWARD (uzatish) qiling.")
        await state.set_state(AdminStates.waiting_for_manga_post)
        
    elif action == "old_manga_post":
        await callback.message.answer("Post yaratmoqchi bo'lgan eski manga kodini kiriting (Masalan: solo_15):")
        await state.set_state(AdminStates.waiting_for_old_manga_code)
        
    elif action == "stats":
        users = await database.get_all_users()
        await callback.message.answer(f"Botdan foydalanayotgan jami odamlar soni: {len(users)} ta.")

    await callback.answer()

# Kanal qo'shish state
@dp.message(AdminStates.waiting_for_channel_id)
async def process_channel_id(message: types.Message, state: FSMContext):
    await state.update_data(channel_id=message.text)
    await message.answer("Endi ushbu kanalning taklif havolasini (URL) kiriting: (Masalan: https://t.me/kanal_linki)")
    await state.set_state(AdminStates.waiting_for_channel_url)

@dp.message(AdminStates.waiting_for_channel_url)
async def process_channel_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ch_id = data['channel_id']
    url = message.text
    
    # Agar ch_id raqam bo'lsa int ga aylantiramiz, username bo'lsa o'zini qoldiramiz (lekin database int yoki string qabul qilishi kerak, biz int dedik. 
    # Shuning uchun eng yaxshisi ID kiritilishini talab qilish). Keling oddiy qilib str saqlasak ham ishlaydi, DB da int bo'lsa string xatosi bo'lmasligi uchun try.
    try:
        ch_id = int(ch_id)
    except:
        pass # username formatida bo'lsa
        
    await database.add_channel(ch_id, url)
    await message.answer(f"Kanal muvaffaqiyatli qo'shildi!\nID: {ch_id}\nURL: {url}")
    await state.clear()

# Kanal o'chirish
@dp.callback_query(F.data.startswith("del_ch:"))
async def del_channel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    ch_id = callback.data.split(":")[1]
    
    try:
        ch_id = int(ch_id)
    except:
        pass
        
    await database.remove_channel(ch_id)
    await callback.message.answer(f"Kanal (ID: {ch_id}) majburiy ro'yxatdan o'chirildi.")
    await callback.answer()

# Manga qo'shish state
@dp.message(AdminStates.waiting_for_manga_post)
async def process_manga_post(message: types.Message, state: FSMContext):
    # Bu yerda message.forward_from_chat orqali yopiq kanaldan kelganini tekshirsa ham bo'ladi, 
    # lekin admin o'zi to'g'ri forward qiladi deb hisoblaymiz.
    if not message.forward_from_chat:
        await message.answer("Iltimos, postni yopiq kanaldan FORWARD qilib tashlang. Men uning qaysi post ekanligini (message_id) bilib olishim kerak.")
        return
        
    if message.forward_from_chat.id != config.PRIVATE_CHANNEL_ID:
        await message.answer(f"Xatolik! Bu post config.py da belgilangan yopiq kanaldan (ID: {config.PRIVATE_CHANNEL_ID}) emas, balki {message.forward_from_chat.id} dan keldi. Iltimos to'g'ri kanaldan forward qiling.")
        return
        
    msg_id = message.forward_from_message_id
    await state.update_data(msg_id=msg_id)
    
    await message.answer(f"Post qabul qilindi (Kanal post ID: {msg_id}). \n\nEndi bu manga uchun qisqa maxsus kod o'ylab toping (bo'sh joysiz, lotin harflarida). \nMasalan: `solo_15`")
    await state.set_state(AdminStates.waiting_for_manga_code)

@dp.message(AdminStates.waiting_for_manga_code)
async def process_manga_code(message: types.Message, state: FSMContext):
    code = message.text.strip().replace(" ", "_")
    data = await state.get_data()
    msg_id = data['msg_id']
    
    await database.add_manga(code, msg_id)
    
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"
    
    await state.update_data(manga_code=code, manga_link=link)
    
    await message.answer(f"✅ Muvaffaqiyatli saqlandi!\n\nUshbu manganing qismini olish uchun tayyor havola:\n{link}\n\nEndi asosiy kanalga yuborish uchun manga rasmini yuboring (faqat rasm):")
    await state.set_state(AdminStates.waiting_for_manga_image)

@dp.message(AdminStates.waiting_for_manga_image, F.photo)
async def process_manga_image(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(manga_photo_id=photo_id)
    await message.answer("✅ Rasm qabul qilindi! Endi post ostidagi matnni (malumotni) kiriting:")
    await state.set_state(AdminStates.waiting_for_manga_caption)

@dp.message(AdminStates.waiting_for_manga_image)
async def process_manga_image_fallback(message: types.Message, state: FSMContext):
    await message.answer("Iltimos, faqat rasm yuboring.")

@dp.message(AdminStates.waiting_for_manga_caption)
async def process_manga_caption(message: types.Message, state: FSMContext):
    data = await state.get_data()
    link = data.get('manga_link')
    code = data.get('manga_code')
    photo_id = data.get('manga_photo_id')
    
    caption = message.text if message.text else "Yangi manga qismi yuklandi!"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 O'qish", url=link)]
    ])
    
    await message.answer_photo(
        photo=photo_id,
        caption=caption,
        caption_entities=message.entities,
        reply_markup=kb
    )
    
    await message.answer("✅ Tayyor post! Buni asosiy kanalingizga yuborishingiz mumkin.")
    
    # Rassilka (xabar yuborish) qismi
    series_code = code.split('_')[0] if '_' in code else code
    users = await database.get_users_by_favorite(series_code)
    
    if users:
        success = 0
        for uid in users:
            try:
                await bot.send_message(uid, f"🎉 *Yangi qism chiqdi!*\n\nSiz kuzatayotgan '{series_code}' mangasi uchun yangi qism yuklandi.\n\n👉 O'qish uchun bosing: {link}", parse_mode="Markdown")
                success += 1
            except:
                pass
        await message.answer(f"📢 {success} ta obunachiga yangi qism haqida xabar yuborildi!")
        
    await state.clear()

@dp.message(AdminStates.waiting_for_old_manga_code)
async def process_old_manga_code(message: types.Message, state: FSMContext):
    code = message.text.strip().replace(" ", "_")
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"
    
    await state.update_data(old_manga_link=link)
    await message.answer(f"Ushbu manganing linki tayyorlandi:\n{link}\n\nEndi post uchun rasmni yuboring (faqat rasm):")
    await state.set_state(AdminStates.waiting_for_old_manga_image)

@dp.message(AdminStates.waiting_for_old_manga_image, F.photo)
async def process_old_manga_image(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(old_manga_photo_id=photo_id)
    await message.answer("✅ Rasm qabul qilindi! Endi post ostidagi matnni (malumotni) kiriting:")
    await state.set_state(AdminStates.waiting_for_old_manga_caption)

@dp.message(AdminStates.waiting_for_old_manga_image)
async def process_old_manga_image_fallback(message: types.Message, state: FSMContext):
    await message.answer("Iltimos, faqat rasm yuboring.")

@dp.message(AdminStates.waiting_for_old_manga_caption)
async def process_old_manga_caption(message: types.Message, state: FSMContext):
    data = await state.get_data()
    link = data.get('old_manga_link')
    photo_id = data.get('old_manga_photo_id')
    
    caption = message.text if message.text else "Manga qismi yuklandi!"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 O'qish", url=link)]
    ])
    
    await message.answer_photo(
        photo=photo_id,
        caption=caption,
        caption_entities=message.entities,
        reply_markup=kb
    )
    
    await message.answer("✅ Tayyor post! Buni asosiy kanalingizga yuborishingiz mumkin.")
    await state.clear()

# ==================================================
# Dummy Web Server (Render uchun)
# ==================================================
async def handle_ping(request):
    return web.Response(text="Bot is alive and running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Dummy web server started on port {port}")

async def keep_alive():
    """Bot o'zini o'zi har 10 daqiqada uyg'otib turishi uchun."""
    url = "https://mangabotserver.onrender.com"
    while True:
        await asyncio.sleep(10 * 60) # 10 daqiqa kutiladi
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    logging.info(f"O'zini uyg'otish so'rovi yuborildi! Holati: {response.status}")
        except Exception as e:
            logging.error(f"Uyg'otishda xatolik: {e}")

# ==================================================
# Asosiy ishga tushirish funksiyasi
# ==================================================

async def main():
    # Render uchun web serverni darhol fonda ishga tushiramiz (portni band qilish uchun)
    asyncio.create_task(start_web_server())
    asyncio.create_task(keep_alive())

    # Bazani ulaymiz
    await database.init_db()
    logging.info("Ma'lumotlar bazasi ishga tushdi.")
    
    # Botni ishga tushiramiz
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
