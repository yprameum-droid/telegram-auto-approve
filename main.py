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
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

REQUIRED_CHANNEL = os.getenv(
    "REQUIRED_CHANNEL",
    "@YourRequiredChannel"
)

REQUIRED_CHANNEL_LINK = os.getenv(
    "REQUIRED_CHANNEL_LINK",
    "https://t.me/YourRequiredChannel"
)

DB_FILE = "bot.sqlite3"


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")


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

def connect_db():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            username TEXT,
            chat_type TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            auto_accept INTEGER DEFAULT 1,
            welcome_enabled INTEGER DEFAULT 1,
            welcome_message TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_user(user):

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO users
        (user_id, first_name, username)
        VALUES (?, ?, ?)
    """, (
        user.id,
        user.first_name or "",
        user.username or ""
    ))

    conn.commit()
    conn.close()


def save_chat(
    chat,
    owner_id,
    auto_accept=1
):

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO chats
        (
            chat_id,
            title,
            username,
            chat_type,
            owner_id,
            auto_accept
        )
        VALUES (?, ?, ?, ?, ?, ?)

        ON CONFLICT(chat_id)
        DO UPDATE SET
            title=excluded.title,
            username=excluded.username,
            chat_type=excluded.chat_type
    """, (
        chat.id,
        chat.title or "",
        chat.username,
        chat.type,
        owner_id,
        auto_accept
    ))

    conn.commit()
    conn.close()


def get_chat(chat_id):

    conn = connect_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM chats WHERE chat_id=?",
        (chat_id,)
    )

    row = cur.fetchone()

    conn.close()

    return row


def get_user_chats(
    user_id,
    chat_type
):

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM chats
        WHERE owner_id=?
        AND chat_type=?
        ORDER BY title
    """, (
        user_id,
        chat_type
    ))

    rows = cur.fetchall()

    conn.close()

    return rows


def set_auto_accept(
    chat_id,
    value
):

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE chats
        SET auto_accept=?
        WHERE chat_id=?
    """, (
        1 if value else 0,
        chat_id
    ))

    conn.commit()
    conn.close()


