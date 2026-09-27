import os
import sqlite3
import logging
from html import escape

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    ContextTypes,
)

# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

REQUIRED_CHANNEL = os.getenv(
    "REQUIRED_CHANNEL",
    "@YourRequiredChannel"
)

REQUIRED_CHANNEL_LINK = os.getenv(
    "REQUIRED_CHANNEL_LINK",
    "https://t.me/YourRequiredChannel"
)

DATABASE_FILE = "bot_data.sqlite3"


if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. Add BOT_TOKEN in Railway Variables."
    )


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# =========================================================
# DATABASE
# =========================================================

def db():
    connection = sqlite3.connect(
        DATABASE_FILE,
        check_same_thread=False
    )

    connection.row_factory = sqlite3.Row

    return connection


def init_database():

    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            username TEXT,
            chat_type TEXT NOT NULL,
            auto_accept INTEGER NOT NULL DEFAULT 1,
            added_by INTEGER,
            added_at INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT
        )
    """)

    connection.commit()
    connection.close()


def save_user(user):

    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO users
        (user_id, first_name, username)
        VALUES (?, ?, ?)
    """, (
        user.id,
        user.first_name or "",
        user.username or ""
    ))

    connection.commit()
    connection.close()


def save_chat(chat, added_by=None):

    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO chats
        (
            chat_id,
            title,
            username,
            chat_type,
            auto_accept,
            added_by,
            added_at
        )
        VALUES (?, ?, ?, ?, 1, ?, strftime('%s','now'))
    """, (
        chat.id,
        chat.title or "Unknown",
        chat.username,
        chat.type,
        added_by
    ))

    cursor.execute("""
        UPDATE chats
        SET
            title = ?,
            username = ?,
            chat_type = ?
        WHERE chat_id = ?
    """, (
        chat.title or "Unknown",
        chat.username,
        chat.type,
        chat.id
    ))

    connection.commit()
    connection.close()


def get_chat(chat_id):

    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM chats
        WHERE chat_id = ?
    """, (chat_id,))

    result = cursor.fetchone()

    connection.close()

    return result


def get_user_chats(user_id, chat_types):

    connection = db()
    cursor = connection.cursor()

    placeholders = ",".join(
        ["?"] * len(chat_types)
    )

    cursor.execute(
        f"""
        SELECT *
        FROM chats
        WHERE chat_type IN ({placeholders})
        ORDER BY title
        """,
        chat_types
    )

    rows = cursor.fetchall()

    connection.close()

    # Only return chats where the user is currently an admin.
    return rows


def set_auto_accept(chat_id, enabled):

    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE chats
        SET auto_accept = ?
        WHERE chat_id = ?
    """, (
        1 if enabled else 0,
        chat_id
    ))

    connection.commit()
    connection.close()


def delete_chat(chat_id):

    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM chats
        WHERE chat_id = ?
    """, (chat_id,))

    connection.commit()
    connection.close()


# =========================================================
# REQUIRED CHANNEL
# =========================================================

async def is_required_channel_member(
    bot,
    user_id
):

    try:

        member = await bot.get_chat_member(
            REQUIRED_CHANNEL,
            user_id
        )

        return member.status in (
            "member",
            "administrator",
            "creator"
        )

    except Exception as error:

        logger.warning(
            "Required channel membership check failed: %s",
            error
        )

        return False


def required_channel_keyboard():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📢 Join Required Channel",
                url=REQUIRED_CHANNEL_LINK
            )
        ],
        [
            InlineKeyboardButton(
                "✅ Check Membership",
                callback_data="check_membership"
            )
        ]
    ])


async def check_gate(
    update,
    context
):

    user = update.effective_user

    if not user:
        return False

    save_user(user)

    member = await is_required_channel_member(
        context.bot,
        user.id
    )

    if member:
        return True

    message = update.effective_message

    if message:

        await message.reply_text(
            "🔒 <b>Channel Join Required</b>\n\n"
            "এই Bot ব্যবহার করার আগে আমাদের "
            "Required Channel-এ Join করুন.\n\n"
            "প্রথমে Channel-এ Join করুন, "
            "তারপর নিচের Check Membership চাপুন.",
            parse_mode="HTML",
            reply_markup=required_channel_keyboard()
        )

    return False


# =========================================================
# CHAT ADMIN CHECK
# =========================================================

