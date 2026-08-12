import config
from motor.motor_asyncio import AsyncIOMotorClient
import certifi

# MongoDB'ga ulanish (faqat init_db chaqirilganda ishga tushadi)
client = None
db = None

async def init_db():
    global client, db
    # Ulanishni o'rnatish, TLS sertifikatlarini ko'rsatish
    client = AsyncIOMotorClient(config.MONGO_URL, tlsCAFile=certifi.where())
    db = client.manga_bot_db # Baza nomi

    # Kolleksiyalar avtomatik yaratiladi, faqat kerak bo'lsa index (kalitlar) o'rnatamiz
    await db.channels.create_index("channel_id", unique=True)
    await db.mangas.create_index("code", unique=True)
    await db.favorites.create_index([("user_id", 1), ("series_code", 1)], unique=True)

# --- Foydalanuvchilar ---
async def add_user(user_id: int):
    # Agar foydalanuvchi bo'lmasa, uni qo'shadi (upsert)
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id}},
        upsert=True
    )

async def get_all_users():
    cursor = db.users.find({}, {"user_id": 1, "_id": 0})
    users = await cursor.to_list(length=None)
    return [u["user_id"] for u in users]

# --- Kanallar (Majburiy obuna) ---
async def add_channel(channel_id: int, url: str):
    await db.channels.update_one(
        {"channel_id": channel_id},
        {"$set": {"channel_id": channel_id, "url": url}},
        upsert=True
    )

async def remove_channel(channel_id):
    # Ba'zida MongoDB'da ID string yoki int formatida qolib ketgan bo'lishi mumkin
    try:
        int_id = int(channel_id)
    except:
        int_id = None
        
    str_id = str(channel_id)
    
    query = {"$in": [str_id]}
    if int_id is not None:
        query["$in"].append(int_id)
        
    await db.channels.delete_many({"channel_id": query})

async def get_channels():
    cursor = db.channels.find({}, {"channel_id": 1, "url": 1, "_id": 0})
    channels = await cursor.to_list(length=None)
    return [(ch["channel_id"], ch["url"]) for ch in channels]

# --- Mangalar ---
async def add_manga(code: str, message_id: int):
    await db.mangas.update_one(
        {"code": code},
        {"$set": {"code": code, "message_id": message_id}},
        upsert=True
    )

async def get_manga(code: str):
    manga = await db.mangas.find_one({"code": code})
    return manga["message_id"] if manga else None

# --- Sevimlilar ---
async def add_favorite(user_id: int, series_code: str):
    await db.favorites.update_one(
        {"user_id": user_id, "series_code": series_code},
        {"$set": {"user_id": user_id, "series_code": series_code}},
        upsert=True
    )

async def remove_favorite(user_id: int, series_code: str):
    await db.favorites.delete_one({"user_id": user_id, "series_code": series_code})

async def get_users_by_favorite(series_code: str):
    cursor = db.favorites.find({"series_code": series_code}, {"user_id": 1, "_id": 0})
    favorites = await cursor.to_list(length=None)
    return [f["user_id"] for f in favorites]
            
async def is_favorite(user_id: int, series_code: str) -> bool:
    f = await db.favorites.find_one({"user_id": user_id, "series_code": series_code})
    return f is not None
