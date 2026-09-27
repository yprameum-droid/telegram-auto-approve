import asyncio
import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# =========================================================
# ADMIN CONFIG
# =========================================================

# তোমার Telegram numeric User ID এখানে বসাও
ADMIN_ID = 123456789

USERS_PER_PAGE = 10


# =========================================================
# ADMIN CHECK
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# =========================================================
# ADMIN MENU
# =========================================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text(
            "❌ You are not authorized to use Admin Panel."
        )
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📢 Broadcast",
                callback_data="admin_broadcast"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 User List",
                callback_data="admin_users_0"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Statistics",
                callback_data="admin_stats"
            )
        ]
    ])

    await update.message.reply_text(
        "👑 <b>Admin Panel</b>\n\n"
        "Welcome Admin.\n"
        "Choose an option:",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# GET USERS
# =========================================================

def get_all_users():

    connection = context_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT user_id, first_name, username
        FROM users
        ORDER BY user_id DESC
    """)

    users = cursor.fetchall()

    connection.close()

    return users


def context_db():
    import sqlite3

    connection = sqlite3.connect(
        "bot_data.sqlite3",
        check_same_thread=False
    )

    connection.row_factory = sqlite3.Row

    return connection


# =========================================================
# USER LIST
# =========================================================

async def show_users(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    page: int = 0
):

    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer(
            "❌ Admin only.",
            show_alert=True
        )
        return

    users = get_all_users()

    total_users = len(users)

    total_pages = max(
        1,
        (total_users + USERS_PER_PAGE - 1)
        // USERS_PER_PAGE
    )

    if page < 0:
        page = 0

    if page >= total_pages:
        page = total_pages - 1

    start = page * USERS_PER_PAGE
    end = start + USERS_PER_PAGE

    page_users = users[start:end]

    text = (
        "👥 <b>User List</b>\n\n"
        f"Total Users: <b>{total_users}</b>\n"
        f"Page: <b>{page + 1}/{total_pages}</b>\n\n"
    )

    if not page_users:

        text += "No users found."

    else:

        for number, user in enumerate(
            page_users,
            start=start + 1
        ):

            first_name = user["first_name"] or "Unknown"
            username = user["username"]

            if username:
                username_text = f"@{username}"
            else:
                username_text = "No Username"

            text += (
                f"<b>{number}.</b> "
                f"{escape_html(first_name)}\n"
                f"   👤 {username_text}\n"
                f"   🆔 <code>{user['user_id']}</code>\n\n"
            )

    buttons = []

    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                "◀️ Previous",
                callback_data=f"admin_users_{page - 1}"
            )
        )

    if page < total_pages - 1:
        navigation.append(
            InlineKeyboardButton(
                "Next ▶️",
                callback_data=f"admin_users_{page + 1}"
            )
        )

    if navigation:
        buttons.append(navigation)

    buttons.append([
        InlineKeyboardButton(
            "🔎 Search User",
            callback_data="admin_search"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ Admin Panel",
            callback_data="admin_home"
        )
    ])

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


def escape_html(text):

    if not text:
        return ""

    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# =========================================================
# STATISTICS
# =========================================================

async def admin_stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer(
            "❌ Admin only.",
            show_alert=True
        )
        return

    connection = context_db()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT COUNT(*) AS total FROM users"
    )

    total = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE username IS NOT NULL
        AND username != ''
    """)

    username_users = cursor.fetchone()[0]

    connection.close()

    await query.edit_message_text(
        "📊 <b>User Statistics</b>\n\n"
        f"👥 Total Users: <b>{total}</b>\n"
        f"🔹 Users with Username: <b>{username_users}</b>\n"
        f"🔹 Users without Username: "
        f"<b>{total - username_users}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👥 User List",
                    callback_data="admin_users_0"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Admin Panel",
                    callback_data="admin_home"
                )
            ]
        ])
    )


# =========================================================
# BROADCAST START
# =========================================================