async def is_chat_admin(
    bot,
    chat_id,
    user_id
):

    try:

        member = await bot.get_chat_member(
            chat_id,
            user_id
        )

        return member.status in (
            "administrator",
            "creator"
        )

    except Exception as error:

        logger.warning(
            "Admin check failed: %s",
            error
        )

        return False


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await check_gate(
        update,
        context
    ):
        return

    await show_main_menu(
        update,
        context
    )


# =========================================================
# MAIN MENU
# =========================================================

async def show_main_menu(
    update,
    context
):

    user = update.effective_user

    text = (
        f"👋 Hello <b>{escape(user.first_name)}</b>\n\n"
        "🤖 <b>Join Request Management Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "This bot helps you:\n\n"
        "✅ Manage join requests for your "
        "groups and channels\n"
        "📢 Automatically approve requests\n"
        "⚙️ Control each chat separately\n\n"
        "👇 Choose an option:"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Add Channel",
                callback_data="add_channel"
            ),
            InlineKeyboardButton(
                "➕ Add Group",
                callback_data="add_group"
            )
        ],
        [
            InlineKeyboardButton(
                "📋 My Channels",
                callback_data="my_channels"
            ),
            InlineKeyboardButton(
                "👥 My Groups",
                callback_data="my_groups"
            )
        ],
        [
            InlineKeyboardButton(
                "ℹ️ Help",
                callback_data="help"
            )
        ]
    ])

    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# MEMBERSHIP CHECK BUTTON
# =========================================================

async def check_membership(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    ok = await is_required_channel_member(
        context.bot,
        query.from_user.id
    )

    if not ok:

        await query.edit_message_text(
            "❌ <b>Membership Not Found</b>\n\n"
            "আপনি এখনো Required Channel-এ "
            "Join করেননি.",
            parse_mode="HTML",
            reply_markup=required_channel_keyboard()
        )

        return

    await query.edit_message_text(
        "✅ <b>Membership Verified!</b>\n\n"
        "এখন আপনি Bot ব্যবহার করতে পারবেন.",
        parse_mode="HTML"
    )

    await query.message.reply_text(
        "👇 <b>Main Menu</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "➕ Add Channel",
                    callback_data="add_channel"
                ),
                InlineKeyboardButton(
                    "➕ Add Group",
                    callback_data="add_group"
                )
            ],
            [
                InlineKeyboardButton(
                    "📋 My Channels",
                    callback_data="my_channels"
                ),
                InlineKeyboardButton(
                    "👥 My Groups",
                    callback_data="my_groups"
                )
            ],
            [
                InlineKeyboardButton(
                    "ℹ️ Help",
                    callback_data="help"
                )
            ]
        ])
    )


# =========================================================
# ADD CHANNEL
# =========================================================

async def add_channel(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    bot_username = context.bot.username

    add_link = (
        f"https://t.me/{bot_username}"
        f"?startchannel"
        f"&admin=invite_users"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Add Bot to Channel",
                url=add_link
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Check My Channels",
                callback_data="my_channels"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data="back"
            )
        ]
    ])

    await query.edit_message_text(
        "📢 <b>Add a New Channel</b>\n\n"
        "1️⃣ নিচের Add Button চাপুন\n"
        "2️⃣ আপনার Channel নির্বাচন করুন\n"
        "3️⃣ Bot-কে Administrator করুন\n"
        "4️⃣ <b>Invite Users via Link</b> permission দিন\n\n"
        "Bot Admin হলে Channel automatically "
        "আপনার My Channels list-এ যুক্ত হবে.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# ADD GROUP
# =========================================================

async def add_group(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    bot_username = context.bot.username

    add_link = (
        f"https://t.me/{bot_username}"
        f"?startgroup=addbot"
        f"&admin=invite_users"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Add Bot to Group",
                url=add_link
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Check My Groups",
                callback_data="my_groups"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data="back"
            )
        ]
    ])

    await query.edit_message_text(
        "👥 <b>Add a New Group</b>\n\n"
        "1️⃣ নিচের Add Button চাপুন\n"
        "2️⃣ আপনার Group নির্বাচন করুন\n"
        "3️⃣ Bot-কে Administrator করুন\n"
        "4️⃣ <b>Invite Users via Link</b> permission দিন\n\n"
        "Bot Admin হলে Group automatically "
        "আপনার My Groups list-এ যুক্ত হবে.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# BOT ADDED / PROMOTED
# =========================================================

async def bot_chat_member_update(
    update,
    context
):

    event = update.my_chat_member

    if not event:
        return

    chat = event.chat
    new_member = event.new_chat_member

    if chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
        ChatType.CHANNEL
    ):
        return

    # Bot must be administrator
    if new_member.status != "administrator":

        if new_member.status in (
            "left",
            "kicked"
        ):

            delete_chat(chat.id)

        return

    # Join-request permission
    can_invite = getattr(
        new_member,
        "can_invite_users",
        False
    )

    if not can_invite:

        try:

            await context.bot.send_message(
                chat_id=event.from_user.id,
                text=(
                    "⚠️ <b>Permission Required</b>\n\n"
                    f"Chat: <b>{escape(chat.title or '')}</b>\n\n"
                    "Bot Admin হয়েছে, কিন্তু "
                    "<b>Invite Users via Link</b> permission "
                    "দেওয়া হয়নি.\n\n"
                    "এই permission দিন যাতে Bot Join Request "
                    "receive এবং approve করতে পারে."
                ),
                parse_mode="HTML"
            )

        except Exception:
            pass

        return

    # Save chat
    save_chat(
        chat,
        event.from_user.id
    )

    logger.info(
        "Registered chat: %s (%s)",
        chat.title,
        chat.id
    )

    # Notify person who added/promoted bot
    try:

        await context.bot.send_message(
            chat_id=event.from_user.id,
            text=(
                "✅ <b>Bot Added Successfully!</b>\n\n"
                f"📢 Chat: <b>{escape(chat.title or '')}</b>\n"
                f"⚙️ Auto-approve: <b>Enabled</b>\n\n"
                "The bot is now ready to manage "
                "join requests."
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⚙️ Manage Chat",
                        callback_data=f"manage:{chat.id}"
                    )
                ]
            ])
        )

    except Exception as error:

        logger.warning(
            "Could not notify admin: %s",
            error
        )


