import os
import sqlite3
import logging
from functools import wraps

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
    ContextTypes,
)

# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

REQUIRED_CHANNEL = os.getenv(
    "REQUIRED_CHANNEL",
    "@YourChannel"
)

REQUIRED_CHANNEL_LINK = os.getenv(
    "REQUIRED_CHANNEL_LINK",
    "https://t.me/YourChannel"
)

DB_FILE = "bot.db"

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. Add BOT_TOKEN in Railway Variables."
    )


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# =========================================================
# DATABASE
# =========================================================

def db():
    connection = sqlite3.connect(
        DB_FILE,
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
            title TEXT,
            chat_type TEXT,
            auto_accept INTEGER DEFAULT 1
        )
    """)

    connection.commit()
    connection.close()


def register_chat(chat):

    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO chats
        (chat_id, title, chat_type, auto_accept)
        VALUES (?, ?, ?, 1)
    """, (
        chat.id,
        chat.title or "",
        chat.type
    ))

    cursor.execute("""
        UPDATE chats
        SET title = ?, chat_type = ?
        WHERE chat_id = ?
    """, (
        chat.title or "",
        chat.type,
        chat.id
    ))

    connection.commit()
    connection.close()


def get_chat_settings(chat_id):

    connection = db()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM chats WHERE chat_id = ?",
        (chat_id,)
    )

    result = cursor.fetchone()

    connection.close()

    return result


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


# =========================================================
# REQUIRED CHANNEL CHECK
# =========================================================

async def is_subscribed(bot, user_id):

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
            "Subscription check failed: %s",
            error
        )

        return False


async def subscription_keyboard():

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
                callback_data="check_subscription"
            )
        ]
    ])


# =========================================================
# USER ACCESS
# =========================================================

