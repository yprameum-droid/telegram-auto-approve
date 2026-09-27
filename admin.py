import os
import asyncio
import sqlite3
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest, RetryAfter
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

DATABASE_FILE = os.getenv("DATABASE_FILE", "bot_data.sqlite3")
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "0").strip()
try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    ADMIN_ID = 0

USERS_PER_PAGE = 10


def is_admin(user_id: int) -> bool:
    return bool(ADMIN_ID) and user_id == ADMIN_ID


def db():
    connection = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def get_user_count() -> int:
    connection = db()
    try:
        return connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        connection.close()


def get_users(page: int = 0):
    offset = max(0, page) * USERS_PER_PAGE
    connection = db()
    try:
        return connection.execute(
            """
            SELECT user_id, first_name, username
            FROM users
            ORDER BY user_id DESC
            LIMIT ? OFFSET ?
            """,
            (USERS_PER_PAGE, offset),
        ).fetchall()
    finally:
        connection.close()


def search_users(term: str):
    term = term.strip().lstrip("@").strip()
    connection = db()
    try:
        if term.isdigit():
            return connection.execute(
                """
                SELECT user_id, first_name, username
                FROM users
                WHERE user_id = ?
                ORDER BY user_id DESC
                LIMIT 50
                """,
                (int(term),),
            ).fetchall()

        like = f"%{term}%"
        return connection.execute(
            """
            SELECT user_id, first_name, username
            FROM users
            WHERE username LIKE ? COLLATE NOCASE
               OR first_name LIKE ? COLLATE NOCASE
            ORDER BY user_id DESC
            LIMIT 50
            """,
            (like, like),
        ).fetchall()
    finally:
        connection.close()


def format_user(row) -> str:
    username = row["username"] or "—"
    if username != "—":
        username = f"@{username.lstrip('@')}"
    first_name = row["first_name"] or "—"
    return (
        f"👤 <b>{first_name}</b>\n"
        f"🔹 Username: <code>{username}</code>\n"
        f"🆔 ID: <code>{row['user_id']}</code>"
    )


def admin_home_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
            InlineKeyboardButton("👥 Users", callback_data="admin_users:0"),
        ],
        [
            InlineKeyboardButton("🔎 Search User", callback_data="admin_search"),
            InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
        ],
    ])


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id):
        return

    context.user_data.pop("admin_state", None)
    count = get_user_count()
    await update.effective_message.reply_text(
        "🔐 <b>Admin Panel</b>\n\n"
        f"👥 Total users: <b>{count}</b>\n\n"
        "নিচের অপশন থেকে কাজ নির্বাচন করুন:",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_home_keyboard(),
    )