# =========================================================
# MY CHANNELS
# =========================================================

async def my_channels(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    rows = get_user_chats(
        query.from_user.id,
        [ChatType.CHANNEL]
    )

    # Verify the user is currently admin
    valid_rows = []

    for row in rows:

        if await is_chat_admin(
            context.bot,
            row["chat_id"],
            query.from_user.id
        ):

            valid_rows.append(row)

    if not valid_rows:

        await query.edit_message_text(
            "📋 <b>My Channels</b>\n\n"
            "আপনার কোনো Channel এখনো যুক্ত নেই.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "➕ Add Channel",
                        callback_data="add_channel"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="back"
                    )
                ]
            ])
        )

        return

    buttons = []

    for row in valid_rows:

        status = (
            "🟢"
            if row["auto_accept"]
            else "🔴"
        )

        buttons.append([
            InlineKeyboardButton(
                f"{status} {row['title'][:35]}",
                callback_data=f"manage:{row['chat_id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ Back",
            callback_data="back"
        )
    ])

    await query.edit_message_text(
        "📋 <b>My Channels</b>\n\n"
        "Manage করতে Channel নির্বাচন করুন:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# =========================================================
# MY GROUPS
# =========================================================

async def my_groups(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    rows = get_user_chats(
        query.from_user.id,
        [
            ChatType.GROUP,
            ChatType.SUPERGROUP
        ]
    )

    valid_rows = []

    for row in rows:

        if await is_chat_admin(
            context.bot,
            row["chat_id"],
            query.from_user.id
        ):

            valid_rows.append(row)

    if not valid_rows:

        await query.edit_message_text(
            "👥 <b>My Groups</b>\n\n"
            "আপনার কোনো Group এখনো যুক্ত নেই.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "➕ Add Group",
                        callback_data="add_group"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="back"
                    )
                ]
            ])
        )

        return

    buttons = []

    for row in valid_rows:

        status = (
            "🟢"
            if row["auto_accept"]
            else "🔴"
        )

        buttons.append([
            InlineKeyboardButton(
                f"{status} {row['title'][:35]}",
                callback_data=f"manage:{row['chat_id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ Back",
            callback_data="back"
        )
    ])

    await query.edit_message_text(
        "👥 <b>My Groups</b>\n\n"
        "Manage করতে Group নির্বাচন করুন:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# =========================================================
# MANAGE CHAT
# =========================================================

async def manage_chat(
    update,
    context,
    chat_id=None
):

    query = update.callback_query

    if chat_id is None:
        chat_id = int(
            query.data.split(":")[1]
        )

    row = get_chat(chat_id)

    if not row:

        await query.answer(
            "Chat not found.",
            show_alert=True
        )

        return

    # User must currently be admin
    if not await is_chat_admin(
        context.bot,
        chat_id,
        query.from_user.id
    ):

        await query.answer(
            "❌ আপনি এই Chat-এর Admin নন.",
            show_alert=True
        )

        return

    await query.answer()

    state = (
        "🟢 ENABLED"
        if row["auto_accept"]
        else "🔴 DISABLED"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🟢 Auto Accept ON",
                callback_data=f"on:{chat_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🔴 Auto Accept OFF",
                callback_data=f"off:{chat_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🗑 Remove",
                callback_data=f"remove:{chat_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data="back"
            )
        ]
    ])

    await query.edit_message_text(
        "⚙️ <b>Manage Chat</b>\n\n"
        f"📢 <b>{escape(row['title'])}</b>\n\n"
        f"Auto Approve: <b>{state}</b>\n\n"
        "🟢 ON = Join Request automatically approve\n"
        "🔴 OFF = Request pending থাকবে",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# TOGGLE
# =========================================================

async def toggle_auto_accept(
    update,
    context
):

    query = update.callback_query

    action, chat_id_text = query.data.split(":")

    chat_id = int(chat_id_text)

    if not await is_chat_admin(
        context.bot,
        chat_id,
        query.from_user.id
    ):

        await query.answer(
            "❌ শুধু ওই Chat-এর Admin এটি পরিবর্তন করতে পারবেন.",
            show_alert=True
        )

        return

    set_auto_accept(
        chat_id,
        action == "on"
    )

    await query.answer(
        "Auto Accept updated."
    )

    await manage_chat(
        update,
        context,
        chat_id
    )


# =========================================================
# REMOVE CHAT
# =========================================================

async def remove_chat_callback(
    update,
    context
):

    query = update.callback_query

    chat_id = int(
        query.data.split(":")[1]
    )

    if not await is_chat_admin(
        context.bot,
        chat_id,
        query.from_user.id
    ):

        await query.answer(
            "❌ Admin only.",
            show_alert=True
        )

        return

    delete_chat(chat_id)

    await query.answer()

    await query.edit_message_text(
        "✅ <b>Chat Removed</b>\n\n"
        "এই Chat আর Bot-এর managed list-এ থাকবে না.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ Main Menu",
                    callback_data="back"
                )
            ]
        ])
    )


