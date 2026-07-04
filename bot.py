"""
Bovari Marketing - Buyurtma Kuzatuv Boti
==========================================
Mijozlar kod orqali o'z reels buyurtmasi holatini bilib olishadi.
Video tayyor bo'lganda, admin uni kod bilan botga yuboradi - bot mijozga yetkazadi.
"""

import logging
import os
import random
import sqlite3
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ============================================================
# SOZLAMALAR
# ============================================================
# Bu ikkitasi fayl ichiga yozilmaydi — muhit o'zgaruvchisi (environment
# variable) sifatida beriladi. Railway/Render kabi xizmatning "Variables"
# bo'limiga kiritasiz, fayl bilan ishlash shart emas.
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Vergul bilan ajratilgan ID'lar: "123456789,987654321"
ADMIN_IDS = [
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()
]

DB_PATH = "bovari_orders.db"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN muhit o'zgaruvchisi topilmadi.")
if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS muhit o'zgaruvchisi topilmadi.")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Kodda chalkashtiruvchi harflar/raqamlar olib tashlandi: 0, O, 1, I, L
CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


# ============================================================
# DATABASE FUNKSIYALARI
# ============================================================
def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            code TEXT PRIMARY KEY,
            client_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'jarayonda',
            client_chat_id INTEGER,
            video_file_id TEXT,
            created_at TEXT,
            ready_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def get_order(code: str):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT * FROM orders WHERE code = ?", (code,)).fetchone()
    conn.close()
    return row


def add_order(code: str, client_name: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO orders (code, client_name, status, created_at) VALUES (?, ?, 'jarayonda', ?)",
        (code, client_name, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def register_client_chat_id(code: str, chat_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE orders SET client_chat_id = ? WHERE code = ?", (chat_id, code))
    conn.commit()
    conn.close()


def mark_ready(code: str, video_file_id: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE orders SET status = 'tayyor', video_file_id = ?, ready_at = ? WHERE code = ?",
        (video_file_id, datetime.now().isoformat(), code),
    )
    conn.commit()
    conn.close()


def generate_unique_code() -> str:
    while True:
        code = "".join(random.choices(CODE_CHARS, k=6))
        if not get_order(code):
            return code


# ============================================================
# MIJOZ UCHUN HANDLER'LAR
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Assalomu alaykum! Bovari Marketing botiga xush kelibsiz.\n\n"
        "Buyurtmangiz holatini bilish uchun sizga berilgan kodni shu yerga yozing."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Foydalanuvchi kod yuborganda ishlaydi (buyruq bo'lmagan har qanday matn)."""
    code = update.message.text.strip().upper()
    chat_id = update.message.chat_id

    order = get_order(code)
    if not order:
        await update.message.reply_text(
            "Bunday kod topilmadi. Kodni tekshirib, qaytadan yuboring."
        )
        return

    _, client_name, status, _, video_file_id, _, _ = order

    # Bot keyinchalik avtomatik yuborishi uchun chat_id'ni eslab qoladi
    register_client_chat_id(code, chat_id)

    if status == "tayyor":
        await update.message.reply_text(f"Salom {client_name}! Reels videongiz tayyor 🎬")
        if video_file_id:
            await context.bot.send_video(chat_id=chat_id, video=video_file_id)
        else:
            await update.message.reply_text(
                "Video topilmadi, iltimos admin bilan bog'laning."
            )
    else:
        await update.message.reply_text(
            f"Salom {client_name}! Buyurtmangiz hali jarayonda.\n"
            f"Tayyor bo'lishi bilan video shu yerga avtomatik yuboriladi."
        )


# ============================================================
# ADMIN UCHUN HANDLER'LAR
# ============================================================
def _is_admin(update: Update) -> bool:
    return update.effective_user.id in ADMIN_IDS


async def new_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/yangi <mijoz_nomi> - yangi buyurtma va kod yaratadi"""
    if not _is_admin(update):
        return

    if not context.args:
        await update.message.reply_text("Foydalanish: /yangi Mijoz Nomi")
        return

    client_name = " ".join(context.args)
    code = generate_unique_code()
    add_order(code, client_name)

    await update.message.reply_text(
        f"✅ Yangi buyurtma yaratildi\n\n"
        f"Mijoz: {client_name}\n"
        f"Kod: {code}\n\n"
        f"Shu kodni mijozga bering."
    )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin videoni kod bilan (caption sifatida) yuborganda ishlaydi"""
    if not _is_admin(update):
        return

    caption = update.message.caption
    if not caption:
        await update.message.reply_text(
            "Video bilan birga buyurtma kodini caption qilib yozing. Masalan: K7XQ2M"
        )
        return

    code = caption.strip().upper()
    order = get_order(code)
    if not order:
        await update.message.reply_text(f"'{code}' kodli buyurtma topilmadi.")
        return

    _, client_name, _, client_chat_id, _, _, _ = order
    video_file_id = update.message.video.file_id
    mark_ready(code, video_file_id)

    await update.message.reply_text(f"'{client_name}' ({code}) buyurtmasi tayyor deb belgilandi.")

    if client_chat_id:
        await context.bot.send_message(
            chat_id=client_chat_id, text=f"Salom {client_name}! Reels videongiz tayyor 🎬"
        )
        await context.bot.send_video(chat_id=client_chat_id, video=video_file_id)
        await update.message.reply_text("Mijozga avtomatik yuborildi ✅")
    else:
        await update.message.reply_text(
            "Mijoz hali botga yozmagan — kodini kiritgan zahoti video avtomatik yuboriladi."
        )


async def list_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/royxat - jarayondagi barcha buyurtmalarni ko'rsatadi"""
    if not _is_admin(update):
        return

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT code, client_name FROM orders WHERE status = 'jarayonda' ORDER BY created_at"
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Jarayondagi buyurtmalar yo'q.")
        return

    text = "📋 Jarayondagi buyurtmalar:\n\n" + "\n".join(
        f"• {name} — {code}" for code, name in rows
    )
    await update.message.reply_text(text)


# ============================================================
# ASOSIY DASTUR
# ============================================================
def main() -> None:
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("yangi", new_order))
    app.add_handler(CommandHandler("royxat", list_pending))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