async def start_broadcast(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer(
            "❌ Admin only.",
            show_alert=True
        )
        return

    context.user_data["broadcast_mode"] = True

    await query.edit_message_text(
        "📢 <b>Broadcast</b>\n\n"
        "এখন যে message সবাইকে পাঠাতে চান "
        "সেটা পাঠান।\n\n"
        "Text, Photo, Video অথবা Document "
        "পাঠাতে পারবেন।\n\n"
        "❌ Cancel করতে /cancel লিখুন।",
        parse_mode="HTML"
    )


# =========================================================
# CANCEL BROADCAST
# =========================================================

async def cancel_broadcast(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    context.user_data["broadcast_mode"] = False

    await update.message.reply_text(
        "❌ Broadcast cancelled."
    )


# =========================================================
# BROADCAST MESSAGE
# =========================================================

async def broadcast_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not is_admin(user.id):
        return

    if not context.user_data.get(
        "broadcast_mode",
        False
    ):
        return

    context.user_data["broadcast_mode"] = False

    connection = context_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT user_id
        FROM users
    """)

    users = cursor.fetchall()

    connection.close()

    total = len(users)
    success = 0
    failed = 0

    await update.message.reply_text(
        "📢 Broadcast started...\n\n"
        f"👥 Total Users: {total}"
    )

    for row in users:

        user_id = row["user_id"]

        try:

            await update.message.copy(
                chat_id=user_id
            )

            success += 1

        except Exception as error:

            failed += 1

            logger.warning(
                "Broadcast failed for %s: %s",
                user_id,
                error
            )

        # Telegram flood control
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        "✅ <b>Broadcast Completed</b>\n\n"
        f"👥 Total Users: <b>{total}</b>\n"
        f"✅ Successfully Sent: <b>{success}</b>\n"
        f"❌ Failed: <b>{failed}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👑 Admin Panel",
                    callback_data="admin_home"
                )
            ]
        ])
    )


# =========================================================
# SEARCH USER
# =========================================================

async def search_user_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer(
            "❌ Admin only.",
            show_alert=True
        )
        return

    context.user_data["search_user_mode"] = True

    await query.edit_message_text(
        "🔎 <b>Search User</b>\n\n"
        "Username অথবা User ID পাঠান।\n\n"
        "উদাহরণ:\n"
        "<code>@username</code>\n"
        "অথবা\n"
        "<code>123456789</code>\n\n"
        "❌ Cancel করতে /cancel লিখুন।",
        parse_mode="HTML"
    )


async def search_user_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not is_admin(user.id):
        return

    if not context.user_data.get(
        "search_user_mode",
        False
    ):
        return

    context.user_data["search_user_mode"] = False

    search = update.message.text.strip()

    if search.startswith("@"):
        search = search[1:]

    connection = context_db()
    cursor = connection.cursor()

    if search.isdigit():

        cursor.execute("""
            SELECT user_id, first_name, username
            FROM users
            WHERE user_id = ?
        """, (int(search),))

    else:

        cursor.execute("""
            SELECT user_id, first_name, username
            FROM users
            WHERE LOWER(username) = LOWER(?)
        """, (search,))

    rows = cursor.fetchall()

    connection.close()

    if not rows:

        await update.message.reply_text(
            "❌ User পাওয়া যায়নি।"
        )
        return

    text = "🔎 <b>Search Result</b>\n\n"

    for row in rows:

        username = row["username"]

        username_text = (
            f"@{username}"
            if username
            else "No Username"
        )

        text += (
            f"👤 <b>{escape_html(row['first_name'])}</b>\n"
            f"Username: {username_text}\n"
            f"User ID: <code>{row['user_id']}</code>\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👥 User List",
                    callback_data="admin_users_0"
                )
            ],
            [
                InlineKeyboardButton(
                    "👑 Admin Panel",
                    callback_data="admin_home"
                )
            ]
        ])
    )


# =========================================================
# ADMIN CALLBACK ROUTER
# =========================================================

async def admin_callback_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer(
            "❌ Admin only.",
            show_alert=True
        )
        return

    data = query.data

    if data == "admin_home":

        await query.answer()

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📢 Broadcast",
                    callback_data="admin_broadcast"
                )
            ],
            [
                InlineKeyboardButton(
                    "👥 User List",
                    callback_data="admin_users_0"
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 Statistics",
                    callback_data="admin_stats"
                )
            ]
        ])

        await query.edit_message_text(
            "👑 <b>Admin Panel</b>\n\n"
            "Choose an option:",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    elif data == "admin_broadcast":

        await start_broadcast(
            update,
            context
        )

    elif data == "admin_stats":

        await admin_stats(
            update,
            context
        )

    elif data == "admin_search":

        await search_user_start(
            update,
            context
        )

    elif data.startswith("admin_users_"):

        page = int(
            data.replace(
                "admin_users_",
                ""
            )
        )

        await show_users(
            update,
            context,
            page
        )