# =========================================================
# JOIN REQUEST
# =========================================================

async def handle_join_request(
    update,
    context
):

    request = update.chat_join_request

    if not request:
        return

    chat = request.chat
    user = request.from_user

    row = get_chat(chat.id)

    if not row:

        logger.warning(
            "Received request from unregistered chat: %s",
            chat.id
        )

        return

    logger.info(
        "Join request: user=%s chat=%s",
        user.id,
        chat.id
    )

    # -----------------------------------------------------
    # STEP 1: SEND REVIEW MESSAGE IMMEDIATELY
    # -----------------------------------------------------

    try:

        await context.bot.send_message(
            chat_id=request.user_chat_id,
            text=(
                "⏳ <b>Your Join Request Has Been Received</b>\n\n"
                f"📢 <b>{escape(chat.title or '')}</b>\n\n"
                "🔎 <b>Your request is being reviewed.</b>\n"
                "Please wait..."
            ),
            parse_mode="HTML"
        )

    except Exception as error:

        logger.warning(
            "Could not send review message: %s",
            error
        )

    # -----------------------------------------------------
    # STEP 2: CHECK AUTO ACCEPT
    # -----------------------------------------------------

    if not row["auto_accept"]:

        logger.info(
            "Auto Accept OFF for chat %s",
            chat.id
        )

        return

    # -----------------------------------------------------
    # STEP 3: APPROVE
    # -----------------------------------------------------

    try:

        await context.bot.approve_chat_join_request(
            chat_id=chat.id,
            user_id=user.id
        )

        logger.info(
            "Join request approved: user=%s chat=%s",
            user.id,
            chat.id
        )

    except Exception as error:

        logger.error(
            "Approve failed: %s",
            error
        )

        try:

            await context.bot.send_message(
                chat_id=request.user_chat_id,
                text=(
                    "⚠️ <b>Your request could not be "
                    "approved automatically.</b>\n\n"
                    "Please wait for an administrator."
                ),
                parse_mode="HTML"
            )

        except Exception:
            pass

        return

    # -----------------------------------------------------
    # STEP 4: APPROVED MESSAGE
    # -----------------------------------------------------

    try:

        await context.bot.send_message(
            chat_id=request.user_chat_id,
            text=(
                "✅ <b>Your Join Request Has Been Approved!</b>\n\n"
                f"📢 <b>{escape(chat.title or '')}</b>\n\n"
                "You can now access the chat."
            ),
            parse_mode="HTML"
        )

    except Exception as error:

        logger.warning(
            "Could not send approval message: %s",
            error
        )