async def require_subscription(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user:
        return False

    subscribed = await is_subscribed(
        context.bot,
        user.id
    )

    if subscribed:
        return True

    keyboard = await subscription_keyboard()

    message = update.effective_message

    if message:

        await message.reply_text(
            "🔒 Bot ব্যবহার করার আগে আমাদের "
            "Required Channel-এ Join করতে হবে.\n\n"
            "1️⃣ Channel-এ Join করুন\n"
            "2️⃣ তারপর নিচের Check Membership চাপুন.",
            reply_markup=keyboard
        )

    return False


# =========================================================
# ADMIN CHECK
# =========================================================

async def is_chat_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return False

    if chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
        ChatType.CHANNEL
    ):
        return False

    try:

        member = await context.bot.get_chat_member(
            chat.id,
            user.id
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

    user = update.effective_user

    text = (
        "🤖 <b>Auto Approve Bot</b>\n\n"
        "এই বট Group, Supergroup এবং Channel-এর "
        "Join Request automatically approve করতে পারে.\n\n"
        "Bot ব্যবহার করতে প্রথমে Required Channel-এ Join করুন."
    )

    keyboard = await subscription_keyboard()

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# CHECK SUBSCRIPTION
# =========================================================

async def check_subscription(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    subscribed = await is_subscribed(
        context.bot,
        user_id
    )

    if subscribed:

        await query.edit_message_text(
            "✅ <b>Membership Verified!</b>\n\n"
            "আপনি এখন বট ব্যবহার করতে পারবেন.",
            parse_mode="HTML"
        )

    else:

        keyboard = await subscription_keyboard()

        await query.edit_message_text(
            "❌ আপনি এখনো Required Channel-এ Join করেননি.\n\n"
            "আগে Channel-এ Join করুন.",
            reply_markup=keyboard
        )


# =========================================================
# REGISTER CHAT
# =========================================================

async def setup_chat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await require_subscription(
        update,
        context
    ):
        return

    chat = update.effective_chat

    if chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
        ChatType.CHANNEL
    ):

        await update.effective_message.reply_text(
            "❌ এই command শুধু Group/Channel-এ ব্যবহার করুন."
        )

        return

    if not await is_chat_admin(
        update,
        context
    ):

        await update.effective_message.reply_text(
            "❌ এই command ব্যবহার করতে আপনাকে "
            "Group/Channel-এর Admin হতে হবে."
        )

        return

    register_chat(chat)

    await update.effective_message.reply_text(
        "✅ এই Chat সফলভাবে registered হয়েছে.\n\n"
        "Auto Accept বর্তমানে ON.\n\n"
        "Settings দেখতে /panel ব্যবহার করুন."
    )


# =========================================================
# PANEL
# =========================================================

async def panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await require_subscription(
        update,
        context
    ):
        return

    chat = update.effective_chat

    if chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
        ChatType.CHANNEL
    ):

        await update.effective_message.reply_text(
            "❌ /panel Group অথবা Channel-এ ব্যবহার করুন."
        )

        return

    if not await is_chat_admin(
        update,
        context
    ):

        await update.effective_message.reply_text(
            "❌ শুধু Admin এই Panel ব্যবহার করতে পারবেন."
        )

        return

    register_chat(chat)

    settings = get_chat_settings(chat.id)

    enabled = bool(settings["auto_accept"])

    state = "🟢 ON" if enabled else "🔴 OFF"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🟢 Auto Accept ON",
                callback_data="auto_on"
            ),
            InlineKeyboardButton(
                "🔴 Auto Accept OFF",
                callback_data="auto_off"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data="refresh_panel"
            )
        ]
    ])

    await update.effective_message.reply_text(
        f"⚙️ <b>Auto Approve Settings</b>\n\n"
        f"Chat: <b>{chat.title}</b>\n"
        f"Auto Accept: <b>{state}</b>\n\n"
        f"Join Request এলে Auto Accept "
        f"{'করা হবে' if enabled else 'করা হবে না'}.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# PANEL BUTTONS
# =========================================================

async def panel_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    chat = update.effective_chat
    user = query.from_user

    if not chat:
        return

    # Admin verification
    try:

        member = await context.bot.get_chat_member(
            chat.id,
            user.id
        )

        if member.status not in (
            "administrator",
            "creator"
        ):

            await query.answer(
                "❌ শুধু Admin ব্যবহার করতে পারবেন.",
                show_alert=True
            )

            return

    except Exception:

        await query.answer(
            "❌ Admin verification failed.",
            show_alert=True
        )

        return

    action = query.data

    register_chat(chat)

    if action == "auto_on":

        set_auto_accept(
            chat.id,
            True
        )

    elif action == "auto_off":

        set_auto_accept(
            chat.id,
            False
        )

    elif action == "refresh_panel":

        pass

    settings = get_chat_settings(chat.id)

    enabled = bool(settings["auto_accept"])

    state = "🟢 ON" if enabled else "🔴 OFF"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🟢 Auto Accept ON",
                callback_data="auto_on"
            ),
            InlineKeyboardButton(
                "🔴 Auto Accept OFF",
                callback_data="auto_off"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data="refresh_panel"
            )
        ]
    ])

    await query.edit_message_text(
        f"⚙️ <b>Auto Approve Settings</b>\n\n"
        f"Chat: <b>{chat.title}</b>\n"
        f"Auto Accept: <b>{state}</b>\n\n"
        f"Join Request এলে Auto Accept "
        f"{'করা হবে' if enabled else 'করা হবে না'}.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# STATUS
# =========================================================

async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await require_subscription(
        update,
        context
    ):
        return

    chat = update.effective_chat

    if not await is_chat_admin(
        update,
        context
    ):

        await update.effective_message.reply_text(
            "❌ Admin only."
        )

        return

    register_chat(chat)

    settings = get_chat_settings(chat.id)

    state = "ON 🟢" if settings["auto_accept"] else "OFF 🔴"

    await update.effective_message.reply_text(
        f"📊 <b>Status</b>\n\n"
        f"Chat: <b>{chat.title}</b>\n"
        f"Auto Accept: <b>{state}</b>\n"
        f"Required Channel: <b>{REQUIRED_CHANNEL}</b>",
        parse_mode="HTML"
    )


# =========================================================
# JOIN REQUEST HANDLER
# =========================================================

async def handle_join_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    request = update.chat_join_request

    if not request:
        return

    chat = request.chat
    user = request.from_user

    logger.info(
        "Join request received: user=%s chat=%s",
        user.id,
        chat.id
    )

    # Register chat automatically
    register_chat(chat)

    settings = get_chat_settings(chat.id)

    if not settings:
        return

    # Auto accept OFF
    if not bool(settings["auto_accept"]):

        logger.info(
            "Auto Accept OFF for %s",
            chat.id
        )

        return

    # =====================================================
    # APPROVE REQUEST
    # =====================================================

    try:

        await request.approve()

        logger.info(
            "Approved join request: %s -> %s",
            user.id,
            chat.id
        )

    except Exception as error:

        logger.error(
            "Could not approve request: %s",
            error
        )

        return

    # =====================================================
    # USER NOTIFICATION
    # =====================================================

    # Important:
    # Telegram bots cannot start a private conversation
    # with a user who has never opened /start.
    #
    # If the user has already started this bot,
    # this message will work.

    try:

        bot_username = context.bot.username

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔎 Review Your Request",
                    url=f"https://t.me/{bot_username}"
                )
            ]
        ])

        await context.bot.send_message(
            chat_id=user.id,
            text=(
                f"✅ <b>Your join request was approved!</b>\n\n"
                f"Chat: <b>{chat.title}</b>\n\n"
                f"Review your request below."
            ),
            parse_mode="HTML",
            reply_markup=keyboard
        )

    except Exception as error:

        logger.info(
            "Could not send DM to user %s: %s",
            user.id,
            error
        )


# =========================================================
# HELP
# =========================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await require_subscription(
        update,
        context
    ):
        return

    await update.effective_message.reply_text(
        "🤖 <b>Auto Approve Bot</b>\n\n"

        "/start - Start the bot\n"
        "/setup - Register this chat\n"
        "/panel - Open settings\n"
        "/status - Show status\n"
        "/help - Show help\n\n"

        "<b>Admin Commands</b>\n"
        "/setup\n"
        "/panel\n"
        "/status",
        parse_mode="HTML"
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Exception while handling update:",
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

    # Commands
    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "setup",
            setup_chat
        )
    )

    application.add_handler(
        CommandHandler(
            "panel",
            panel
        )
    )

    application.add_handler(
        CommandHandler(
            "status",
            status
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    # Required channel button
    application.add_handler(
        CallbackQueryHandler(
            check_subscription,
            pattern="^check_subscription$"
        )
    )

    # Panel buttons
    application.add_handler(
        CallbackQueryHandler(
            panel_callback,
            pattern="^(auto_on|auto_off|refresh_panel)$"
        )
    )

    # Join Requests
    application.add_handler(
        ChatJoinRequestHandler(
            handle_join_request
        )
    )

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "===================================="
    )

    logger.info(
        "AUTO APPROVE BOT STARTED"
    )

    logger.info(
        "Required Channel: %s",
        REQUIRED_CHANNEL
    )

    logger.info(
        "===================================="
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