def set_welcome(
    chat_id,
    enabled
):

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE chats
        SET welcome_enabled=?
        WHERE chat_id=?
    """, (
        1 if enabled else 0,
        chat_id
    ))

    conn.commit()
    conn.close()


def remove_chat(chat_id):

    conn = connect_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM chats WHERE chat_id=?",
        (chat_id,)
    )

    conn.commit()
    conn.close()


# =========================================================
# REQUIRED CHANNEL
# =========================================================

async def check_required_channel(
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

    except Exception as e:

        logger.warning(
            "Required channel check failed: %s",
            e
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


async def gate(
    update,
    context
):

    user = update.effective_user

    if not user:
        return False

    save_user(user)

    # Owner bypass
    if OWNER_ID and user.id == OWNER_ID:
        return True

    ok = await check_required_channel(
        context.bot,
        user.id
    )

    if ok:
        return True

    message = update.effective_message

    if message:

        await message.reply_text(
            "🔒 <b>Channel Join Required</b>\n\n"
            "এই Bot ব্যবহার করার আগে আমাদের "
            "Required Channel-এ Join করতে হবে.\n\n"
            "1️⃣ Channel-এ Join করুন\n"
            "2️⃣ তারপর <b>Check Membership</b> চাপুন.",
            parse_mode="HTML",
            reply_markup=required_channel_keyboard()
        )

    return False


# =========================================================
# ADMIN CHECK
# =========================================================

async def user_is_admin(
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

    except Exception:

        return False


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    save_user(user)

    if not await gate(
        update,
        context
    ):
        return

    await send_main_menu(
        update,
        context
    )


# =========================================================
# MAIN MENU
# =========================================================

async def send_main_menu(
    update,
    context
):

    user = update.effective_user

    text = (
        f"👋 Hello <b>{escape(user.first_name)}</b>\n\n"
        "🤖 <b>Join Request Management Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "This bot helps you:\n\n"
        "✅ Manage join requests for your "
        "channels and groups\n"
        "📢 Automatically approve requests\n"
        "⚙️ Control Auto Accept individually\n"
        "📋 Manage all connected chats\n\n"
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
                "🌐 Language",
                callback_data="language"
            ),
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
# MEMBERSHIP BUTTON
# =========================================================

async def check_membership_button(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    ok = await check_required_channel(
        context.bot,
        query.from_user.id
    )

    if not ok:

        await query.edit_message_text(
            "❌ <b>Membership not found</b>\n\n"
            "আগে Required Channel-এ Join করুন.",
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
            ]
        ])
    )


# =========================================================
# ADD CHANNEL / GROUP
# =========================================================

async def add_channel(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    username = context.bot.username

    link = (
        f"https://t.me/{username}"
        f"?startchannel"
        f"&admin=invite_users"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Add Bot to Channel",
                url=link
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Verify Channel",
                callback_data="refresh_chats"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data="back_menu"
            )
        ]
    ])

    await query.edit_message_text(
        "📢 <b>Add a New Channel</b>\n\n"
        "1️⃣ নিচের button চাপুন\n"
        "2️⃣ আপনার Channel select করুন\n"
        "3️⃣ Bot-কে Administrator করুন\n"
        "4️⃣ <b>Invite Users via Link / Manage Join Requests</b> "
        "permission দিন\n\n"
        "Bot Admin হলে channel automatically "
        "<b>My Channels</b>-এ যুক্ত হবে.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


async def add_group(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    username = context.bot.username

    link = (
        f"https://t.me/{username}"
        f"?startgroup=addbot"
        f"&admin=invite_users"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Add Bot to Group",
                url=link
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Verify Group",
                callback_data="refresh_chats"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data="back_menu"
            )
        ]
    ])

    await query.edit_message_text(
        "👥 <b>Add a New Group</b>\n\n"
        "1️⃣ নিচের button চাপুন\n"
        "2️⃣ আপনার Group select করুন\n"
        "3️⃣ Bot-কে Administrator করুন\n"
        "4️⃣ Join Request manage করার permission দিন\n\n"
        "Bot Admin হলে Group automatically "
        "<b>My Groups</b>-এ যুক্ত হবে.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# BOT ADDED / PROMOTED
# =========================================================

async def bot_membership_update(
    update,
    context
):

    member_update = update.my_chat_member

    if not member_update:
        return

    chat = member_update.chat
    new_member = member_update.new_chat_member

    # Only groups/supergroups/channels
    if chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
        ChatType.CHANNEL
    ):
        return

    if new_member.status != "administrator":
        return

    # Must be able to manage join requests
    can_invite = getattr(
        new_member,
        "can_invite_users",
        False
    )

    if not can_invite:

        try:

            await context.bot.send_message(
                chat_id=member_update.from_user.id,
                text=(
                    f"⚠️ <b>{escape(chat.title or 'Chat')}</b>\n\n"
                    "আমি Admin হয়েছি, কিন্তু "
                    "<b>Invite Users via Link / Join Requests</b> "
                    "permission নেই.\n\n"
                    "এই permission দিন তারপর আবার চেষ্টা করুন."
                ),
                parse_mode="HTML"
            )

        except Exception:
            pass

        return

    owner_id = member_update.from_user.id

    save_chat(
        chat,
        owner_id,
        auto_accept=1
    )

    logger.info(
        "Chat registered: %s (%s), owner=%s",
        chat.title,
        chat.id,
        owner_id
    )

    try:

        await context.bot.send_message(
            chat_id=owner_id,
            text=(
                "✅ <b>Bot Added Successfully!</b>\n\n"
                f"📢 Chat: <b>{escape(chat.title or '')}</b>\n"
                f"🔗 ID: <code>{chat.id}</code>\n"
                "⚙️ Auto-approve: <b>Enabled</b>\n\n"
                "The bot is now ready to manage "
                "join requests."
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⚙️ Manage",
                        callback_data=f"manage:{chat.id}"
                    )
                ]
            ])
        )

    except Exception as e:

        logger.warning(
            "Could not notify owner: %s",
            e
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
        ChatType.CHANNEL
    )

    if not rows:

        await query.edit_message_text(
            "📋 <b>My Channels</b>\n\n"
            "কোনো Channel এখনো যুক্ত করা হয়নি.",
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
                        callback_data="back_menu"
                    )
                ]
            ])
        )

        return

    buttons = []

    for row in rows:

        state = (
            "🟢"
            if row["auto_accept"]
            else "🔴"
        )

        buttons.append([
            InlineKeyboardButton(
                f"{state} {row['title'][:30]}",
                callback_data=f"manage:{row['chat_id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ Back",
            callback_data="back_menu"
        )
    ])

    await query.edit_message_text(
        "📋 <b>My Channels</b>\n\n"
        "যে Channel manage করতে চান সেটি নির্বাচন করুন:",
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
        ChatType.GROUP
    )

    supergroups = get_user_chats(
        query.from_user.id,
        ChatType.SUPERGROUP
    )

    rows = list(rows) + list(supergroups)

    if not rows:

        await query.edit_message_text(
            "👥 <b>My Groups</b>\n\n"
            "কোনো Group এখনো যুক্ত করা হয়নি.",
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
                        callback_data="back_menu"
                    )
                ]
            ])
        )

        return

    buttons = []

    for row in rows:

        state = (
            "🟢"
            if row["auto_accept"]
            else "🔴"
        )

        buttons.append([
            InlineKeyboardButton(
                f"{state} {row['title'][:30]}",
                callback_data=f"manage:{row['chat_id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ Back",
            callback_data="back_menu"
        )
    ])

    await query.edit_message_text(
        "👥 <b>My Groups</b>\n\n"
        "যে Group manage করতে চান সেটি নির্বাচন করুন:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# =========================================================
# MANAGE CHAT
# =========================================================

async def manage_chat(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    chat_id = int(
        query.data.split(":")[1]
    )

    row = get_chat(chat_id)

    if not row:

        await query.edit_message_text(
            "❌ Chat পাওয়া যায়নি."
        )

        return

    # Security
    if row["owner_id"] != query.from_user.id:

        admin = await user_is_admin(
            context.bot,
            chat_id,
            query.from_user.id
        )

        if not admin:

            await query.answer(
                "❌ You are not an admin of this chat.",
                show_alert=True
            )

            return

    state = (
        "🟢 ENABLED"
        if row["auto_accept"]
        else "🔴 DISABLED"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🟢 Enable Auto Accept",
                callback_data=f"enable:{chat_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🔴 Disable Auto Accept",
                callback_data=f"disable:{chat_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Refresh",
                callback_data=f"manage:{chat_id}"
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
                callback_data="back_menu"
            )
        ]
    ])

    await query.edit_message_text(
        "⚙️ <b>Chat Manager</b>\n\n"
        f"📢 <b>{escape(row['title'])}</b>\n\n"
        f"Auto Approve: <b>{state}</b>\n\n"
        "Join Request এলে Auto Accept "
        "ON থাকলে সঙ্গে সঙ্গে approve হবে.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# ENABLE / DISABLE
# =========================================================

async def toggle_chat(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    action, id_string = query.data.split(":")

    chat_id = int(id_string)

    row = get_chat(chat_id)

    if not row:
        return

    if row["owner_id"] != query.from_user.id:

        if not await user_is_admin(
            context.bot,
            chat_id,
            query.from_user.id
        ):

            await query.answer(
                "❌ Admin only.",
                show_alert=True
            )

            return

    if action == "enable":

        set_auto_accept(
            chat_id,
            True
        )

    else:

        set_auto_accept(
            chat_id,
            False
        )

    # Re-render
    query.data = f"manage:{chat_id}"

    await manage_chat(
        update,
        context
    )


# =========================================================
# REMOVE
# =========================================================

async def remove_chat_callback(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    chat_id = int(
        query.data.split(":")[1]
    )

    row = get_chat(chat_id)

    if not row:
        return

    if row["owner_id"] != query.from_user.id:

        if not await user_is_admin(
            context.bot,
            chat_id,
            query.from_user.id
        ):

            await query.answer(
                "❌ Admin only.",
                show_alert=True
            )

            return

    remove_chat(chat_id)

    await query.edit_message_text(
        "✅ <b>Chat Removed</b>\n\n"
        "এই Chat আর Bot-এর managed list-এ নেই.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ Main Menu",
                    callback_data="back_menu"
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

    # If bot was added manually and database isn't ready
    if not row:

        logger.warning(
            "Join request from unregistered chat: %s",
            chat.id
        )

        return

    # -----------------------------------------------------
    # FIRST MESSAGE: REVIEW
    # -----------------------------------------------------

    try:

        await context.bot.send_message(
            chat_id=request.user_chat_id,
            text=(
                "⏳ <b>Your Join Request Has Been Received</b>\n\n"
                f"📢 Chat: <b>{escape(chat.title or '')}</b>\n\n"
                "🔎 Your request is being reviewed.\n"
                "Please wait..."
            ),
            parse_mode="HTML"
        )

    except Exception as e:

        logger.warning(
            "Could not send review message: %s",
            e
        )

    # -----------------------------------------------------
    # AUTO APPROVE
    # -----------------------------------------------------

    if not row["auto_accept"]:

        logger.info(
            "Auto approve OFF: %s",
            chat.id
        )

        return

    try:

        await request.approve()

        logger.info(
            "Approved request: user=%s chat=%s",
            user.id,
            chat.id
        )

    except Exception as e:

        logger.error(
            "Approve failed: %s",
            e
        )

        try:

            await context.bot.send_message(
                chat_id=request.user_chat_id,
                text=(
                    "⚠️ <b>Your request could not be "
                    "processed automatically.</b>\n\n"
                    "Please wait for an administrator."
                ),
                parse_mode="HTML"
            )

        except Exception:
            pass

        return

    # -----------------------------------------------------
    # APPROVED MESSAGE
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

    except Exception as e:

        logger.warning(
            "Could not send approval message: %s",
            e
        )


# =========================================================
# HELP
# =========================================================

async def help_command(
    update,
    context
):

    if not await gate(
        update,
        context
    ):
        return

    await update.effective_message.reply_text(
        "ℹ️ <b>How to use</b>\n\n"
        "1️⃣ Join the Required Channel\n"
        "2️⃣ Open the Bot again\n"
        "3️⃣ Add the Bot to your Group/Channel\n"
        "4️⃣ Make it Administrator\n"
        "5️⃣ Give Join Request permission\n"
        "6️⃣ Manage Auto Accept from My Groups/My Channels.",
        parse_mode="HTML"
    )


# =========================================================
# BACK
# =========================================================

async def back_menu(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    if not await check_required_channel(
        context.bot,
        query.from_user.id
    ) and query.from_user.id != OWNER_ID:

        await query.edit_message_text(
            "🔒 Required Channel-এ Join করুন.",
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

    # Required channel verification
    if data == "check_membership":
        await check_membership_button(
            update,
            context
        )
        return

    # Every other button requires membership
    if not await check_required_channel(
        context.bot,
        query.from_user.id
    ) and query.from_user.id != OWNER_ID:

        await query.answer(
            "🔒 Join the Required Channel first.",
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

    elif data == "back_menu":

        await back_menu(
            update,
            context
        )

    elif data == "help":

        await help_command(
            update,
            context
        )

    elif data == "refresh_chats":

        await query.answer(
            "🔄 Chat list updated.",
            show_alert=True
        )

    elif data.startswith("manage:"):

        await manage_chat(
            update,
            context
        )

    elif data.startswith("enable:"):

        await toggle_chat(
            update,
            context
        )

    elif data.startswith("disable:"):

        await toggle_chat(
            update,
            context
        )

    elif data.startswith("remove:"):

        await remove_chat_callback(
            update,
            context
        )


# =========================================================
# OWNER: REQUIRED CHANNEL STATUS
# =========================================================

async def required_command(
    update,
    context
):

    user = update.effective_user

    if user.id != OWNER_ID:

        await update.effective_message.reply_text(
            "❌ Owner only."
        )

        return

    await update.effective_message.reply_text(
        "🔐 <b>Required Channel</b>\n\n"
        f"Channel: <code>{escape(REQUIRED_CHANNEL)}</code>\n"
        f"Link: {escape(REQUIRED_CHANNEL_LINK)}\n\n"
        "এই Channel-এ Join না করলে Main Menu দেখা যাবে না.",
        parse_mode="HTML"
    )


# =========================================================
# ERROR
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

    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Private commands
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    app.add_handler(
        CommandHandler(
            "required",
            required_command
        )
    )

    # Detect bot added/promoted
    app.add_handler(
        ChatMemberHandler(
            bot_membership_update,
            ChatMemberHandler.MY_CHAT_MEMBER
        )
    )

    # Join Requests
    app.add_handler(
        ChatJoinRequestHandler(
            handle_join_request
        )
    )

    # Buttons
    app.add_handler(
        CallbackQueryHandler(
            callback_router
        )
    )

    app.add_error_handler(
        error_handler
    )

    logger.info(
        "======================================"
    )

    logger.info(
        "AUTO APPROVE BOT STARTED"
    )

    logger.info(
        "Required Channel: %s",
        REQUIRED_CHANNEL
    )

    logger.info(
        "======================================"
    )

    app.run_polling(
        allowed_updates=[
            "message",
            "callback_query",
            "my_chat_member",
            "chat_join_request"
        ]
    )


if __name__ == "__main__":
    main()