# =========================================================
# HELP
# =========================================================

async def help_command(
    update,
    context
):

    if not await check_gate(
        update,
        context
    ):
        return

    await update.effective_message.reply_text(
        "ℹ️ <b>How It Works</b>\n\n"
        "1️⃣ Required Channel-এ Join করুন\n"
        "2️⃣ Add Channel অথবা Add Group চাপুন\n"
        "3️⃣ Bot-কে Administrator করুন\n"
        "4️⃣ Invite Users via Link permission দিন\n"
        "5️⃣ My Channels/My Groups থেকে Chat manage করুন\n"
        "6️⃣ Auto Accept ON করলে Join Request "
        "সঙ্গে সঙ্গে approve হবে.",
        parse_mode="HTML"
    )


# =========================================================
# BACK
# =========================================================

async def back(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    if not await is_required_channel_member(
        context.bot,
        query.from_user.id
    ):

        await query.edit_message_text(
            "🔒 Required Channel-এ আগে Join করুন.",
            reply_markup=required_channel_keyboard()
        )

        return

    await query.edit_message_text(
        "👇 <b>Main Menu</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "➕ Add Channel",
                    callback_data="add_channel"
                ),
                InlineKeyboardButton(
                    "➕ Add Group",
                    callback_data="add_group"
                )
            ],
            [
                InlineKeyboardButton(
                    "📋 My Channels",
                    callback_data="my_channels"
                ),
                InlineKeyboardButton(
                    "👥 My Groups",
                    callback_data="my_groups"
                )
            ],
            [
                InlineKeyboardButton(
                    "ℹ️ Help",
                    callback_data="help"
                )
            ]
        ])
    )


# =========================================================
# CALLBACK ROUTER
# =========================================================

async def callback_router(
    update,
    context
):

    query = update.callback_query
    data = query.data

    # Membership button is allowed before membership
    if data == "check_membership":

        await check_membership(
            update,
            context
        )

        return

    # Everything else requires membership
    if not await is_required_channel_member(
        context.bot,
        query.from_user.id
    ):

        await query.answer(
            "🔒 আগে Required Channel-এ Join করুন.",
            show_alert=True
        )

        return

    if data == "add_channel":

        await add_channel(
            update,
            context
        )

    elif data == "add_group":

        await add_group(
            update,
            context
        )

    elif data == "my_channels":

        await my_channels(
            update,
            context
        )

    elif data == "my_groups":

        await my_groups(
            update,
            context
        )

    elif data == "help":

        await help_command(
            update,
            context
        )

    elif data == "back":

        await back(
            update,
            context
        )

    elif data.startswith("manage:"):

        await manage_chat(
            update,
            context
        )

    elif data.startswith("on:"):

        await toggle_auto_accept(
            update,
            context
        )

    elif data.startswith("off:"):

        await toggle_auto_accept(
            update,
            context
        )

    elif data.startswith("remove:"):

        await remove_chat_callback(
            update,
            context
        )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update,
    context
):

    logger.error(
        "Unhandled error:",
        exc_info=context.error
    )


# =========================================================
# MAIN
# =========================================================

def main():

    init_database()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # /start
    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # /help
    application.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    # Detect bot added/promoted
    application.add_handler(
        ChatMemberHandler(
            bot_chat_member_update,
            ChatMemberHandler.MY_CHAT_MEMBER
        )
    )

    # Join requests
    application.add_handler(
        ChatJoinRequestHandler(
            handle_join_request
        )
    )

    # Inline buttons
    application.add_handler(
        CallbackQueryHandler(
            callback_router
        )
    )

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "========================================"
    )

    logger.info(
        "AUTO APPROVE BOT STARTED"
    )

    logger.info(
        "Required Channel: %s",
        REQUIRED_CHANNEL
    )

    logger.info(
        "========================================"
    )

    application.run_polling(
        allowed_updates=[
            "message",
            "callback_query",
            "my_chat_member",
            "chat_join_request"
        ]
    )


if __name__ == "__main__":
    main()