async def show_users(query, page: int = 0):
    total = get_user_count()
    max_page = max(0, (total - 1) // USERS_PER_PAGE)
    page = max(0, min(page, max_page))
    rows = get_users(page)

    text = f"👥 <b>User List</b> — {total} users\n"
    text += f"📄 Page {page + 1}/{max_page + 1}\n\n"

    if not rows:
        text += "কোনো user পাওয়া যায়নি।"
    else:
        start = page * USERS_PER_PAGE + 1
        for index, row in enumerate(rows, start):
            username = row["username"] or "—"
            if username != "—":
                username = f"@{username.lstrip('@')}"
            text += (
                f"<b>{index}.</b> {row['first_name'] or '—'}\n"
                f"   Username: <code>{username}</code>\n"
                f"   ID: <code>{row['user_id']}</code>\n\n"
            )

    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"admin_users:{page - 1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin_users:{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([
        InlineKeyboardButton("🔎 Search", callback_data="admin_search"),
        InlineKeyboardButton("⬅️ Admin Home", callback_data="admin_home"),
    ])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    if not user or not is_admin(user.id):
        await query.answer("❌ Admin only.", show_alert=True)
        return

    await query.answer()
    data = query.data or ""

    if data == "admin_home":
        context.user_data.pop("admin_state", None)
        count = get_user_count()
        await query.edit_message_text(
            "🔐 <b>Admin Panel</b>\n\n"
            f"👥 Total users: <b>{count}</b>\n\n"
            "নিচের অপশন থেকে কাজ নির্বাচন করুন:",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_home_keyboard(),
        )
        return

    if data == "admin_broadcast":
        context.user_data["admin_state"] = "broadcast"
        await query.edit_message_text(
            "📢 <b>Broadcast</b>\n\n"
            "এখন যে message পাঠাতে চান সেটি এখানে পাঠান।\n"
            "Text, photo, video, documentসহ Telegram message পাঠানো যাবে।\n\n"
            "❌ বন্ধ করতে /cancel লিখুন।",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]
            ]),
        )
        return

    if data == "admin_cancel":
        context.user_data.pop("admin_state", None)
        await query.edit_message_text(
            "✅ কাজ বাতিল করা হয়েছে।",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Admin Home", callback_data="admin_home")]
            ]),
        )
        return

    if data.startswith("admin_users:"):
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            page = 0
        await show_users(query, page)
        return

    if data == "admin_search":
        context.user_data["admin_state"] = "search"
        await query.edit_message_text(
            "🔎 <b>Search User</b>\n\n"
            "Username (with/without @), name অথবা User ID পাঠান।\n\n"
            "❌ বন্ধ করতে /cancel লিখুন।",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]
            ]),
        )
        return

    if data == "admin_stats":
        count = get_user_count()
        await query.edit_message_text(
            "📊 <b>Bot Statistics</b>\n\n"
            f"👥 Total registered users: <b>{count}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 User List", callback_data="admin_users:0")],
                [InlineKeyboardButton("⬅️ Admin Home", callback_data="admin_home")],
            ]),
        )
        return


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not is_admin(user.id):
        return False

    if context.user_data.get("admin_state") != "broadcast":
        return False

    connection = db()
    try:
        user_ids = [row[0] for row in connection.execute("SELECT user_id FROM users")]
    finally:
        connection.close()

    context.user_data.pop("admin_state", None)

    sent = 0
    failed = 0
    removed = 0

    status = await message.reply_text(
        f"📢 Broadcast শুরু হয়েছে...\n👥 মোট {len(user_ids)} users",
    )

    for user_id in user_ids:
        if user_id == ADMIN_ID:
            continue
        try:
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id,
            )
            sent += 1
            await asyncio.sleep(0.04)
        except RetryAfter as error:
            await asyncio.sleep(float(error.retry_after) + 0.5)
            try:
                await context.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id,
                )
                sent += 1
            except Exception:
                failed += 1
        except (Forbidden, BadRequest):
            failed += 1
        except Exception as error:
            failed += 1
            logger.warning("Broadcast failed for %s: %s", user_id, error)

    await status.edit_text(
        "✅ <b>Broadcast Completed</b>\n\n"
        f"📨 Sent: <b>{sent}</b>\n"
        f"❌ Failed: <b>{failed}</b>\n"
        f"👥 Total targeted: <b>{max(0, len(user_ids) - (1 if ADMIN_ID in user_ids else 0))}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_home_keyboard(),
    )
    return True


async def search_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not is_admin(user.id):
        return False

    if context.user_data.get("admin_state") != "search":
        return False

    term = message.text or message.caption or ""
    rows = search_users(term)
    context.user_data.pop("admin_state", None)

    if not rows:
        text = (
            "🔎 <b>Search Result</b>\n\n"
            f"কোনো user পাওয়া যায়নি: <code>{term}</code>"
        )
    else:
        text = f"🔎 <b>Search Result</b> — {len(rows)} found\n\n"
        for index, row in enumerate(rows, 1):
            text += f"<b>{index}.</b> {format_user(row)}\n\n"

    await message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎 Search Again", callback_data="admin_search")],
            [InlineKeyboardButton("👥 User List", callback_data="admin_users:0")],
            [InlineKeyboardButton("⬅️ Admin Home", callback_data="admin_home")],
        ]),
    )
    return True


async def admin_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id):
        return

    state = context.user_data.get("admin_state")
    if state == "broadcast":
        await broadcast_message(update, context)
    elif state == "search":
        await search_user_message(update, context)


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id):
        return

    context.user_data.pop("admin_state", None)
    await update.effective_message.reply_text(
        "✅ Admin operation cancelled.",
        reply_markup=admin_home_keyboard(),
    )
