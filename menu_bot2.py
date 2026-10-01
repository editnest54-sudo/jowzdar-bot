from pathlib import Path
import sqlite3
import os
import shutil
import re
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup as _AiogramInlineKeyboardMarkup,
    InlineKeyboardButton as _AiogramInlineKeyboardButton,
    BotCommand as _AiogramBotCommand,
    BotCommandScopeDefault,
    BotCommandScopeChat,
    FSInputFile,
    InputMediaPhoto,
    InputMediaVideo,
)


# =========================================================
# لایه‌ی سازگاری با سینتکس قدیمی (aiogram 2 -> aiogram 3)
# =========================================================
# aiogram 3 دیگه از .add() روی InlineKeyboardMarkup و آرگومان
# موقعیتی روی InlineKeyboardButton/BotCommand پشتیبانی نمی‌کنه.
# این سه کلاس همون رفتار قدیمی رو روی مدل‌های واقعی aiogram 3
# شبیه‌سازی می‌کنن تا نیازی به دست‌کاری صدها فراخوانی نباشه.

_ROW_STYLES = ("danger", "danger", "success", "success", "primary")  # ردیف ۱-۲ قرمز، ۳-۴ سبز، ۵+ آبی


def _apply_row_styles(inline_keyboard):
    """رنگ ردیف‌ها: ۱ و ۲ قرمز، ۳ و ۴ سبز، ۵ به بعد آبی."""
    for idx, row in enumerate(inline_keyboard):
        style = _ROW_STYLES[idx] if idx < len(_ROW_STYLES) else "primary"
        for btn in row:
            try:
                btn.style = style
            except Exception:
                pass


class InlineKeyboardButton(_AiogramInlineKeyboardButton):

    def __init__(self, text=None, *args, **kwargs):

        if text is not None:
            kwargs["text"] = text

        super().__init__(**kwargs)


class InlineKeyboardMarkup(_AiogramInlineKeyboardMarkup):

    def __init__(self, row_width: int = 3, **kwargs):

        kwargs.setdefault("inline_keyboard", [])

        super().__init__(**kwargs)

        object.__setattr__(self, "_row_width", row_width)

    def add(self, *buttons):

        if not buttons:
            return self

        rows = [list(r) for r in self.inline_keyboard]

        if rows and len(rows[-1]) < self._row_width:
            current_row = rows[-1]
        else:
            current_row = []
            rows.append(current_row)

        for b in buttons:

            if len(current_row) >= self._row_width:
                current_row = []
                rows.append(current_row)

            current_row.append(b)

        self.inline_keyboard = rows

        _apply_row_styles(self.inline_keyboard)

        return self

    def row(self, *buttons):

        rows = [list(r) for r in self.inline_keyboard]
        rows.append(list(buttons))
        self.inline_keyboard = rows

        _apply_row_styles(self.inline_keyboard)

        return self


def BotCommand(command=None, description=None, **kwargs):

    if command is not None:
        kwargs["command"] = command

    if description is not None:
        kwargs["description"] = description

    return _AiogramBotCommand(**kwargs)


# =========================================================
# تنظیمات ربات
# =========================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

OWNER = 5690205344

# گروه لاگ ورود کاربران
START_LOG_GROUP_ID = -1003910785089

# گروه لاگ فعالیت کاربران
ACTIVITY_LOG_GROUP_ID = -1004383374418

# گروه لاگ فعالیت ادمین
ADMIN_LOG_GROUP_ID = -1004499440877

# گروه جداگانه برای پیام‌های ارسالی کاربران
# شناسه گروه را اینجا قرار بده
USER_MESSAGE_GROUP_ID = -1004413006254

VILLAGE_NAME = "روستای جوزدر"


# =========================================================
# مکان های دیدنی
# =========================================================

SCENIC_PLACES = [
    ("rastebragh", "راست‌براگ"),
    ("godan", "گودان"),
    ("tijgi", "تیجگی"),
    ("گلگ", "گلگ"),
    ("سروست", "سروست"),
    ("سینگمیر", "سینگمیر"),
    ("بزوت", "بزوت"),
    ("تراتی", "تراتی"),
    ("سیران کوه", "سیران کوه"),
    ("توتک", "توتک"),
    ("کوه سَل", "کوه سَل"),
]

SCENIC_LABEL = dict(SCENIC_PLACES)


# =========================================================
# امکانات روستا
# =========================================================

FACILITIES = [
    ("chaman", "🌱 چمن"),
    ("park", "🌳 پارک"),
    ("school", "🏫 مدرسه"),
    ("mosque", "🕌 مسجد"),
    ("maktab", "📚 مکتب"),
    ("health", "🏥 خانه بهداشت"),
]

FACILITY_LABEL = dict(FACILITIES)


# =========================================================
# فروشگاه‌ها
# =========================================================

SHOPS = [
    ("sattar", "سوپرمارکت ستار"),
    ("jasem", "سوپرمارکت جاسم"),
    ("mohammad", "سوپرمارکت محمد"),
    ("khaled", "سوپرمارکت خالد"),
    ("gandom", "نانوایی گندم"),
    ("mehran", "آرایشگاه مهران"),
]

SHOP_LABEL = dict(SHOPS)


# =========================================================
# انواع فایل
# =========================================================

KIND_LABEL = {
    "video": "🎥 فیلم‌ها",
    "photo": "🖼 عکس‌ها",
}


# =========================================================
# BOT
# =========================================================

bot = Bot(token=TOKEN)
dp = Dispatcher()


# =========================================================
# DATABASE
# =========================================================

db = sqlite3.connect(
    "village.db",
    check_same_thread=False
)


# =========================================================
# DATABASE HELPERS
# =========================================================

def column_exists(table_name, column_name):

    rows = db.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        row[1] == column_name
        for row in rows
    )


def ensure_column(
    table_name,
    column_name,
    column_type
):

    if not column_exists(
        table_name,
        column_name
    ):

        db.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name} {column_type}
            """
        )

        db.commit()


# =========================================================
# جدول فایل ها
# =========================================================

db.execute("""
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place TEXT,
    kind TEXT,
    file_id TEXT
)
""")

ensure_column(
    "items",
    "place",
    "TEXT"
)

ensure_column(
    "items",
    "kind",
    "TEXT"
)

ensure_column(
    "items",
    "file_id",
    "TEXT"
)

ensure_column(
    "items",
    "likes",
    "INTEGER DEFAULT 0"
)


# =========================================================
# جدول مکان ها
# =========================================================

db.execute("""
CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_type TEXT,
    name TEXT,
    description TEXT,
    file_id TEXT,
    lat REAL,
    lon REAL
)
""")

ensure_column(
    "places",
    "place_type",
    "TEXT"
)

ensure_column(
    "places",
    "name",
    "TEXT"
)

ensure_column(
    "places",
    "description",
    "TEXT"
)

ensure_column(
    "places",
    "file_id",
    "TEXT"
)

ensure_column(
    "places",
    "lat",
    "REAL"
)

ensure_column(
    "places",
    "lon",
    "REAL"
)


# =========================================================
# SETTINGS
# =========================================================

db.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")


# =========================================================
# USERS
# =========================================================

db.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    chat_id INTEGER,
    username TEXT,
    full_name TEXT,
    first_seen TEXT,
    last_seen TEXT,
    start_count INTEGER DEFAULT 0
)
""")


# =========================================================
# ACTIVITY STATS
# =========================================================

db.execute("""
CREATE TABLE IF NOT EXISTS activity_stats (
    section TEXT PRIMARY KEY,
    views INTEGER DEFAULT 0
)
""")


# =========================================================
# ACTIVITY LOG
# =========================================================

db.execute("""
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    section TEXT,
    activity_type TEXT,
    details TEXT,
    created_at TEXT
)
""")


db.commit()


db.execute("""
CREATE TABLE IF NOT EXISTS item_likes (
    item_id INTEGER,
    user_id INTEGER,
    created_at TEXT,
    PRIMARY KEY (item_id, user_id)
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS message_items (
    chat_id INTEGER,
    message_id INTEGER,
    item_id INTEGER,
    PRIMARY KEY (chat_id, message_id)
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    message TEXT,
    created_at TEXT
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS user_notifications (
    user_id INTEGER PRIMARY KEY,
    enabled INTEGER DEFAULT 1
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    message TEXT,
    created_at TEXT,
    status TEXT DEFAULT 'new'
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS user_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    message_type TEXT,
    created_at TEXT
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    event_date TEXT,
    description TEXT,
    created_at TEXT
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY,
    role TEXT DEFAULT 'admin',
    created_at TEXT
)
""")

ensure_column("items", "title", "TEXT")
ensure_column("items", "description", "TEXT")
ensure_column("items", "views", "INTEGER DEFAULT 0")
db.commit()

 # =========================================================
# STATE
# =========================================================

admin_state = {}


# =========================================================
# SETTINGS
# =========================================================

def get_setting(
    key,
    default=""
):

    row = db.execute(
        """
        SELECT value
        FROM settings
        WHERE key = ?
        """,
        (key,)
    ).fetchone()

    return row[0] if row else default


def set_setting(
    key,
    value
):

    db.execute(
        """
        INSERT INTO settings
        (key, value)
        VALUES (?, ?)

        ON CONFLICT(key)
        DO UPDATE SET
        value = excluded.value
        """,
        (
            key,
            value
        )
    )

    db.commit()


# =========================================================
# TIME
# =========================================================

def now_text():

    return datetime.now().strftime(
        "%Y/%m/%d - %H:%M:%S"
    )


# =========================================================
# USER INFO
# =========================================================

def get_user_name(user):

    return (
        user.full_name
        or "بدون نام"
    )


def get_username(user):

    return (
        f"@{user.username}"
        if user.username
        else "ندارد"
    )


# =========================================================
# REGISTER USER
# =========================================================

def register_user(user, chat_id):

    now = now_text()

    row = db.execute(
        """
        SELECT user_id
        FROM users
        WHERE user_id = ?
        """,
        (user.id,)
    ).fetchone()

    if row:

        db.execute(
            """
            UPDATE users
            SET
                chat_id = ?,
                username = ?,
                full_name = ?,
                last_seen = ?,
                start_count = start_count + 1
            WHERE user_id = ?
            """,
            (
                chat_id,
                user.username or "",
                user.full_name or "",
                now,
                user.id
            )
        )

    else:

        db.execute(
            """
            INSERT INTO users
            (
                user_id,
                chat_id,
                username,
                full_name,
                first_seen,
                last_seen,
                start_count
            )
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                user.id,
                chat_id,
                user.username or "",
                user.full_name or "",
                now,
                now
            )
        )

    db.commit()


# =========================================================
# UNIQUE USERS COUNT
# =========================================================

def total_users():

    row = db.execute(
        """
        SELECT COUNT(*)
        FROM users
        """
    ).fetchone()

    return row[0]


# =========================================================
# SECTION VIEW COUNT
# =========================================================

def increase_section_view(section):

    db.execute(
        """
        INSERT INTO activity_stats
        (section, views)
        VALUES (?, 1)

        ON CONFLICT(section)
        DO UPDATE SET
        views = views + 1
        """,
        (section,)
    )

    db.commit()

    row = db.execute(
        """
        SELECT views
        FROM activity_stats
        WHERE section = ?
        """,
        (section,)
    ).fetchone()

    return row[0] if row else 1


# =========================================================
# SEND ACTIVITY LOG
# =========================================================

async def log_user_activity(
    user,
    section,
    activity_type,
    details=""
):

    if not ACTIVITY_LOG_GROUP_ID:
        return

    views = increase_section_view(
        section
    )

    users_count = total_users()

    text = (
        "📊 فعالیت کاربر\n\n"
        f"🕐 تاریخ و ساعت: {now_text()}\n\n"
        f"👤 نام: {get_user_name(user)}\n"
        f"🔹 Username: {get_username(user)}\n"
        f"🆔 شناسه کاربر: {user.id}\n\n"
        f"📱 نوع فعالیت: {activity_type}\n"
        f"📸 بخش: {section}\n"
    )

    if details:

        text += (
            f"📍 جزئیات: {details}\n"
        )

    text += (
        "\n"
        f"👥 تعداد کاربران: {users_count}\n"
        f"👁 بازدید این بخش: {views}"
    )

    try:

        await bot.send_message(
            ACTIVITY_LOG_GROUP_ID,
            text
        )

    except Exception as e:

        print(
            "ACTIVITY LOG ERROR:",
            repr(e)
        )

    try:

        db.execute(
            """
            INSERT INTO activity_logs
            (
                user_id,
                section,
                activity_type,
                details,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user.id,
                section,
                activity_type,
                details,
                now_text()
            )
        )

        db.commit()

    except Exception as e:

        print(
            "ACTIVITY DATABASE ERROR:",
            repr(e)
        )


# =========================================================
# ADMIN LOG
# =========================================================

async def log_admin_activity(
    user,
    action,
    section="",
    details="",
    result="موفق"
):

    if not ADMIN_LOG_GROUP_ID:
        return

    text = (
        "⚙️ فعالیت ادمین\n\n"
        f"🕐 تاریخ و ساعت: {now_text()}\n\n"
        f"👤 ادمین: {get_user_name(user)}\n"
        f"🔹 Username: {get_username(user)}\n"
        f"🆔 شناسه: {user.id}\n\n"
        f"🔧 عملیات: {action}\n"
    )

    if section:

        text += (
            f"📍 بخش: {section}\n"
        )

    if details:

        text += (
            f"📁 جزئیات: {details}\n"
        )

    text += (
        f"✅ نتیجه: {result}"
    )

    try:

        await bot.send_message(
            ADMIN_LOG_GROUP_ID,
            text
        )

    except Exception as e:

        print(
            "ADMIN LOG ERROR:",
            repr(e)
        )


# =========================================================
# ADMIN CHECK
# =========================================================

def is_admin(user_id):

    if user_id == OWNER:
        return True
    row = db.execute(
        "SELECT user_id FROM admins WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    return bool(row)


def admin_role(user_id):

    if user_id == OWNER:
        return "owner"
    row = db.execute(
        "SELECT role FROM admins WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    return row[0] if row else ""


# =========================================================
# پسندیدن محتوا (👍)
# =========================================================

def add_like_button(kb, item_id):
    """یه دکمه‌ی پسندیدم به کیبورد اضافه می‌کنه (به عنوان یه سطر جدا)."""

    kb.add(
        InlineKeyboardButton(
            "👍 پسندیدم",
            callback_data=f"like_{item_id}",
            style="success"
        )
    )

    return kb


@dp.callback_query(F.data.startswith("like_"))
async def like_item(
    call: types.CallbackQuery
):

    try:
        item_id = int(call.data.replace("like_", ""))
    except ValueError:
        return await call.answer("❌ محتوای نامعتبر.", show_alert=True)

    row = db.execute(
        "SELECT place, kind FROM items WHERE id = ?",
        (item_id,)
    ).fetchone()

    if not row:
        return await call.answer("❌ محتوا پیدا نشد.", show_alert=True)

    try:
        db.execute(
            "INSERT INTO item_likes (item_id, user_id, created_at) VALUES (?, ?, ?)",
            (item_id, call.from_user.id, now_text())
        )
        db.execute(
            "UPDATE items SET likes = COALESCE(likes, 0) + 1 WHERE id = ?",
            (item_id,)
        )
        db.commit()
        message = "👍 لایک ثبت شد."
    except sqlite3.IntegrityError:
        message = "ℹ️ قبلاً این محتوا را لایک کرده‌ای."

    likes = db.execute(
        "SELECT COALESCE(likes, 0) FROM items WHERE id = ?",
        (item_id,)
    ).fetchone()[0]

    await call.answer(f"{message} ({likes} پسند)")


def remember_item_message(chat_id, message_id, item_id):
    """یادش می‌مونه این پیام (عکس/فیلم) مال کدوم آیتمه، تا اگه کاربر
    باهاش ری‌اکشن واقعی تلگرام بزنه، بشه لایکش رو تو دیتابیس ثبت کرد."""
    try:
        db.execute(
            "INSERT OR REPLACE INTO message_items (chat_id, message_id, item_id) VALUES (?, ?, ?)",
            (chat_id, message_id, item_id)
        )
        db.commit()
    except Exception as e:
        print("REMEMBER ITEM MESSAGE ERROR:", repr(e))


async def send_or_edit_media(chat_id, kind, file_id, caption, kb, edit_message=None):
    """اگه edit_message داده شده باشه (یعنی داریم رو یه گالری موجود بعدی/قبلی
    می‌زنیم)، همون پیام رو ویرایش می‌کنه (عکس/فیلم عوض می‌شه، پیام جدید نمیاد).
    وگرنه (اولین بار ورود به گالری) یه پیام جدید می‌فرسته."""

    media_cls = InputMediaPhoto if kind == "photo" else InputMediaVideo

    if edit_message is not None:
        try:
            result = await bot.edit_message_media(
                chat_id=chat_id,
                message_id=edit_message.message_id,
                media=media_cls(media=file_id, caption=caption),
                reply_markup=kb
            )
            if isinstance(result, types.Message):
                return result
            return edit_message
        except Exception as e:
            print("EDIT MEDIA ERROR (falling back to new message):", repr(e))

    if kind == "photo":
        return await bot.send_photo(chat_id, file_id, caption=caption, reply_markup=kb)
    return await bot.send_video(chat_id, file_id, caption=caption, reply_markup=kb)


@dp.message_reaction()
async def on_message_reaction(event: types.MessageReactionUpdated):
    """وقتی کاربر با ری‌اکشن واقعی تلگرام (❤️👍😂 و غیره) به یه عکس/فیلمِ
    ربات واکنش نشون بده، همون به‌عنوان لایک ثبت می‌شه (اگه اضافه کرده) یا
    لایک برداشته می‌شه (اگه ری‌اکشنش رو پاک کرده)."""

    row = db.execute(
        "SELECT item_id FROM message_items WHERE chat_id = ? AND message_id = ?",
        (event.chat.id, event.message_id)
    ).fetchone()

    if not row:
        return

    item_id = row[0]
    user_id = event.user.id if event.user else None

    if user_id is None:
        return

    had_reaction = len(event.old_reaction) > 0
    has_reaction = len(event.new_reaction) > 0

    try:
        if has_reaction and not had_reaction:
            db.execute(
                "INSERT INTO item_likes (item_id, user_id, created_at) VALUES (?, ?, ?)",
                (item_id, user_id, now_text())
            )
            db.execute(
                "UPDATE items SET likes = COALESCE(likes, 0) + 1 WHERE id = ?",
                (item_id,)
            )
            db.commit()

        elif had_reaction and not has_reaction:
            cur = db.execute(
                "DELETE FROM item_likes WHERE item_id = ? AND user_id = ?",
                (item_id, user_id)
            )
            if cur.rowcount:
                db.execute(
                    "UPDATE items SET likes = MAX(COALESCE(likes, 0) - 1, 0) WHERE id = ?",
                    (item_id,)
                )
            db.commit()

    except sqlite3.IntegrityError:
        pass
    except Exception as e:
        print("MESSAGE REACTION ERROR:", repr(e))

# =========================================================
# SAFE EDIT

# =========================================================

async def safe_edit_or_send(
    call,
    text,
    kb=None
):

    if (
        call.message
        and call.message.content_type == "text"
    ):

        try:

            await call.message.edit_text(
                text,
                reply_markup=kb
            )

            return

        except Exception:
            pass

    await bot.send_message(
        call.message.chat.id,
        text,
        reply_markup=kb
    )


# =========================================================
# MAIN MENU
# =========================================================

def scenic_menu_keyboard(back_callback="back_main"):
    kb = InlineKeyboardMarkup()
    row = []
    for key, label in SCENIC_PLACES:
        row.append(InlineKeyboardButton(label, callback_data=f"scenic_{key}"))
        if len(row) == 2:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    kb.row(InlineKeyboardButton("🔙 بازگشت", callback_data=back_callback))
    return kb

def admin_success_keyboard(back_callback="admin_panel"):
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🔙 بازگشت", callback_data=back_callback))
    return kb


def main_menu(user_id=None):

    kb = InlineKeyboardMarkup(row_width=2)

    kb.add(
        InlineKeyboardButton(
            "🏘 معرفی روستا",
            callback_data="main_intro",
            style="primary"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "🏞 مکان‌های دیدنی",
            callback_data="main_scenic",
            style="primary"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "🏘 محلات روستا",
            callback_data="main_neighborhoods",
            style="primary"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "🏫 امکانات روستا",
            callback_data="main_facilities",
            style="primary"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "🔎 جستجوی محتوا",
            callback_data="user_search",
            style="primary"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "📅 رویدادهای روستا",
            callback_data="user_events",
            style="primary"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "📬 پیشنهاد و پیام",
            callback_data="user_feedback",
            style="primary"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "ℹ️ راهنمای ربات",
            callback_data="user_help",
            style="primary"
        )
    )

    if user_id == OWNER:

        kb.add(
            InlineKeyboardButton(
                "⚙️ مدیریت ربات",
                callback_data="admin_panel"
            )
        )

    kb.add(InlineKeyboardButton(
        "📸 پیج رسمی روستای جوزدر",
        url="https://www.instagram.com/jowzdar/",
        style="success"
    ))

    return kb


# =========================================================
# START
# =========================================================

@dp.message(Command("start"))
async def start(
    msg: types.Message
):

    user = msg.from_user

    register_user(
        user,
        msg.chat.id
    )

    username = get_username(user)
    full_name = get_user_name(user)

    # =====================================================
    # START LOG
    # =====================================================

    log_text = (
        "🟢 ورود کاربر\n\n"
        f"🕐 تاریخ و ساعت: {now_text()}\n\n"
        f"👤 نام: {full_name}\n"
        f"🔹 Username: {username}\n"
        f"🆔 شناسه کاربر: {user.id}\n"
        f"💬 Chat ID: {msg.chat.id}\n\n"
        f"👥 تعداد کاربران: {total_users()}"
    )

    if START_LOG_GROUP_ID:

        try:

            await bot.send_message(
                START_LOG_GROUP_ID,
                log_text
            )

        except Exception as e:

            print(
                "START LOG ERROR:",
                repr(e)
            )


    # =====================================================
    # WELCOME
    # =====================================================

    welcome_photo = get_setting(
        "welcome_photo"
    )

    caption = (
        f"👋 به ربات رسمی {VILLAGE_NAME} خوش آمدید.\n\n"
        "این ربات برای معرفی روستا، مکان‌های دیدنی، محله‌ها، "
        "امکانات، رویدادها و دسترسی سریع به عکس‌ها و فیلم‌های روستا طراحی شده است.\n\n"
        "از منوی زیر بخش موردنظر خود را انتخاب کنید.\n"
        "برای آشنایی با نحوه جستجو و امکانات ربات، گزینه «ℹ️ راهنمای ربات» را انتخاب کنید."
    )

    if welcome_photo:

        try:

            await bot.send_photo(
                msg.chat.id,
                welcome_photo,
                caption=caption,
                reply_markup=main_menu(
                    msg.from_user.id
                )
            )

            return

        except Exception as e:

            print(
                "WELCOME PHOTO ERROR:",
                repr(e)
            )

    await msg.answer(
        caption,
        reply_markup=main_menu(
            msg.from_user.id
        )
    )


# =========================================================
# BACK MAIN
# =========================================================

@dp.callback_query(F.data == "back_main")
async def back_main(
    call: types.CallbackQuery
):

    user_state.pop(call.from_user.id, None)

    await safe_edit_or_send(
        call,
        "🏘 منوی اصلی:",
        main_menu(
            call.from_user.id
        )
    )

    await call.answer()


# =========================================================
# معرفی روستا
# =========================================================

def intro_menu():

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("📖 شناسنامه روستا", callback_data="intro_id", style="danger"))
    kb.add(InlineKeyboardButton("👥 جمعیت روستا", callback_data="intro_pop", style="danger"))
    kb.add(InlineKeyboardButton("🖼 رسانه‌های روستا", callback_data="intro_media", style="danger"))
    kb.add(InlineKeyboardButton("🕰 آرشیو قدیمی روستا", callback_data="intro_old_media", style="danger"))
    kb.add(InlineKeyboardButton("🌴 نخلستان جوزدر", callback_data="intro_nakhlestan", style="success"))
    kb.add(InlineKeyboardButton("📍 لوکیشن روستا", callback_data="intro_loc", style="success"))
    kb.row(InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style="primary"))
    return kb


@dp.callback_query(F.data == "main_intro")
async def main_intro(
    call: types.CallbackQuery
):

    await log_user_activity(
        call.from_user,
        "معرفی روستا",
        "کلیک روی دکمه",
        "ورود به بخش معرفی روستا"
    )

    await safe_edit_or_send(
        call,
        "🏘 معرفی روستا:",
        intro_menu()
    )

    await call.answer()


# =========================================================
# شناسنامه
# =========================================================

@dp.callback_query(F.data == "intro_id")
async def intro_id(call: types.CallbackQuery):

    await log_user_activity(call.from_user, "معرفی روستا", "مشاهده محتوا", "شناسنامه روستا")
    photo_id = get_setting("info_photo")
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔙 بازگشت", callback_data="main_intro", style="primary")
    )

    if photo_id:
        await bot.send_photo(call.message.chat.id, photo_id, reply_markup=kb)
    else:
        await safe_edit_or_send(call, "❌ عکس شناسنامه هنوز توسط مدیریت ثبت نشده است.", kb)
    await call.answer()


# =========================================================
# جمعیت
# =========================================================

@dp.callback_query(F.data == "intro_pop")
async def intro_pop(call: types.CallbackQuery):

    await log_user_activity(call.from_user, "معرفی روستا", "مشاهده محتوا", "جمعیت")
    photo_id = get_setting("population_photo")
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔙 بازگشت", callback_data="main_intro", style="primary")
    )

    if photo_id:
        await bot.send_photo(call.message.chat.id, photo_id, reply_markup=kb)
    else:
        await safe_edit_or_send(call, "❌ عکس جمعیت هنوز توسط مدیریت ثبت نشده است.", kb)
    await call.answer()


# =========================================================
# لوکیشن روستا
# =========================================================

@dp.callback_query(F.data == "intro_loc")
async def intro_loc(
    call: types.CallbackQuery
):

    await log_user_activity(
        call.from_user,
        "معرفی روستا",
        "مشاهده لوکیشن",
        "لوکیشن روستا"
    )

    lat = get_setting(
        "village_lat"
    )

    lon = get_setting(
        "village_lon"
    )

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="main_intro"
        )
    )

    if lat and lon:

        await bot.send_location(
            call.message.chat.id,
            float(lat),
            float(lon)
        )

        await bot.send_message(
            call.message.chat.id,
            "📍 لوکیشن روستا",
            reply_markup=kb
        )

    else:

        await bot.send_message(
            call.message.chat.id,
            "📍 لوکیشن روستا هنوز ثبت نشده.",
            reply_markup=kb
        )

    await call.answer()


# =========================================================
# عکس های روستا
# =========================================================

@dp.callback_query(F.data == "intro_media")
async def intro_media(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.row(InlineKeyboardButton("🖼 عکس‌های روستا", callback_data="intro_village_photo", style="danger"))
    kb.row(InlineKeyboardButton("🎥 فیلم‌های روستا", callback_data="intro_village_video", style="success"))
    kb.row(InlineKeyboardButton("🔙 بازگشت", callback_data="main_intro", style="primary"))
    await safe_edit_or_send(call, "🖼🎥 رسانه‌های روستا:", kb)
    await call.answer()


@dp.callback_query(F.data == "intro_village_photo")
async def intro_village_photo(call: types.CallbackQuery):

    await send_collection_item(
        call.message.chat.id,
        "village",
        "photo",
        0,
        "intro_media"
    )
    await call.answer()


@dp.callback_query(F.data == "intro_village_video")
async def intro_village_video(call: types.CallbackQuery):

    await send_collection_item(
        call.message.chat.id,
        "village",
        "video",
        0,
        "intro_media"
    )
    await call.answer()


@dp.callback_query(F.data == "intro_old_media")
async def intro_old_media(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.row(InlineKeyboardButton("🖼 عکس‌های قدیمی", callback_data="intro_old_photo", style="danger"))
    kb.row(InlineKeyboardButton("🎥 فیلم‌های قدیمی", callback_data="intro_old_video", style="success"))
    kb.row(InlineKeyboardButton("🔙 بازگشت", callback_data="main_intro", style="primary"))
    await safe_edit_or_send(call, "🕰 آرشیو قدیمی روستا:", kb)
    await call.answer()


@dp.callback_query(F.data == "intro_old_photo")
async def intro_old_photo(call: types.CallbackQuery):

    await send_collection_item(
        call.message.chat.id,
        "old_photos",
        "photo",
        0,
        "intro_old_media"
    )
    await call.answer()


@dp.callback_query(F.data == "intro_old_video")
async def intro_old_video(call: types.CallbackQuery):

    await send_collection_item(
        call.message.chat.id,
        "old_photos",
        "video",
        0,
        "intro_old_media"
    )
    await call.answer()


@dp.callback_query(F.data == "intro_nakhlestan")
async def intro_nakhlestan(
    call: types.CallbackQuery
):

    await log_user_activity(
        call.from_user,
        "نخلستان جوزدر",
        "مشاهده محتوا",
        "نخلستان"
    )

    await send_collection_item(
        call.message.chat.id,
        "nakhlestan",
        "photo",
        0,
        "main_intro"
    )

    await call.answer()


# =========================================================
# Navigation collections
# =========================================================

@dp.callback_query(F.data.startswith("colnav|"))
async def collection_navigation(
    call: types.CallbackQuery
):

    parts = call.data.split("|")

    place = parts[1]
    kind = parts[2]
    index = int(parts[3])

    back = (
        parts[4]
        if len(parts) > 4
        else "main_intro"
    )

    await log_user_activity(
        call.from_user,
        "مجموعه رسانه‌ای",
        "مشاهده محتوای بعدی",
        f"{place} - {kind} - شماره {index + 1}"
    )

    await send_collection_item(
        call.message.chat.id,
        place,
        kind,
        index,
        back,
        edit_message=call.message
    )

    await call.answer()


async def send_collection_item(
    chat_id,
    place,
    kind,
    index,
    back_callback,
    edit_message=None
):

    rows = db.execute(
        """
        SELECT id, file_id
        FROM items
        WHERE place = ?
        AND kind = ?
        ORDER BY id
        """,
        (
            place,
            kind
        )
    ).fetchall()

    titles = {
        "village": "🖼 عکس‌های روستا",
        "old_photos": "🕰 عکس‌های قدیمی روستا",
        "nakhlestan": "🌴 نخلستان جوزدر",
    }

    title = titles.get(
        place,
        place
    )

    if not rows:

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data=back_callback
            )
        )

        await bot.send_message(
            chat_id,
            f"{title}\n\nهنوز فایلی ثبت نشده.",
            reply_markup=kb
        )

        return

    if index >= len(rows):

        index = 0

    file_id = rows[index][1]
    item_id = rows[index][0]

    db.execute(
        "UPDATE items SET views = COALESCE(views, 0) + 1 WHERE id = ?",
        (item_id,)
    )
    db.commit()

    kb = InlineKeyboardMarkup()

    prev_index = index - 1 if index > 0 else len(rows) - 1
    next_index = index + 1 if index + 1 < len(rows) else 0

    kb.add(
        InlineKeyboardButton(
            "⬅️ قبلی",
            callback_data=(
                f"colnav|{place}|{kind}|{prev_index}|{back_callback}"
            )
        )
    )

    kb.add(
        InlineKeyboardButton(
            f"➡️ بعدی ({index + 1}/{len(rows)})",
            callback_data=(
                f"colnav|{place}|{kind}|{next_index}|{back_callback}"
            )
        )
    )

    add_like_button(kb, item_id)

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data=back_callback
        )
    )

    caption = (
        f"{title}\n\n"
        f"{'🎥' if kind == 'video' else '📷'} {index + 1} از {len(rows)}"
    )

    if kind == "video":
        sent = await send_or_edit_media(chat_id, "video", file_id, caption, kb, edit_message)
    else:
        sent = await send_or_edit_media(chat_id, "photo", file_id, caption, kb, edit_message)

    remember_item_message(chat_id, sent.message_id, item_id)


# =========================================================
# مکان های دیدنی
# =========================================================

def scenic_menu():

    kb = InlineKeyboardMarkup()

    for key, label in SCENIC_PLACES:

        kb.add(
            InlineKeyboardButton(
                label,
                callback_data=f"splace_{key}"
            )
        )

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="back_main"
        )
    )

    return kb


def scenic_kind_menu(place):

    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🎥 فیلم‌ها",
            callback_data=f"skind_{place}_video"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "🖼 عکس‌ها",
            callback_data=f"skind_{place}_photo"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "📍 لوکیشن",
            callback_data=f"sloc_{place}"
        )
    )

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="main_scenic"
        )
    )

    return kb


@dp.callback_query(F.data == "main_scenic")
async def main_scenic(
    call: types.CallbackQuery
):

    await log_user_activity(
        call.from_user,
        "مکان‌های دیدنی",
        "کلیک روی بخش",
        "ورود به مکان‌های دیدنی"
    )

    await safe_edit_or_send(
        call,
        "🏞 مکان‌های دیدنی رو انتخاب کن:",
        scenic_menu()
    )

    await call.answer()


@dp.callback_query(F.data.startswith("splace_"))
async def choose_scenic_place(
    call: types.CallbackQuery
):

    key = call.data.replace(
        "splace_",
        ""
    )

    label = SCENIC_LABEL.get(
        key,
        key
    )

    await log_user_activity(
        call.from_user,
        "مکان‌های دیدنی",
        "انتخاب مکان",
        label
    )

    await safe_edit_or_send(
        call,
        f"📍 {label}\n\nیکی از گزینه‌ها را انتخاب کن:",
        scenic_kind_menu(key)
    )

    await call.answer()


# =========================================================
# مکان دیدنی - فیلم/عکس
# =========================================================

@dp.callback_query(F.data.startswith("skind_"))
async def choose_scenic_kind(
    call: types.CallbackQuery
):

    _, place, kind = call.data.split("_")

    label = SCENIC_LABEL.get(
        place,
        place
    )

    await log_user_activity(
        call.from_user,
        "مکان‌های دیدنی",
        "مشاهده محتوا",
        f"{label} - {KIND_LABEL[kind]}"
    )

    await send_media_item(
        call.message.chat.id,
        place,
        kind,
        0,
        f"splace_{place}"
    )

    await call.answer()


@dp.callback_query(F.data.startswith("snav_"))
async def scenic_navigation(
    call: types.CallbackQuery
):

    _, place, kind, index = call.data.split("_")

    await log_user_activity(
        call.from_user,
        "مکان‌های دیدنی",
        "مشاهده محتوای بعدی",
        f"{SCENIC_LABEL.get(place, place)} - {KIND_LABEL[kind]}"
    )

    await send_media_item(
        call.message.chat.id,
        place,
        kind,
        int(index),
        f"splace_{place}",
        edit_message=call.message
    )

    await call.answer()


async def send_media_item(
    chat_id,
    place,
    kind,
    index,
    back_callback,
    edit_message=None
):

    rows = db.execute(
        """
        SELECT id, file_id
        FROM items
        WHERE place = ?
        AND kind = ?
        ORDER BY id
        """,
        (
            place,
            kind
        )
    ).fetchall()

    label = SCENIC_LABEL.get(
        place,
        place
    )

    if not rows:

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data=back_callback
            )
        )

        await bot.send_message(
            chat_id,
            f"هنوز {KIND_LABEL[kind]} برای «{label}» ثبت نشده.",
            reply_markup=kb
        )

        return

    if index >= len(rows):

        index = 0

    file_id = rows[index][1]
    item_id = rows[index][0]

    db.execute(
        "UPDATE items SET views = COALESCE(views, 0) + 1 WHERE id = ?",
        (item_id,)
    )
    db.commit()

    kb = InlineKeyboardMarkup()

    prev_index = index - 1 if index > 0 else len(rows) - 1
    next_index = index + 1 if index + 1 < len(rows) else 0

    kb.add(
        InlineKeyboardButton(
            "⬅️ قبلی",
            callback_data=(
                f"snav_{place}_{kind}_{prev_index}"
            )
        )
    )

    kb.add(
        InlineKeyboardButton(
            f"➡️ بعدی ({index + 1}/{len(rows)})",
            callback_data=(
                f"snav_{place}_{kind}_{next_index}"
            )
        )
    )

    add_like_button(kb, item_id)

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data=back_callback
        )
    )

    if kind == "photo":

        sent = await send_or_edit_media(
            chat_id, "photo", file_id,
            f"📍 {label}\n🖼 {index + 1}/{len(rows)}",
            kb, edit_message
        )

    else:

        sent = await send_or_edit_media(
            chat_id, "video", file_id,
            f"📍 {label}\n🎥 {index + 1}/{len(rows)}",
            kb, edit_message
        )

    remember_item_message(chat_id, sent.message_id, item_id)


# =========================================================
# لوکیشن مکان دیدنی
# =========================================================

@dp.callback_query(F.data.startswith("sloc_"))
async def scenic_location(
    call: types.CallbackQuery
):

    place = call.data.replace(
        "sloc_",
        ""
    )

    label = SCENIC_LABEL.get(
        place,
        place
    )

    await log_user_activity(
        call.from_user,
        "مکان‌های دیدنی",
        "مشاهده لوکیشن",
        label
    )

    lat = get_setting(
        f"scenic_{place}_lat"
    )

    lon = get_setting(
        f"scenic_{place}_lon"
    )

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data=f"splace_{place}"
        )
    )

    if lat and lon:

        await bot.send_location(
            call.message.chat.id,
            float(lat),
            float(lon)
        )

        await bot.send_message(
            call.message.chat.id,
            f"📍 لوکیشن {label}",
            reply_markup=kb
        )

    else:

        await bot.send_message(
            call.message.chat.id,
            f"📍 لوکیشن {label} هنوز ثبت نشده.",
            reply_markup=kb
        )

    await call.answer()


# =========================================================
# امکانات روستا
# =========================================================

def facilities_menu():

    kb = InlineKeyboardMarkup()

    for key, label in FACILITIES:

        kb.add(
            InlineKeyboardButton(
                label,
                callback_data=f"facility_{key}"
            )
        )

    kb.add(
        InlineKeyboardButton(
            "🛒 فروشگاه‌ها",
            callback_data="main_shops"
        )
    )

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="back_main",
            style="primary"
        )
    )

    return kb


def facility_kind_menu(key):

    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🎥 فیلم‌ها",
            callback_data=f"fkind_{key}_video"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "🖼 عکس‌ها",
            callback_data=f"fkind_{key}_photo"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "📍 لوکیشن",
            callback_data=f"floc_{key}"
        )
    )

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="main_facilities"
        )
    )

    return kb


@dp.callback_query(F.data == "main_facilities")
async def main_facilities(
    call: types.CallbackQuery
):

    await log_user_activity(
        call.from_user,
        "امکانات روستا",
        "کلیک روی بخش",
        "ورود به امکانات"
    )

    await safe_edit_or_send(
        call,
        "🏫 امکانات روستا:",
        facilities_menu()
    )

    await call.answer()


@dp.callback_query(F.data.startswith("facility_"))
async def choose_facility(
    call: types.CallbackQuery
):

    key = call.data.replace(
        "facility_",
        ""
    )

    label = FACILITY_LABEL.get(
        key,
        key
    )

    await log_user_activity(
        call.from_user,
        "امکانات روستا",
        "انتخاب بخش",
        label
    )

    await safe_edit_or_send(
        call,
        f"{label}\n\nیکی از گزینه‌ها را انتخاب کن:",
        facility_kind_menu(key)
    )

    await call.answer()


@dp.callback_query(F.data.startswith("fkind_"))
async def choose_facility_kind(
    call: types.CallbackQuery
):

    _, key, kind = call.data.split("_")

    label = FACILITY_LABEL.get(
        key,
        key
    )

    await log_user_activity(
        call.from_user,
        "امکانات روستا",
        "مشاهده محتوا",
        f"{label} - {KIND_LABEL[kind]}"
    )

    await send_media_item_generic(
        call.message.chat.id,
        f"facility_{key}",
        kind,
        0,
        f"facility_{key}"
    )

    await call.answer()


@dp.callback_query(F.data.startswith("fnav_"))
async def facility_navigation(
    call: types.CallbackQuery
):

    _, key, kind, index = call.data.split("_")

    await log_user_activity(
        call.from_user,
        "امکانات روستا",
        "مشاهده محتوای بعدی",
        f"{FACILITY_LABEL.get(key, key)} - {KIND_LABEL[kind]}"
    )

    await send_media_item_generic(
        call.message.chat.id,
        f"facility_{key}",
        kind,
        int(index),
        f"facility_{key}",
        edit_message=call.message
    )

    await call.answer()


async def send_media_item_generic(
    chat_id,
    place,
    kind,
    index,
    back_callback,
    edit_message=None
):

    rows = db.execute(
        """
        SELECT id, file_id
        FROM items
        WHERE place = ?
        AND kind = ?
        ORDER BY id
        """,
        (
            place,
            kind
        )
    ).fetchall()

    label_key = place.replace(
        "facility_",
        ""
    )

    label = FACILITY_LABEL.get(
        label_key,
        label_key
    )

    if not rows:

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data=back_callback
            )
        )

        await bot.send_message(
            chat_id,
            f"هنوز فایلی برای {label} ثبت نشده.",
            reply_markup=kb
        )

        return

    if index >= len(rows):

        index = 0

    file_id = rows[index][1]
    item_id = rows[index][0]

    db.execute(
        "UPDATE items SET views = COALESCE(views, 0) + 1 WHERE id = ?",
        (item_id,)
    )
    db.commit()

    kb = InlineKeyboardMarkup()

    prev_index = index - 1 if index > 0 else len(rows) - 1
    next_index = index + 1 if index + 1 < len(rows) else 0

    kb.add(
        InlineKeyboardButton(
            "⬅️ قبلی",
            callback_data=(
                f"fnav_{label_key}_{kind}_{prev_index}"
            )
        )
    )

    kb.add(
        InlineKeyboardButton(
            f"➡️ بعدی ({index + 1}/{len(rows)})",
            callback_data=(
                f"fnav_{label_key}_{kind}_{next_index}"
            )
        )
    )

    add_like_button(kb, item_id)

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data=back_callback
        )
    )

    if kind == "photo":

        sent = await send_or_edit_media(
            chat_id, "photo", file_id,
            f"{label}\n🖼 {index + 1}/{len(rows)}",
            kb, edit_message
        )

    else:

        sent = await send_or_edit_media(
            chat_id, "video", file_id,
            f"{label}\n🎥 {index + 1}/{len(rows)}",
            kb, edit_message
        )

    remember_item_message(chat_id, sent.message_id, item_id)


# =========================================================
# لوکیشن امکانات
# =========================================================

@dp.callback_query(F.data.startswith("floc_"))
async def facility_location(
    call: types.CallbackQuery
):

    key = call.data.replace(
        "floc_",
        ""
    )

    label = FACILITY_LABEL.get(
        key,
        key
    )

    await log_user_activity(
        call.from_user,
        "امکانات روستا",
        "مشاهده لوکیشن",
        label
    )

    lat = get_setting(
        f"facility_{key}_lat"
    )

    lon = get_setting(
        f"facility_{key}_lon"
    )

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data=f"facility_{key}"
        )
    )

    if lat and lon:

        await bot.send_location(
            call.message.chat.id,
            float(lat),
            float(lon)
        )

        await bot.send_message(
            call.message.chat.id,
            f"📍 لوکیشن {label}",
            reply_markup=kb
        )

    else:

        await bot.send_message(
            call.message.chat.id,
            f"📍 لوکیشن {label} هنوز ثبت نشده.",
            reply_markup=kb
        )

    await call.answer()


# =========================================================
# فروشگاه‌ها
# =========================================================

def shops_menu():

    kb = InlineKeyboardMarkup()

    for key, label in SHOPS:

        kb.add(
            InlineKeyboardButton(
                label,
                callback_data=f"shop_{key}"
            )
        )

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="main_facilities"
        )
    )

    return kb


def shop_kind_menu(key):

    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🖼 عکس‌ها",
            callback_data=f"shkind_{key}_photo"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "📍 لوکیشن",
            callback_data=f"shloc_{key}"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "📞 شماره تماس",
            callback_data=f"shphone_{key}"
        )
    )

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="main_shops"
        )
    )

    return kb


@dp.callback_query(F.data == "main_shops")
async def main_shops(
    call: types.CallbackQuery
):

    await log_user_activity(
        call.from_user,
        "فروشگاه‌ها",
        "کلیک روی بخش",
        "ورود به فروشگاه‌ها"
    )

    await safe_edit_or_send(
        call,
        "🛒 فروشگاه‌ها:",
        shops_menu()
    )

    await call.answer()


@dp.callback_query(F.data.startswith("shop_"))
async def choose_shop(
    call: types.CallbackQuery
):

    key = call.data.replace(
        "shop_",
        ""
    )

    label = SHOP_LABEL.get(
        key,
        key
    )

    await log_user_activity(
        call.from_user,
        "فروشگاه‌ها",
        "انتخاب فروشگاه",
        label
    )

    await safe_edit_or_send(
        call,
        f"{label}\n\nیکی از گزینه‌ها را انتخاب کن:",
        shop_kind_menu(key)
    )

    await call.answer()


@dp.callback_query(F.data.startswith("shkind_"))
async def choose_shop_kind(
    call: types.CallbackQuery
):

    _, key, kind = call.data.split("_")

    label = SHOP_LABEL.get(
        key,
        key
    )

    await log_user_activity(
        call.from_user,
        "فروشگاه‌ها",
        "مشاهده محتوا",
        f"{label} - {KIND_LABEL[kind]}"
    )

    await send_shop_media_item(
        call.message.chat.id,
        key,
        0
    )

    await call.answer()


@dp.callback_query(F.data.startswith("shnav_"))
async def shop_navigation(
    call: types.CallbackQuery
):

    _, key, index = call.data.split("_")

    await log_user_activity(
        call.from_user,
        "فروشگاه‌ها",
        "مشاهده عکس بعدی",
        SHOP_LABEL.get(key, key)
    )

    await send_shop_media_item(
        call.message.chat.id,
        key,
        int(index),
        edit_message=call.message
    )

    await call.answer()


async def send_shop_media_item(
    chat_id,
    key,
    index,
    edit_message=None
):

    place = f"shop_{key}"

    label = SHOP_LABEL.get(
        key,
        key
    )

    back_callback = f"shop_{key}"

    rows = db.execute(
        """
        SELECT id, file_id
        FROM items
        WHERE place = ?
        AND kind = 'photo'
        ORDER BY id
        """,
        (place,)
    ).fetchall()

    if not rows:

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data=back_callback
            )
        )

        await bot.send_message(
            chat_id,
            f"هنوز عکسی برای {label} ثبت نشده.",
            reply_markup=kb
        )

        return

    if index >= len(rows):

        index = 0

    item_id, file_id = rows[index]

    db.execute(
        "UPDATE items SET views = COALESCE(views, 0) + 1 WHERE id = ?",
        (item_id,)
    )
    db.commit()

    kb = InlineKeyboardMarkup()

    prev_index = index - 1 if index > 0 else len(rows) - 1
    next_index = index + 1 if index + 1 < len(rows) else 0

    kb.add(
        InlineKeyboardButton(
            "⬅️ قبلی",
            callback_data=f"shnav_{key}_{prev_index}"
        )
    )

    kb.add(
        InlineKeyboardButton(
            f"➡️ بعدی ({index + 1}/{len(rows)})",
            callback_data=f"shnav_{key}_{next_index}"
        )
    )

    add_like_button(kb, item_id)

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data=back_callback
        )
    )

    sent = await send_or_edit_media(
        chat_id, "photo", file_id,
        f"{label}\n🖼 {index + 1}/{len(rows)}",
        kb, edit_message
    )

    remember_item_message(chat_id, sent.message_id, item_id)


@dp.callback_query(F.data.startswith("shloc_"))
async def shop_location(
    call: types.CallbackQuery
):

    key = call.data.replace(
        "shloc_",
        ""
    )

    label = SHOP_LABEL.get(
        key,
        key
    )

    await log_user_activity(
        call.from_user,
        "فروشگاه‌ها",
        "مشاهده لوکیشن",
        label
    )

    lat = get_setting(f"shop_{key}_lat")
    lon = get_setting(f"shop_{key}_lon")

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data=f"shop_{key}"
        )
    )

    if lat and lon:

        await bot.send_location(
            call.message.chat.id,
            float(lat),
            float(lon)
        )

        await bot.send_message(
            call.message.chat.id,
            f"📍 لوکیشن {label}",
            reply_markup=kb
        )

    else:

        await bot.send_message(
            call.message.chat.id,
            f"📍 لوکیشن {label} هنوز ثبت نشده.",
            reply_markup=kb
        )

    await call.answer()


@dp.callback_query(F.data.startswith("shphone_"))
async def shop_phone(
    call: types.CallbackQuery
):

    key = call.data.replace(
        "shphone_",
        ""
    )

    label = SHOP_LABEL.get(
        key,
        key
    )

    await log_user_activity(
        call.from_user,
        "فروشگاه‌ها",
        "مشاهده شماره تماس",
        label
    )

    phone = get_setting(f"shop_{key}_phone")

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data=f"shop_{key}"
        )
    )

    if phone:

        await bot.send_message(
            call.message.chat.id,
            f"📞 شماره تماس {label}:\n{phone}",
            reply_markup=kb
        )

    else:

        await bot.send_message(
            call.message.chat.id,
            f"📞 شماره تماس {label} هنوز ثبت نشده.",
            reply_markup=kb
        )

    await call.answer()


# =========================================================
# محلات
# =========================================================

def neighborhoods_menu():

    photo = get_setting("neighborhoods_photo")

    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="back_main",
            style="primary"
        )
    )

    return photo, kb


@dp.callback_query(F.data == "main_neighborhoods")
async def main_neighborhoods(
    call: types.CallbackQuery
):

    await log_user_activity(
        call.from_user,
        "محلات روستا",
        "کلیک روی بخش",
        "نمایش عکس محلات"
    )

    photo, kb = neighborhoods_menu()

    if photo:
        try:
            await bot.send_photo(
                call.message.chat.id,
                photo,
                caption="🏘 محلات روستای جوزدر",
                reply_markup=kb
            )
        except Exception as e:
            print("NEIGHBORHOODS PHOTO SEND ERROR:", repr(e))
            await safe_edit_or_send(
                call,
                "🏘 محلات روستا\n\nخطا در نمایش عکس.",
                kb
            )
    else:
        await safe_edit_or_send(
            call,
            "🏘 محلات روستا\n\nهنوز عکسی ثبت نشده.",
            kb
        )

    await call.answer()


# =========================================================
# ADMIN PANEL
# =========================================================

def admin_panel():

    kb = InlineKeyboardMarkup(row_width=2)

    kb.row(
        InlineKeyboardButton("➕ افزودن عکس / فیلم", callback_data="admin_add_content", style="success"),
        InlineKeyboardButton("🗑 حذف عکس / فیلم", callback_data="admin_delete_content", style="danger")
    )
    kb.row(
        InlineKeyboardButton("📍 مدیریت لوکیشن‌ها", callback_data="admin_locations", style="primary"),
        InlineKeyboardButton("📞 شماره تماس فروشگاه‌ها", callback_data="admin_shop_phones", style="primary")
    )
    kb.row(
        InlineKeyboardButton("✏️ اطلاعات روستا", callback_data="admin_village_settings", style="primary"),
        InlineKeyboardButton("📊 آمار ربات", callback_data="admin_stats", style="primary")
    )
    kb.row(
        InlineKeyboardButton("📢 اطلاعیه برای کاربران", callback_data="admin_broadcast", style="primary"),
        InlineKeyboardButton("👥 کاربران و مدیران", callback_data="admin_users", style="primary")
    )
    kb.row(
        InlineKeyboardButton("📅 مدیریت رویدادها", callback_data="admin_events", style="primary"),
        InlineKeyboardButton("💾 بکاپ دیتابیس", callback_data="admin_backup", style="primary")
    )
    kb.row(
        InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_main", style="primary")
    )
    return kb


@dp.callback_query(F.data == "admin_panel")
async def admin_panel_callback(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    await safe_edit_or_send(
        call,
        "⚙️ پنل مدیریت:",
        admin_panel()
    )

    await call.answer()


@dp.callback_query(F.data == "admin_cancel")
async def admin_cancel(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    admin_state.pop(call.from_user.id, None)

    await safe_edit_or_send(
        call,
        "⚙️ پنل مدیریت:",
        admin_panel()
    )

    await call.answer("لغو شد.")


def admin_cancel_kb():
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔙 لغو و بازگشت", callback_data="admin_cancel")
    )

def admin_result_kb(back_callback="admin_panel"):
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔙 بازگشت", callback_data=back_callback)
    )



# =========================================================
# ADMIN WORKING ACTIONS
# =========================================================
# (نسخه‌ی واقعی و متصل این توابع پایین‌تر از تابع on_startup تعریف شده)

@dp.callback_query(F.data == "admin_events")
async def admin_events(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔ دسترسی نداری.", show_alert=True)

    rows = db.execute("""
        SELECT id, title, event_date, description
        FROM events
        ORDER BY event_date ASC, id DESC
        LIMIT 30
    """).fetchall()

    text = "📅 مدیریت رویدادها\n━━━━━━━━━━━━━━\n\n"
    if not rows:
        text += "هنوز رویدادی ثبت نشده است."
    else:
        for event_id, title, event_date, description in rows:
            text += (
                f"🆔 {event_id} | 📌 {title or 'بدون عنوان'}\n"
                f"🗓 {event_date or 'بدون تاریخ'}\n"
                f"📝 {(description or '')[:120]}\n\n"
            )

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ افزودن رویداد", callback_data="admin_event_add", style="success"))
    if rows:
        kb.add(InlineKeyboardButton("🗑 حذف یک رویداد", callback_data="admin_event_delete", style="danger"))
    kb.row(InlineKeyboardButton("🔙 پنل مدیریت", callback_data="admin_panel"))

    await safe_edit_or_send(call, text[:4000], kb)
    await call.answer()


@dp.callback_query(F.data == "admin_event_add")
async def admin_event_add(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔ دسترسی نداری.", show_alert=True)

    admin_state[call.from_user.id] = {"mode": "add_event"}

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔙 مدیریت رویدادها", callback_data="admin_events")
    )
    await safe_edit_or_send(
        call,
        "➕ افزودن رویداد\n\n"
        "در پیام بعدی این قالب را بفرست:\n"
        "عنوان | تاریخ | توضیحات\n\n"
        "مثال فقط برای قالب:\n"
        "رویداد نمونه | 1405/01/01 | توضیحات رویداد\n\n"
        "برای لغو /done را بفرست.",
        kb
    )
    await call.answer()


@dp.callback_query(F.data == "admin_event_delete")
async def admin_event_delete(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔ دسترسی نداری.", show_alert=True)

    rows = db.execute("""
        SELECT id, title, event_date
        FROM events
        ORDER BY event_date ASC, id DESC
        LIMIT 30
    """).fetchall()

    kb = InlineKeyboardMarkup()
    for event_id, title, event_date in rows:
        kb.add(
            InlineKeyboardButton(
                f"🗑 {event_id} - {(title or 'بدون عنوان')[:28]}",
                callback_data=f"admin_event_del_{event_id}",
                style="danger"
            )
        )
    kb.row(InlineKeyboardButton("🔙 مدیریت رویدادها", callback_data="admin_events"))

    await safe_edit_or_send(
        call,
        "🗑 رویدادی را که می‌خواهی حذف شود انتخاب کن:",
        kb
    )
    await call.answer()


@dp.callback_query(F.data.startswith("admin_event_del_"))
async def admin_event_del(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔ دسترسی نداری.", show_alert=True)

    try:
        event_id = int(call.data.rsplit("_", 1)[1])
        db.execute("DELETE FROM events WHERE id = ?", (event_id,))
        db.commit()
        await call.answer("✅ رویداد حذف شد.")
        return await admin_events(call)
    except Exception as e:
        print("EVENT DELETE ERROR:", repr(e))
        await call.answer("❌ حذف رویداد انجام نشد.", show_alert=True)


@dp.callback_query(F.data == "admin_backup")
async def admin_backup(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔ دسترسی نداری.", show_alert=True)

    try:
        db.commit()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Path(f"village_backup_{stamp}.db")
        backup_db = sqlite3.connect(str(backup_path))
        try:
            with backup_db:
                db.backup(backup_db)
        finally:
            backup_db.close()

        await bot.send_document(
            call.message.chat.id,
            FSInputFile(str(backup_path)),
            caption=f"💾 بکاپ دیتابیس آماده شد.\n🕐 {stamp}"
        )

        try:
            backup_path.unlink()
        except Exception:
            pass

        await call.answer("✅ بکاپ ساخته شد.")
    except Exception as e:
        print("BACKUP ERROR:", repr(e))
        await call.answer("❌ بکاپ ساخته نشد.", show_alert=True)


@dp.callback_query(F.data == "admin_users")
async def admin_users(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔ دسترسی نداری.", show_alert=True)

    total = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    admins = db.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
    rows = db.execute("""
        SELECT user_id, full_name, username, last_seen
        FROM users
        ORDER BY last_seen DESC
        LIMIT 30
    """).fetchall()

    text = (
        "👥 کاربران و مدیران\n━━━━━━━━━━━━━━\n\n"
        f"👤 کل کاربران: {total}\n"
        f"👑 کل مدیران: {admins}\n\n"
    )
    for uid, name, username, last_seen in rows:
        role = "👑 مدیر" if is_admin(uid) else "👤 کاربر"
        text += (
            f"{role}\n"
            f"نام: {name or '-'}\n"
            f"Username: @{username or '-'}\n"
            f"🆔 {uid}\n"
            f"🕐 آخرین فعالیت: {last_seen or '-'}\n\n"
        )

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔙 پنل مدیریت", callback_data="admin_panel")
    )
    await safe_edit_or_send(call, text[:4000], kb)
    await call.answer()


@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("⛔ دسترسی نداری.", show_alert=True)

    admin_state[call.from_user.id] = {"mode": "broadcast"}

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔙 پنل مدیریت", callback_data="admin_panel")
    )
    await safe_edit_or_send(
        call,
        "📢 اطلاعیه برای کاربران\n\n"
        "متن اطلاعیه را در پیام بعدی بفرست.\n"
        "برای لغو /done را بفرست.",
        kb
    )
    await call.answer()


# =========================================================
# ADMIN STATS (منوی آمار)
# =========================================================

def stats_hub_menu():

    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "📊 خلاصه کلی",
            callback_data="stats_summary"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "🏆 بیشترین لایک",
            callback_data="stats_top_likes"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "👁 بیشترین بازدید",
            callback_data="stats_top_views"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "📍 تفکیک بر اساس بخش",
            callback_data="stats_sections"
        )
    )

    kb.row(
        InlineKeyboardButton(
            "🔙 پنل مدیریت",
            callback_data="admin_panel"
        )
    )

    return kb


@dp.callback_query(F.data == "admin_stats")
async def admin_stats(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    await log_admin_activity(
        call.from_user,
        "ورود به بخش آمار"
    )

    await safe_edit_or_send(
        call,
        "📊 آمار ربات — کدوم بخش رو می‌خوای ببینی؟",
        stats_hub_menu()
    )

    await call.answer()


@dp.callback_query(F.data == "stats_summary")
async def stats_summary(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    users = total_users()
    total_items = db.execute(
        "SELECT COUNT(*) FROM items"
    ).fetchone()[0]
    total_likes = db.execute(
        "SELECT COUNT(*) FROM item_likes"
    ).fetchone()[0]
    total_views = db.execute(
        "SELECT COALESCE(SUM(views), 0) FROM items"
    ).fetchone()[0]

    text = (
        "📊 خلاصه کلی آمار روستا\n\n"
        f"👥 تعداد کاربران یکتا: {users}\n"
        f"🖼🎥 تعداد کل محتوا (عکس و فیلم): {total_items}\n"
        f"❤️ تعداد کل لایک‌ها: {total_likes}\n"
        f"👁 تعداد کل بازدیدها: {total_views}"
    )

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="admin_stats"
        )
    )

    await safe_edit_or_send(
        call,
        text,
        kb
    )

    await call.answer()


def item_label(place, title):

    base = CONTENT_TARGET_LABEL.get(
        place,
        place
    )

    return title or base


@dp.callback_query(F.data == "stats_top_likes")
async def stats_top_likes(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    rows = db.execute(
        """
        SELECT id, place, kind, likes, title
        FROM items
        WHERE likes > 0
        ORDER BY likes DESC, id DESC
        LIMIT 15
        """
    ).fetchall()

    kb = InlineKeyboardMarkup()

    if rows:

        for item_id, place, kind, likes, title in rows:

            kb.add(
                InlineKeyboardButton(
                    f"❤️ {likes} — {item_label(place, title)} ({KIND_LABEL.get(kind, kind)})",
                    callback_data=f"itemlikers_{item_id}"
                )
            )

        text = "🏆 محتواهایی که بیشترین لایک را دارند:\n\nروی هرکدوم بزن تا ببینی کیا لایکش کردن."

    else:

        text = "🏆 هنوز هیچ محتوایی لایک نگرفته."

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="admin_stats"
        )
    )

    await safe_edit_or_send(
        call,
        text,
        kb
    )

    await call.answer()


@dp.callback_query(F.data == "stats_top_views")
async def stats_top_views(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    rows = db.execute(
        """
        SELECT id, place, kind, views, title
        FROM items
        WHERE views > 0
        ORDER BY views DESC, id DESC
        LIMIT 15
        """
    ).fetchall()

    text = "👁 محتواهایی که بیشترین بازدید را دارند:\n\n"

    if rows:

        for item_id, place, kind, views, title in rows:

            text += (
                f"• #{item_id} — {item_label(place, title)} | "
                f"{KIND_LABEL.get(kind, kind)} | 👁 {views}\n"
            )

    else:

        text += "هنوز هیچ محتوایی بازدید نگرفته."

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="admin_stats"
        )
    )

    await safe_edit_or_send(
        call,
        text,
        kb
    )

    await call.answer()


@dp.callback_query(F.data == "stats_sections")
async def stats_sections(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    rows = db.execute(
        """
        SELECT section, views
        FROM activity_stats
        ORDER BY views DESC
        """
    ).fetchall()

    text = "📍 بازدید هر بخش (تفکیک‌شده):\n\n"

    if rows:

        for section, views in rows:

            text += f"• {section}: {views} بازدید\n"

    else:

        text += "هنوز آماری ثبت نشده."

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="admin_stats"
        )
    )

    await safe_edit_or_send(
        call,
        text,
        kb
    )

    await call.answer()


@dp.callback_query(F.data.startswith("itemlikers_"))
async def item_likers(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    item_id = call.data.replace(
        "itemlikers_",
        ""
    )

    item = db.execute(
        "SELECT place, kind, title, likes, views FROM items WHERE id = ?",
        (item_id,)
    ).fetchone()

    if not item:

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data="stats_top_likes"
            )
        )

        await safe_edit_or_send(
            call,
            "❌ این محتوا پیدا نشد (شاید حذف شده).",
            kb
        )

        return await call.answer()

    place, kind, title, likes, views = item
    label = item_label(place, title)

    likers = db.execute(
        """
        SELECT il.user_id, il.created_at, u.full_name, u.username
        FROM item_likes il
        LEFT JOIN users u ON u.user_id = il.user_id
        WHERE il.item_id = ?
        ORDER BY il.created_at DESC
        """,
        (item_id,)
    ).fetchall()

    text = (
        f"👥 کسانی که «{label}» ({KIND_LABEL.get(kind, kind)}) را پسندیده‌اند:\n"
        f"❤️ مجموع لایک: {likes or 0} | 👁 بازدید: {views or 0}\n\n"
    )

    if likers:

        for user_id, created_at, full_name, username in likers:

            uname = (
                f"@{username}"
                if username
                else "بدون یوزرنیم"
            )

            text += (
                f"👤 {full_name or 'بدون نام'} ({uname})\n"
                f"🆔 {user_id} — 🕐 {created_at}\n\n"
            )

    else:

        text += "هنوز کسی این محتوا را لایک نکرده."

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="stats_top_likes"
        )
    )

    await safe_edit_or_send(
        call,
        text,
        kb
    )

    await call.answer()


# =========================================================
# ADMIN CONTENT TARGETS
# =========================================================

CONTENT_TARGETS = []

CONTENT_TARGETS.extend(
    SCENIC_PLACES
)

CONTENT_TARGETS.extend(
    [
        ("village", "🖼 عکس‌های روستا"),
        ("old_photos", "🖼 عکس‌های قدیمی جوزدر"),
        ("nakhlestan", "🌴 نخلستان جوزدر"),
    ]
)

for key, label in FACILITIES:

    CONTENT_TARGETS.append(
        (
            f"facility_{key}",
            label
        )
    )

for key, label in SHOPS:

    CONTENT_TARGETS.append(
        (
            f"shop_{key}",
            f"🛒 {label}"
        )
    )

CONTENT_TARGET_LABEL = dict(CONTENT_TARGETS)


def admin_content_target_menu():

    kb = InlineKeyboardMarkup()

    for key, label in CONTENT_TARGETS:

        kb.add(
            InlineKeyboardButton(
                label,
                callback_data=f"admintarget_{key}"
            )
        )

    kb.row(
        InlineKeyboardButton(
            "🔙 پنل مدیریت",
            callback_data="admin_panel"
        )
    )

    return kb


@dp.callback_query(F.data == "admin_add_content")
async def admin_add_content(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    await log_admin_activity(
        call.from_user,
        "شروع افزودن محتوا"
    )

    await safe_edit_or_send(
        call,
        "📁 محتوا را برای کدام قسمت اضافه می‌کنی؟",
        admin_content_target_menu()
    )

    await call.answer()


@dp.callback_query(F.data.startswith("admintarget_"))
async def admin_choose_target(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    key = call.data.replace(
        "admintarget_",
        ""
    )

    if key.startswith("shop_"):

        admin_state[
            call.from_user.id
        ] = {
            "mode": "media",
            "place": key,
            "kind": "photo"
        }

        label = CONTENT_TARGET_LABEL.get(key, key)

        await log_admin_activity(
            call.from_user,
            "انتخاب نوع محتوا",
            key,
            "🖼 عکس"
        )

        await call.message.edit_text(
            f"📁 {label} — 🖼 عکس\n\n"
            "عکس‌ها را یکی‌یکی بفرست.\n\n"
            "بعد از هر فایل پیام «ذخیره شد» می‌آید.\n"
            "برای پایان: /done",
            reply_markup=admin_cancel_kb()
        )

        await call.answer()

        return

    admin_state[
        call.from_user.id
    ] = {
        "mode": "media",
        "place": key,
        "kind": None
    }

    await safe_edit_or_send(
        call,
        "نوع فایل را انتخاب کن:",
        InlineKeyboardMarkup()
        .add(
            InlineKeyboardButton(
                "🎥 فیلم",
                callback_data=f"adminkind_{key}_video"
            )
        )
        .add(
            InlineKeyboardButton(
                "🖼 عکس",
                callback_data=f"adminkind_{key}_photo"
            )
        )
        .add(
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data="admin_add_content"
            )
        )
    )

    await call.answer()


@dp.callback_query(F.data.startswith("adminkind_"))
async def admin_choose_kind(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    data = call.data.replace(
        "adminkind_",
        ""
    )

    pos = data.rfind("_")

    place = data[:pos]
    kind = data[pos + 1:]

    admin_state[
        call.from_user.id
    ] = {
        "mode": "media",
        "place": place,
        "kind": kind
    }

    await log_admin_activity(
        call.from_user,
        "انتخاب نوع محتوا",
        place,
        KIND_LABEL.get(kind, kind)
    )

    await call.message.edit_text(
        f"📁 {KIND_LABEL[kind]}\n\n"
        "فایل‌ها را یکی‌یکی بفرست.\n\n"
        "بعد از هر فایل پیام «ذخیره شد» می‌آید.\n"
        "برای پایان: /done",
        reply_markup=admin_cancel_kb()
    )

    await call.answer()


# =========================================================
# ADMIN DELETE CONTENT  (بخش جدید — همون چیزی که کم بود)
# =========================================================

def admin_delete_target_menu():

    kb = InlineKeyboardMarkup()

    for key, label in CONTENT_TARGETS:

        kb.add(
            InlineKeyboardButton(
                label,
                callback_data=f"deltarget_{key}"
            )
        )

    kb.row(
        InlineKeyboardButton(
            "🔙 پنل مدیریت",
            callback_data="admin_panel"
        )
    )

    return kb


@dp.callback_query(F.data == "admin_delete_content")
async def admin_delete_content(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    await log_admin_activity(
        call.from_user,
        "شروع حذف محتوا"
    )

    await safe_edit_or_send(
        call,
        "🗑 از کدام قسمت می‌خوای حذف کنی؟",
        admin_delete_target_menu()
    )

    await call.answer()


@dp.callback_query(F.data.startswith("deltarget_"))
async def admin_delete_choose_target(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    key = call.data.replace(
        "deltarget_",
        ""
    )

    if key.startswith("shop_"):

        await send_delete_item(
            call.message.chat.id,
            key,
            "photo",
            0,
            f"deltarget_{key}"
        )

        await call.answer()

        return

    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🎥 فیلم",
            callback_data=f"delkind_{key}_video"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "🖼 عکس",
            callback_data=f"delkind_{key}_photo"
        )
    )

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="admin_delete_content"
        )
    )

    await safe_edit_or_send(
        call,
        "نوع فایلی که می‌خوای حذف کنی رو انتخاب کن:",
        kb
    )

    await call.answer()


@dp.callback_query(F.data.startswith("delkind_"))
async def admin_delete_choose_kind(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    data = call.data.replace(
        "delkind_",
        ""
    )

    pos = data.rfind("_")

    place = data[:pos]
    kind = data[pos + 1:]

    await send_delete_item(
        call.message.chat.id,
        place,
        kind,
        0,
        f"deltarget_{place}"
    )

    await call.answer()


@dp.callback_query(F.data.startswith("delnav_"))
async def admin_delete_navigate(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    data = call.data.replace(
        "delnav_",
        ""
    )

    place, kind, index = data.rsplit(
        "_",
        2
    )

    await send_delete_item(
        call.message.chat.id,
        place,
        kind,
        int(index),
        f"deltarget_{place}"
    )

    await call.answer()


@dp.callback_query(F.data.startswith("delitem_"))
async def admin_delete_item(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    data = call.data.replace(
        "delitem_",
        ""
    )

    item_id, rest = data.split(
        "_",
        1
    )

    place, kind, index = rest.rsplit(
        "_",
        2
    )

    db.execute(
        "DELETE FROM items WHERE id = ?",
        (item_id,)
    )

    db.commit()

    await log_admin_activity(
        call.from_user,
        "حذف محتوا",
        place,
        f"{KIND_LABEL.get(kind, kind)} - آیتم شماره {item_id}"
    )

    await call.answer("🗑 حذف شد")

    await send_delete_item(
        call.message.chat.id,
        place,
        kind,
        int(index),
        f"deltarget_{place}"
    )


async def send_delete_item(
    chat_id,
    place,
    kind,
    index,
    back_callback
):

    rows = db.execute(
        """
        SELECT id, file_id
        FROM items
        WHERE place = ?
        AND kind = ?
        ORDER BY id
        """,
        (
            place,
            kind
        )
    ).fetchall()

    label = CONTENT_TARGET_LABEL.get(
        place,
        place
    )

    if not rows:

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data=back_callback
            )
        )

        await bot.send_message(
            chat_id,
            f"چیزی برای «{label}» ({KIND_LABEL[kind]}) موجود نیست.",
            reply_markup=kb
        )

        return

    index = index % len(rows)

    item_id, file_id = rows[index]

    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            f"🗑 حذف این ({index + 1}/{len(rows)})",
            callback_data=(
                f"delitem_{item_id}_{place}_{kind}_{index}"
            ),
            style="danger"
        )
    )

    kb.add(
        InlineKeyboardButton(
            "➡️ بعدی",
            callback_data=(
                f"delnav_{place}_{kind}_{index + 1}"
            )
        )
    )

    kb.row(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data=back_callback
        )
    )

    if kind == "photo":

        await bot.send_photo(
            chat_id,
            file_id,
            caption=(
                f"{label}\n"
                f"🖼 {index + 1}/{len(rows)}"
            ),
            reply_markup=kb
        )

    else:

        await bot.send_video(
            chat_id,
            file_id,
            caption=(
                f"{label}\n"
                f"🎥 {index + 1}/{len(rows)}"
            ),
            reply_markup=kb
        )


# =========================================================
# ADMIN LOCATIONS
# =========================================================

def admin_locations_menu():

    kb = InlineKeyboardMarkup()

    for key, label in SCENIC_PLACES:

        kb.add(
            InlineKeyboardButton(
                f"🏞 {label}",
                callback_data=f"adminloc_scenic_{key}"
            )
        )

    for key, label in FACILITIES:

        kb.add(
            InlineKeyboardButton(
                label,
                callback_data=f"adminloc_facility_{key}"
            )
        )

    for key, label in SHOPS:

        kb.add(
            InlineKeyboardButton(
                f"🛒 {label}",
                callback_data=f"adminloc_shop_{key}"
            )
        )

    kb.add(
        InlineKeyboardButton(
            "📍 لوکیشن روستا",
            callback_data="adminloc_village"
        )
    )

    kb.row(
        InlineKeyboardButton(
            "🔙 پنل مدیریت",
            callback_data="admin_panel"
        )
    )

    return kb


@dp.callback_query(F.data == "admin_locations")
async def admin_locations(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    await safe_edit_or_send(
        call,
        "📍 لوکیشن کدام قسمت را می‌خواهی تغییر بدهی؟",
        admin_locations_menu()
    )

    await call.answer()


@dp.callback_query(F.data.startswith("adminloc_"))
async def admin_location_select(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    data = call.data.replace(
        "adminloc_",
        ""
    )

    if data == "village":

        setting_prefix = "village"

    else:

        pos = data.find("_")

        category = data[:pos]
        key = data[pos + 1:]

        setting_prefix = (
            f"{category}_{key}"
        )

    admin_state[
        call.from_user.id
    ] = {
        "mode": "set_custom_location",
        "prefix": setting_prefix
    }

    await log_admin_activity(
        call.from_user,
        "انتخاب تغییر لوکیشن",
        setting_prefix
    )

    await call.message.edit_text(
        "📍 حالا لوکیشن را با گزینه Location تلگرام بفرست.",
        reply_markup=admin_cancel_kb()
    )

    await call.answer()


# =========================================================
# ADMIN SHOP PHONES
# =========================================================

def admin_shop_phones_menu():

    kb = InlineKeyboardMarkup()

    for key, label in SHOPS:

        kb.add(
            InlineKeyboardButton(
                label,
                callback_data=f"adminphone_{key}"
            )
        )

    kb.row(
        InlineKeyboardButton(
            "🔙 پنل مدیریت",
            callback_data="admin_panel"
        )
    )

    return kb


@dp.callback_query(F.data == "admin_shop_phones")
async def admin_shop_phones(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    await safe_edit_or_send(
        call,
        "📞 شماره تماس کدام فروشگاه را می‌خواهی تنظیم کنی؟",
        admin_shop_phones_menu()
    )

    await call.answer()


@dp.callback_query(F.data.startswith("adminphone_"))
async def admin_shop_phone_select(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    key = call.data.replace(
        "adminphone_",
        ""
    )

    admin_state[
        call.from_user.id
    ] = {
        "mode": "set_shop_phone",
        "key": key
    }

    label = SHOP_LABEL.get(
        key,
        key
    )

    await log_admin_activity(
        call.from_user,
        "انتخاب تغییر شماره تماس",
        label
    )

    await call.message.edit_text(
        f"📞 شماره تماس «{label}» را بفرست:",
        reply_markup=admin_cancel_kb()
    )

    await call.answer()


# =========================================================
# ADMIN VILLAGE SETTINGS
# =========================================================

def admin_village_settings():

    kb = InlineKeyboardMarkup(row_width=2)

    kb.row(
        InlineKeyboardButton("📖 تغییر متن شناسنامه", callback_data="set_info"),
        InlineKeyboardButton("🖼 عکس شناسنامه", callback_data="set_info_photo")
    )
    kb.row(
        InlineKeyboardButton("👥 تغییر متن جمعیت", callback_data="set_population"),
        InlineKeyboardButton("🖼 عکس جمعیت", callback_data="set_population_photo")
    )
    kb.row(
        InlineKeyboardButton("📍 تغییر لوکیشن روستا", callback_data="set_location"),
        InlineKeyboardButton("🖼 تغییر عکس خوش‌آمدگویی", callback_data="set_welcome")
    )
    kb.row(
        InlineKeyboardButton("🏘 عکس محلات روستا", callback_data="set_neighborhoods_photo")
    )
    kb.row(
        InlineKeyboardButton("🔙 پنل مدیریت", callback_data="admin_panel")
    )
    return kb


@dp.callback_query(F.data == "admin_village_settings")
async def admin_village_settings_callback(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer(
            "⛔ دسترسی نداری.",
            show_alert=True
        )

    await safe_edit_or_send(
        call,
        "✏️ چه چیزی را می‌خواهی تغییر بدهی؟",
        admin_village_settings()
    )

    await call.answer()


# =========================================================
# SET INFO
# =========================================================

@dp.callback_query(F.data == "set_info")
async def set_info_start(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    admin_state[
        call.from_user.id
    ] = {
        "mode": "set_info"
    }

    await log_admin_activity(
        call.from_user,
        "شروع تغییر شناسنامه"
    )

    await call.message.edit_text(
        "📖 متن جدید شناسنامه روستا را بفرست:",
        reply_markup=admin_cancel_kb()
    )

    await call.answer()


# =========================================================
# SET POPULATION
# =========================================================

@dp.callback_query(F.data == "set_population")
async def set_population_start(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    admin_state[
        call.from_user.id
    ] = {
        "mode": "set_population"
    }

    await log_admin_activity(
        call.from_user,
        "شروع تغییر جمعیت"
    )

    await call.message.edit_text(
        "👥 متن جدید جمعیت را بفرست:",
        reply_markup=admin_cancel_kb()
    )

    await call.answer()


# =========================================================
# SET INFO PHOTO
# =========================================================

@dp.callback_query(F.data == "set_info_photo")
async def set_info_photo_start(call: types.CallbackQuery):

    if not is_admin(call.from_user.id):
        return await call.answer("⛔ دسترسی نداری.", show_alert=True)

    admin_state[call.from_user.id] = {"mode": "set_info_photo"}

    await call.message.edit_text(
        "🖼 عکس شناسنامه روستا را بفرست:",
        reply_markup=admin_cancel_kb()
    )
    await call.answer()


# =========================================================
# SET POPULATION PHOTO
# =========================================================

@dp.callback_query(F.data == "set_population_photo")
async def set_population_photo_start(call: types.CallbackQuery):

    if not is_admin(call.from_user.id):
        return await call.answer("⛔ دسترسی نداری.", show_alert=True)

    admin_state[call.from_user.id] = {"mode": "set_population_photo"}

    await call.message.edit_text(
        "🖼 عکس مربوط به جمعیت روستا را بفرست:",
        reply_markup=admin_cancel_kb()
    )
    await call.answer()



# =========================================================
# SET LOCATION
# =========================================================

@dp.callback_query(F.data == "set_location")
async def set_location_start(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    admin_state[
        call.from_user.id
    ] = {
        "mode": "set_location"
    }

    await log_admin_activity(
        call.from_user,
        "شروع تغییر لوکیشن روستا"
    )

    await call.message.edit_text(
        "📍 لوکیشن جدید روستا را با Location تلگرام بفرست.",
        reply_markup=admin_cancel_kb()
    )

    await call.answer()


# =========================================================
# SET WELCOME
# =========================================================

@dp.callback_query(F.data == "set_welcome")
async def set_welcome_start(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    admin_state[
        call.from_user.id
    ] = {
        "mode": "set_welcome"
    }

    await log_admin_activity(
        call.from_user,
        "شروع تغییر عکس خوش‌آمدگویی"
    )

    await call.message.edit_text(
        "🖼 عکس خوش‌آمدگویی جدید را بفرست:",
        reply_markup=admin_cancel_kb()
    )

    await call.answer()


# =========================================================
# SET NEIGHBORHOODS PHOTO
# =========================================================

@dp.callback_query(F.data == "set_neighborhoods_photo")
async def set_neighborhoods_photo_start(
    call: types.CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):

        return await call.answer()

    admin_state[
        call.from_user.id
    ] = {
        "mode": "set_neighborhoods_photo"
    }

    await log_admin_activity(
        call.from_user,
        "شروع تغییر عکس محلات روستا"
    )

    await call.message.edit_text(
        "🏘 عکس جدید محلات روستا را بفرست:",
        reply_markup=admin_cancel_kb()
    )

    await call.answer()


# =========================================================
# DONE
# =========================================================

@dp.message(Command("done"))
async def done(
    msg: types.Message
):

    user_state.pop(msg.from_user.id, None)

    if not is_admin(
        msg.from_user.id
    ):

        return

    if msg.from_user.id in admin_state:

        state = admin_state.pop(
            msg.from_user.id
        )

        await log_admin_activity(
            msg.from_user,
            "پایان عملیات",
            state.get("place", ""),
            state.get("kind", "")
        )

        await msg.reply(
            "✅ عملیات تمام شد.",
            reply_markup=admin_result_kb("admin_panel")
        )

    else:

        await msg.reply(
            "ℹ️ هیچ عملیات فعالی وجود ندارد."
        )



# =========================================================
# USER PRO FEATURES
# =========================================================

user_state = {}


def user_menu():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔎 جستجوی محتوا", callback_data="user_search"))
    kb.add(InlineKeyboardButton("📅 رویدادهای روستا", callback_data="user_events"))
    kb.add(InlineKeyboardButton("📜 تاریخچه جوزدر", callback_data="user_history"))
    kb.add(InlineKeyboardButton("🔔 اعلان‌ها", callback_data="user_notifications"))
    kb.add(InlineKeyboardButton("📬 پیشنهاد و پیام", callback_data="user_feedback"))
    kb.row(InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_main"))
    return kb


@dp.callback_query(F.data == "user_help")
async def user_help(call: types.CallbackQuery):
    text = (
        f"ℹ️ راهنمای استفاده از ربات {VILLAGE_NAME}\n\n"
        "🏘 معرفی روستا\n"
        "اطلاعات عمومی، شناسنامه، جمعیت، عکس‌ها و لوکیشن روستا را مشاهده کنید.\n\n"
        "🏞 مکان‌های دیدنی\n"
        "برای هر مکان می‌توانید عکس‌ها، فیلم‌ها و لوکیشن آن را مشاهده کنید.\n\n"
        "🏘 محلات روستا\n"
        "محله موردنظر را انتخاب کنید و به عکس‌ها، فیلم‌ها و لوکیشن آن دسترسی داشته باشید.\n\n"
        "🏫 امکانات روستا\n"
        "امکانات ثبت‌شده روستا را همراه با محتوای مربوط به هر بخش مشاهده کنید.\n\n"
        "🔎 جستجوی محتوا\n"
        "می‌توانید نام مکان، محله، امکانات، عنوان یا توضیحات عکس و فیلم و رویدادها را جستجو کنید.\n\n"
        "نمونه جستجو:\n"
        "• راستبراگ\n"
        "• راست براگ\n"
        "• عکس‌های راست براگ\n"
        "• مدرسه\n"
        ""
        "• رویداد\n\n"
        "نکته: فاصله و نیم‌فاصله و تفاوت «ی/ي» و «ک/ك» در جستجو نادیده گرفته می‌شود.\n\n"
        "📅 رویدادهای روستا\n"
        "رویدادهای ثبت‌شده را همراه با تاریخ و توضیحات ببینید.\n\n"
        "📬 پیشنهاد و پیام\n"
        "پیشنهاد، انتقاد یا پیام خود را ارسال کنید تا برای مدیریت ربات ثبت و بررسی شود.\n\n"
        "🔙 برای بازگشت، دکمه «منوی اصلی» را بزنید."
    )

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton(
            "🔎 شروع جستجو",
            callback_data="user_search"
        )
    )
    kb.row(
        InlineKeyboardButton(
            "🔙 منوی اصلی",
            callback_data="back_main"
        )
    )

    await safe_edit_or_send(call, text, kb)
    await call.answer()


SEARCH_INTRO_TEXT = (
    "🔎 جستجوی ربات\n\n"
    "نام مکان، محله، امکانات، فروشگاه، عنوان عکس یا فیلم، توضیحات، رویداد یا حتی متن شناسنامه/جمعیت را بنویس.\n\n"
    "مثال‌ها:\n"
    "• راستبراگ\n"
    "• راست براگ\n"
    "• عکس‌های راست براگ\n"
    "• عکس های راست براگ\n"
    "• مدرسه\n"
    "• سوپرمارکت ستار\n"
    "• رویداد\n\n"
    "فاصله، نیم‌فاصله و تفاوت بعضی حروف فارسی و عربی نادیده گرفته می‌شود.\n"
    "جستجو باز می‌مونه تا هرچقدر خواستی جستجو کنی؛ برای پایان دکمه‌ی «🔚 پایان جستجو» رو بزن یا /done رو بفرست."
)


def search_intro_keyboard():
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🔚 پایان جستجو", callback_data="end_search", style="primary"))
    return kb


@dp.callback_query(F.data == "user_search")
async def user_search_start(call: types.CallbackQuery):
    user_state[call.from_user.id] = "search"
    await safe_edit_or_send(
        call,
        SEARCH_INTRO_TEXT,
        search_intro_keyboard()
    )
    await call.answer()


@dp.message(Command("search"))
async def search_command(msg: types.Message):
    user_state[msg.from_user.id] = "search"
    await bot.send_message(
        msg.chat.id,
        SEARCH_INTRO_TEXT,
        reply_markup=search_intro_keyboard()
    )


@dp.callback_query(F.data == "end_search")
async def end_search(call: types.CallbackQuery):
    user_state.pop(call.from_user.id, None)
    await safe_edit_or_send(
        call,
        "🔎 جستجو تموم شد.\n\nیه گزینه رو انتخاب کن:",
        main_menu(call.from_user.id)
    )
    await call.answer()


@dp.callback_query(F.data == "user_events")
async def user_events(call: types.CallbackQuery):
    rows = db.execute(
        "SELECT id, title, event_date, description FROM events ORDER BY event_date ASC, id DESC"
    ).fetchall()
    if not rows:
        text = "📅 رویدادهای روستا\n\nفعلاً رویدادی ثبت نشده."
    else:
        parts = ["📅 رویدادهای روستا\n"]
        for _, title, event_date, description in rows[:20]:
            parts.append(
                f"🔹 {title}\n"
                f"🗓 {event_date or 'بدون تاریخ'}\n"
                f"{description or ''}\n"
            )
        text = "\n".join(parts)
    await safe_edit_or_send(call, text, InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_main")))
    await call.answer()


@dp.callback_query(F.data == "user_history")
async def user_history(call: types.CallbackQuery):
    rows = db.execute(
        "SELECT activity_type, details, created_at FROM activity_logs WHERE user_id = ? ORDER BY id DESC LIMIT 15",
        (call.from_user.id,)
    ).fetchall()
    if not rows:
        text = "📜 تاریخچه جوزدر\n\nهنوز فعالیتی ثبت نشده."
    else:
        text = "📜 تاریخچه فعالیت شما\n\n"
        for activity, details, created_at in rows:
            text += f"• {created_at} — {activity}\n"
            if details:
                text += f"  {details}\n"
    await safe_edit_or_send(call, text, InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_main")))
    await call.answer()


@dp.callback_query(F.data == "user_notifications")
async def user_notifications(call: types.CallbackQuery):
    row = db.execute(
        "SELECT enabled FROM user_notifications WHERE user_id = ?",
        (call.from_user.id,)
    ).fetchone()
    enabled = row[0] if row else 1
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton(
            "🔕 خاموش کردن" if enabled else "🔔 روشن کردن",
            callback_data="toggle_notifications"
        )
    )
    kb.add(InlineKeyboardButton("📢 آخرین اطلاعیه‌ها", callback_data="last_notifications"))
    kb.row(InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_main"))
    await safe_edit_or_send(
        call,
        f"🔔 اعلان‌ها\n\nوضعیت: {'فعال' if enabled else 'خاموش'}",
        kb
    )
    await call.answer()


@dp.callback_query(F.data == "toggle_notifications")
async def toggle_notifications(call: types.CallbackQuery):
    row = db.execute(
        "SELECT enabled FROM user_notifications WHERE user_id = ?",
        (call.from_user.id,)
    ).fetchone()
    new_value = 0 if row and row[0] else 1
    db.execute(
        """INSERT INTO user_notifications(user_id, enabled) VALUES(?, ?)
        ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled""",
        (call.from_user.id, new_value)
    )
    db.commit()
    await call.answer("🔔 اعلان‌ها روشن شد." if new_value else "🔕 اعلان‌ها خاموش شد.")
    await user_notifications(call)


@dp.callback_query(F.data == "last_notifications")
async def last_notifications(call: types.CallbackQuery):
    rows = db.execute(
        "SELECT title, message, created_at FROM notifications ORDER BY id DESC LIMIT 10"
    ).fetchall()
    text = "📢 آخرین اطلاعیه‌ها\n\n"
    if not rows:
        text += "اطلاعیه‌ای ثبت نشده."
    else:
        for title, message, created_at in rows:
            text += f"🔹 {title}\n🕐 {created_at}\n{message}\n\n"
    await safe_edit_or_send(call, text, InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_main")))
    await call.answer()


@dp.callback_query(F.data == "user_feedback")
async def user_feedback_start(call: types.CallbackQuery):
    user_state[call.from_user.id] = "feedback"
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_main")
    )
    await safe_edit_or_send(
        call,
        "📬 پیام، پیشنهاد یا انتقادت را بفرست.\n\nبرای لغو /done را بزن.",
        kb
    )
    await call.answer()


@dp.callback_query(F.data == "user_more")
async def user_more(call: types.CallbackQuery):
    await safe_edit_or_send(call, "📌 امکانات بیشتر:", main_menu(call.from_user.id))
    await call.answer()


def normalize_search_text(text):
    if not text:
        return ""

    text = str(text)
    replacements = {
        "ي": "ی", "ى": "ی", "ك": "ک",
        "ة": "ه", "ۀ": "ه", "ؤ": "و",
        "إ": "ا", "أ": "ا", "ٱ": "ا",
        "‌": "", "‍": "", "ـ": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _search_terms(query):
    q = normalize_search_text(query)
    q = re.sub(
        r"\b(لوکیشن|موقعیت|مختصات|آدرس|عکس|عکسها|عکسهای|عکسای|"
        r"فیلم|فیلمها|فیلمهای|فیلمای|و|از|در|های|ها|را|روستا)\b",
        " ",
        q
    )
    q = re.sub(r"\s+", " ", q).strip()
    return q, [x for x in q.split() if x]


def _search_match(query, *values):
    q, words = _search_terms(query)
    if not q:
        return False

    searchable = " ".join(
        normalize_search_text(v)
        for v in values if v
    )
    compact_searchable = searchable.replace(" ", "")
    compact_query = q.replace(" ", "")

    return (
        compact_query in compact_searchable
        or all(word in searchable for word in words)
    )


def _location_intent(query):
    q = normalize_search_text(query)
    return any(x in q for x in ("لوکیشن", "موقعیت", "مختصات", "آدرس"))


def _known_location_matches(query):
    matches = []

    for key, label in SCENIC_PLACES:
        if _search_match(query, label, key):
            matches.append(("scenic", key, label))

    for key, label in FACILITIES:
        if _search_match(query, label, key):
            matches.append(("facility", key, label))

    if _search_match(query, VILLAGE_NAME, "روستا", "جوزدر"):
        matches.append(("village", "village", VILLAGE_NAME))

    return matches


def search_content(query):
    q = normalize_search_text(query)
    if not q:
        return []

    for prefix in ("لوکیشن ", "موقعیت ", "آدرس "):
        if q.startswith(prefix):
            q = q[len(prefix):].strip()
            break

    results = []

    try:
        rows = db.execute(
            "SELECT id, place, kind, title, description, likes, views, file_id "
            "FROM items ORDER BY views DESC, likes DESC, id DESC"
        ).fetchall()
    except Exception as e:
        print("SEARCH ITEMS ERROR:", repr(e))
        rows = []

    for row in rows:
        item_id, place, kind, title, description, likes, views, file_id = row
        label = CONTENT_TARGET_LABEL.get(place, place or "")
        if _search_match(q, place, label, title, description, KIND_LABEL.get(kind, "")):
            results.append({"type": "item", "data": row, "score": 30})

    for group_name, collection in (
        ("scenic", SCENIC_PLACES),
        ("facility", FACILITIES),
        ("shop", SHOPS),
    ):
        for key, label in collection:
            if _search_match(q, label, key):
                if group_name == "scenic":
                    lat = get_setting(f"scenic_{key}_lat")
                    lon = get_setting(f"scenic_{key}_lon")
                    callback = f"sloc_{key}"
                elif group_name == "shop":
                    lat = get_setting(f"shop_{key}_lat")
                    lon = get_setting(f"shop_{key}_lon")
                    callback = f"shloc_{key}"
                else:
                    lat = get_setting(f"facility_{key}_lat")
                    lon = get_setting(f"facility_{key}_lon")
                    callback = f"floc_{key}"
                results.append({
                    "type": "known_location",
                    "data": (group_name, key, label, lat, lon, callback),
                    "score": 25
                })

    info_text = get_setting("info_text", "")
    if info_text and _search_match(q, info_text, "شناسنامه روستا"):
        results.append({
            "type": "village_text",
            "data": ("📖 شناسنامه روستا", info_text),
            "score": 22
        })

    population_text = get_setting("population_text", "")
    if population_text and _search_match(q, population_text, "جمعیت"):
        results.append({
            "type": "village_text",
            "data": ("👥 جمعیت روستا", population_text),
            "score": 22
        })

    try:
        place_rows = db.execute(
            "SELECT id, place_type, name, description, file_id, lat, lon "
            "FROM places ORDER BY id DESC"
        ).fetchall()
    except Exception:
        place_rows = []

    for row in place_rows:
        if _search_match(q, row[2], row[3], row[1]):
            results.append({"type": "location", "data": row, "score": 20})

    try:
        event_rows = db.execute(
            "SELECT id, title, event_date, description "
            "FROM events ORDER BY event_date ASC, id DESC"
        ).fetchall()
    except Exception:
        event_rows = []

    for row in event_rows:
        if _search_match(q, row[1], row[2], row[3]):
            results.append({"type": "event", "data": row, "score": 10})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:20]
@dp.message(Command("add_event"))
async def add_event_command(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    admin_state[msg.from_user.id] = {"mode": "add_event"}
    await msg.reply("📅 رویداد را در یک پیام به شکل زیر بفرست:\nعنوان | تاریخ | توضیحات")


@dp.message(Command("admin_users"))
async def admin_users_command(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    rows = db.execute(
        "SELECT user_id, full_name, username, last_seen FROM users ORDER BY last_seen DESC LIMIT 50"
    ).fetchall()
    text = "👥 آخرین کاربران\n\n"
    for uid, name, username, last_seen in rows:
        text += f"🆔 {uid} | {name or '-'} | @{username or '-'} | {last_seen or '-'}\n"
    await msg.reply(text[:4000])


@dp.message(
    lambda msg: msg.from_user.id in user_state,
    F.content_type.in_({"text", "photo", "video"})
)
async def user_search_feedback_router(msg: types.Message):
    """پردازش واقعی حالت‌های 'search' و 'feedback' که با دکمه‌های کاربر ست می‌شن.
    این هندلر عمداً از admin_state استفاده نمی‌کنه تا هیچ‌وقت با اطلاعیه/بکاپ/رویداد ادمین قاطی نشه."""

    mode = user_state.get(msg.from_user.id)

    if mode == "search":

        if not msg.text:
            user_state[msg.from_user.id] = "search"
            return await msg.reply(
                "🔎 برای جستجو باید متن بفرستی، نه عکس یا فیلم.",
                reply_markup=search_intro_keyboard()
            )

        results = search_content(msg.text.strip())

        try:
            await msg.delete()
        except Exception:
            pass

        if not results:
            end_kb = InlineKeyboardMarkup()
            end_kb.row(InlineKeyboardButton("🔚 پایان جستجو", callback_data="end_search", style="primary"))
            return await bot.send_message(
                msg.chat.id,
                "🔎 نتیجه‌ای پیدا نشد.\n\nیه چیز دیگه رو امتحان کن، یا برای پایان جستجو دکمه‌ی زیر رو بزن.",
                reply_markup=end_kb
            )

        header = f"🔎 نتایج جستجو ({len(results)} مورد)"

        await bot.send_message(msg.chat.id, header)

        text_buffer = ""

        last_index = len(results) - 1

        for i, r in enumerate(results):
            rtype = r["type"]
            data = r["data"]
            is_last = (i == last_index)

            if rtype == "item":

                if text_buffer:
                    await bot.send_message(msg.chat.id, text_buffer[:4000])
                    text_buffer = ""

                item_id, place, kind, title, description, likes, views, file_id = data
                label = title or CONTENT_TARGET_LABEL.get(place, place or "")
                caption = (
                    f"📁 {label}\n"
                    f"{KIND_LABEL.get(kind, kind)} | ❤️ {likes or 0} | 👁 {views or 0}"
                )

                kb = InlineKeyboardMarkup()
                if is_last:
                    kb.row(InlineKeyboardButton("🔚 پایان جستجو", callback_data="end_search", style="primary"))

                try:
                    if kind == "photo":
                        sent = await bot.send_photo(
                            msg.chat.id, file_id, caption=caption,
                            reply_markup=kb if is_last else None
                        )
                    else:
                        sent = await bot.send_video(
                            msg.chat.id, file_id, caption=caption,
                            reply_markup=kb if is_last else None
                        )
                    remember_item_message(msg.chat.id, sent.message_id, item_id)
                except Exception:
                    await bot.send_message(msg.chat.id, caption)

            elif rtype == "location":
                _, place_type, name, description, file_id, lat, lon = data
                caption = f"📍 {name} ({place_type})"
                kb = InlineKeyboardMarkup()
                if is_last:
                    kb.row(InlineKeyboardButton("🔚 پایان جستجو", callback_data="end_search", style="primary"))
                if file_id:
                    if text_buffer:
                        await bot.send_message(msg.chat.id, text_buffer[:4000])
                        text_buffer = ""
                    try:
                        await bot.send_photo(
                            msg.chat.id, file_id, caption=caption,
                            reply_markup=kb if is_last else None
                        )
                    except Exception:
                        text_buffer += caption + "\n\n"
                else:
                    text_buffer += caption + "\n\n"
                if lat and lon:
                    try:
                        await bot.send_location(msg.chat.id, float(lat), float(lon))
                    except Exception:
                        pass

            elif rtype == "known_location":
                group_name, key, label, lat, lon, callback = data
                if lat and lon:
                    if text_buffer:
                        await bot.send_message(msg.chat.id, text_buffer[:4000])
                        text_buffer = ""
                    kb = InlineKeyboardMarkup()
                    if is_last:
                        kb.row(InlineKeyboardButton("🔚 پایان جستجو", callback_data="end_search", style="primary"))
                    await bot.send_message(msg.chat.id, f"📍 {label}", reply_markup=kb if is_last else None)
                    try:
                        await bot.send_location(msg.chat.id, float(lat), float(lon))
                    except Exception:
                        pass
                else:
                    text_buffer += f"📍 {label}\n\n"

            elif rtype == "village_text":
                title, full_text = data
                snippet = full_text[:200] + ("…" if len(full_text) > 200 else "")
                text_buffer += f"{title}\n{snippet}\n\n"

            elif rtype == "event":
                event_id, title, event_date, description = data
                text_buffer += f"📅 {title or 'بدون عنوان'} — {event_date or ''}\n\n"

        if text_buffer:
            kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔚 پایان جستجو", callback_data="end_search", style="primary")
            )
            await bot.send_message(msg.chat.id, text_buffer[:4000], reply_markup=kb)

        return

    if mode == "feedback":

        user_state.pop(msg.from_user.id, None)

        header = (
            "📬 پیام جدید کاربر (پیشنهاد و پیام)\n\n"
            f"👤 نام: {get_user_name(msg.from_user)}\n"
            f"🔹 Username: {get_username(msg.from_user)}\n"
            f"🆔 شناسه: {msg.from_user.id}\n"
            f"🕐 زمان: {now_text()}\n"
        )

        sent = False

        if USER_MESSAGE_GROUP_ID:
            try:
                if msg.photo:
                    caption = header + "\n📷 نوع پیام: عکس"
                    if msg.caption:
                        caption += f"\n\n💬 کپشن:\n{msg.caption}"
                    await bot.send_photo(
                        USER_MESSAGE_GROUP_ID,
                        msg.photo[-1].file_id,
                        caption=caption[:1024]
                    )
                elif msg.video:
                    caption = header + "\n🎥 نوع پیام: فیلم"
                    if msg.caption:
                        caption += f"\n\n💬 کپشن:\n{msg.caption}"
                    await bot.send_video(
                        USER_MESSAGE_GROUP_ID,
                        msg.video.file_id,
                        caption=caption[:1024]
                    )
                else:
                    body = (msg.text or "").strip()
                    if not body:
                        user_state[msg.from_user.id] = "feedback"
                        return await msg.reply("❌ پیام خالی است، دوباره بفرست.")
                    await bot.send_message(
                        USER_MESSAGE_GROUP_ID,
                        header + f"\n💬 متن:\n{body}"
                    )
                sent = True
            except Exception as e:
                print("FEEDBACK FORWARD ERROR:", repr(e))

        try:
            await msg.delete()
        except Exception:
            pass

        result_text = (
            "✅ پیام شما برای مدیریت ارسال شد."
            if sent
            else "✅ پیام شما ثبت شد."
        )

        return await bot.send_message(
            msg.chat.id,
            result_text,
            reply_markup=main_menu(msg.from_user.id)
        )

@dp.message(
    lambda msg: (
        not is_admin(msg.from_user.id)
        and msg.chat.type == "private"
        and msg.content_type == "text"
    ),
    F.content_type.in_({"text"})
)
async def user_incoming_message(msg: types.Message):
    """پیام کاربر را به گروه جداگانه می‌فرستد و سپس از چت ربات حذف می‌کند."""

    if msg.voice or msg.audio:
        try:
            await msg.delete()
        except Exception:
            pass
        await bot.send_message(
            msg.chat.id,
            "❌ ارسال پیام صوتی و فایل صوتی مجاز نیست.",
            reply_markup=main_menu(msg.from_user.id)
        )
        return

    if not USER_MESSAGE_GROUP_ID:
        print("USER_MESSAGE_GROUP_ID تنظیم نشده است.")
        return

    header = (
        "📩 پیام جدید کاربر\n\n"
        f"👤 نام: {get_user_name(msg.from_user)}\n"
        f"🔹 Username: {get_username(msg.from_user)}\n"
        f"🆔 شناسه: {msg.from_user.id}\n"
        f"🕐 زمان: {now_text()}\n"
    )

    try:
        if msg.photo:
            await bot.send_photo(
                USER_MESSAGE_GROUP_ID,
                msg.photo[-1].file_id,
                caption=header + "\n📷 نوع پیام: عکس"
            )
            message_type = "photo"

        elif msg.video:
            caption = header + "\n🎥 نوع پیام: فیلم"
            if msg.caption:
                caption += f"\n\n💬 کپشن:\n{msg.caption}"
            await bot.send_video(
                USER_MESSAGE_GROUP_ID,
                msg.video.file_id,
                caption=caption[:1024]
            )
            message_type = "video"

        elif msg.document:
            await bot.send_document(
                USER_MESSAGE_GROUP_ID,
                msg.document.file_id,
                caption=header + "\n📎 نوع پیام: فایل"
            )
            message_type = "document"

        elif msg.text:
            await bot.send_message(
                USER_MESSAGE_GROUP_ID,
                header + f"\n💬 متن:\n{msg.text}"
            )
            message_type = "text"

        else:
            return

        db.execute(
            "INSERT INTO user_messages(user_id, message_type, created_at) VALUES(?, ?, ?)",
            (msg.from_user.id, message_type, now_text())
        )
        db.commit()

        try:
            await msg.delete()
        except Exception:
            pass

        await bot.send_message(
            msg.chat.id,
            "✅ دریافت شد.",
            reply_markup=main_menu(msg.from_user.id)
        )

    except Exception as e:
        print("USER MESSAGE FORWARD ERROR:", repr(e))
        await bot.send_message(
            msg.chat.id,
            "❌ ارسال پیام انجام نشد. دوباره تلاش کن.",
            reply_markup=main_menu(msg.from_user.id)
        )


# =========================================================
# ADMIN MESSAGE ROUTER
# =========================================================

@dp.message(
    lambda msg: not (
        msg.text
        and msg.text.startswith("/")
    ),
    F.content_type.in_({
        "photo",
        "video",
        "location",
        "text"
    })
)
async def admin_router(
    msg: types.Message
):

    if not is_admin(
        msg.from_user.id
    ):

        return

    state = admin_state.get(
        msg.from_user.id
    )

    if not state:
        return

    mode = state.get(
        "mode"
    )

    # =====================================================
    # INFO PHOTO
    # =====================================================

    if mode == "set_info_photo":

        if not msg.photo:
            await msg.reply(
                "❌ لطفاً عکس بفرست.",
                reply_markup=admin_cancel_kb()
            )
            return

        set_setting("info_photo", msg.photo[-1].file_id)
        admin_state.pop(msg.from_user.id, None)

        await log_admin_activity(
            msg.from_user,
            "تغییر عکس شناسنامه روستا",
            "اطلاعات روستا"
        )

        await msg.reply(
            "✅ عکس شناسنامه روستا با موفقیت ذخیره شد.",
            reply_markup=admin_result_kb("admin_village_settings")
        )
        return

    # =====================================================
    # POPULATION PHOTO
    # =====================================================

    if mode == "set_population_photo":

        if not msg.photo:
            await msg.reply(
                "❌ لطفاً عکس بفرست.",
                reply_markup=admin_cancel_kb()
            )
            return

        set_setting("population_photo", msg.photo[-1].file_id)
        admin_state.pop(msg.from_user.id, None)

        await log_admin_activity(
            msg.from_user,
            "تغییر عکس جمعیت روستا",
            "جمعیت"
        )

        await msg.reply(
            "✅ عکس جمعیت روستا با موفقیت ذخیره شد.",
            reply_markup=admin_result_kb("admin_village_settings")
        )
        return

    # =====================================================
    # MEDIA
    # =====================================================

    if mode == "media":

        place = state["place"]
        kind = state["kind"]

        if kind == "photo":

            if not msg.photo:

                await msg.reply(
                    "❌ لطفاً عکس بفرست."
                )

                return

            file_id = msg.photo[-1].file_id

        elif kind == "video":

            if not msg.video:

                await msg.reply(
                    "❌ لطفاً فیلم بفرست."
                )

                return

            file_id = msg.video.file_id

        else:

            await msg.reply(
                "❌ نوع فایل نامعتبر است."
            )

            return

        try:

            db.execute(
                """
                INSERT INTO items
                (place, kind, file_id)
                VALUES (?, ?, ?)
                """,
                (
                    place,
                    kind,
                    file_id
                )
            )

            db.commit()

            count = db.execute(
                """
                SELECT COUNT(*)
                FROM items
                WHERE place = ?
                AND kind = ?
                """,
                (
                    place,
                    kind
                )
            ).fetchone()[0]

            await log_admin_activity(
                msg.from_user,
                "افزودن محتوا",
                place,
                f"{KIND_LABEL[kind]} - فایل شماره {count}"
            )

            await msg.reply(
                "✅ فایل با موفقیت ذخیره شد.\n\n"
                f"📁 نوع: {KIND_LABEL[kind]}\n"
                f"🔢 تعداد فعلی: {count}\n\n"
                "برای فایل بعدی، همان فایل را بفرست.\n"
                "برای پایان: /done",
                reply_markup=admin_result_kb("admin_cancel")
            )

        except Exception as e:

            await log_admin_activity(
                msg.from_user,
                "افزودن محتوا",
                place,
                repr(e),
                "ناموفق"
            )

            await msg.reply(
                "❌ خطا هنگام ذخیره فایل:\n\n"
                f"{repr(e)}"
            )

            print(
                "DATABASE ERROR:",
                repr(e)
            )

        return

    # =====================================================
    # CUSTOM LOCATION
    # =====================================================

    if mode == "set_custom_location":

        if not msg.location:

            await msg.reply(
                "❌ لطفاً Location تلگرام را بفرست."
            )

            return

        prefix = state["prefix"]

        set_setting(
            f"{prefix}_lat",
            str(msg.location.latitude)
        )

        set_setting(
            f"{prefix}_lon",
            str(msg.location.longitude)
        )

        admin_state.pop(
            msg.from_user.id,
            None
        )

        await log_admin_activity(
            msg.from_user,
            "تغییر لوکیشن",
            prefix,
            f"{msg.location.latitude}, {msg.location.longitude}"
        )

        await msg.reply(
            "✅ لوکیشن با موفقیت ذخیره شد."
        ,
            reply_markup=admin_result_kb('admin_locations')
        )

        return

    # =====================================================
    # VILLAGE LOCATION
    # =====================================================

    if mode == "set_location":

        if not msg.location:

            await msg.reply(
                "❌ لطفاً لوکیشن را با Location تلگرام بفرست."
            )

            return

        set_setting(
            "village_lat",
            str(msg.location.latitude)
        )

        set_setting(
            "village_lon",
            str(msg.location.longitude)
        )

        admin_state.pop(
            msg.from_user.id,
            None
        )

        await log_admin_activity(
            msg.from_user,
            "تغییر لوکیشن روستا",
            "روستا",
            f"{msg.location.latitude}, {msg.location.longitude}"
        )

        await msg.reply(
            "✅ لوکیشن روستا با موفقیت تغییر کرد."
        ,
            reply_markup=admin_result_kb('admin_village_settings')
        )

        return

    # =====================================================
    # SHOP PHONE
    # =====================================================

    if mode == "set_shop_phone":

        if not msg.text:

            await msg.reply(
                "❌ لطفاً شماره تماس را به‌صورت متن بفرست."
            )

            return

        key = state["key"]

        label = SHOP_LABEL.get(
            key,
            key
        )

        set_setting(
            f"shop_{key}_phone",
            msg.text.strip()
        )

        admin_state.pop(
            msg.from_user.id,
            None
        )

        await log_admin_activity(
            msg.from_user,
            "تغییر شماره تماس فروشگاه",
            label,
            msg.text.strip()
        )

        await msg.reply(
            f"✅ شماره تماس «{label}» ذخیره شد."
        ,
            reply_markup=admin_result_kb('admin_shop_phones')
        )

        return

    # =====================================================
    # INFO
    # =====================================================

    if mode == "set_info":

        if not msg.text:

            await msg.reply(
                "❌ لطفاً متن بفرست."
            )

            return

        set_setting(
            "info_text",
            msg.text
        )

        admin_state.pop(
            msg.from_user.id,
            None
        )

        await log_admin_activity(
            msg.from_user,
            "تغییر شناسنامه روستا",
            "اطلاعات روستا"
        )

        await msg.reply(
            "✅ شناسنامه روستا به‌روز شد."
        ,
            reply_markup=admin_result_kb('admin_village_settings')
        )

        return

    # =====================================================
    # POPULATION
    # =====================================================

    if mode == "set_population":

        if not msg.text:

            await msg.reply(
                "❌ لطفاً متن بفرست."
            )

            return

        set_setting(
            "population_text",
            msg.text
        )

        admin_state.pop(
            msg.from_user.id,
            None
        )

        await log_admin_activity(
            msg.from_user,
            "تغییر اطلاعات جمعیت",
            "جمعیت"
        )

        await msg.reply(
            "✅ اطلاعات جمعیت به‌روز شد."
        ,
            reply_markup=admin_result_kb('admin_village_settings')
        )

        return

    # =====================================================
    # WELCOME
    # =====================================================

    if mode == "set_welcome":

        if not msg.photo:

            await msg.reply(
                "❌ لطفاً یک عکس بفرست."
            )

            return

        set_setting(
            "welcome_photo",
            msg.photo[-1].file_id
        )

        admin_state.pop(
            msg.from_user.id,
            None
        )

        await log_admin_activity(
            msg.from_user,
            "تغییر عکس خوش‌آمدگویی",
            "صفحه شروع"
        )

        await msg.reply(
            "✅ عکس خوش‌آمدگویی تغییر کرد."
        ,
            reply_markup=admin_result_kb('admin_village_settings')
        )

        return

    if mode == "set_neighborhoods_photo":

        if not msg.photo:

            await msg.reply(
                "❌ لطفاً یک عکس بفرست."
            )

            return

        set_setting(
            "neighborhoods_photo",
            msg.photo[-1].file_id
        )

        admin_state.pop(
            msg.from_user.id,
            None
        )

        await log_admin_activity(
            msg.from_user,
            "تغییر عکس محلات روستا"
        )

        await msg.reply(
            "✅ عکس محلات روستا تغییر کرد.",
            reply_markup=admin_result_kb('admin_village_settings')
        )

        return

    if mode == "add_event":

        if not msg.text:

            await msg.reply(
                "❌ لطفاً متن با قالب «عنوان | تاریخ | توضیحات» بفرست."
            )

            return

        parts = [p.strip() for p in msg.text.split("|")]

        title = parts[0] if len(parts) > 0 else ""
        event_date = parts[1] if len(parts) > 1 else ""
        description = parts[2] if len(parts) > 2 else ""

        if not title:

            await msg.reply(
                "❌ عنوان نمی‌تواند خالی باشد. دوباره با قالب «عنوان | تاریخ | توضیحات» بفرست."
            )

            return

        db.execute(
            "INSERT INTO events (title, event_date, description, created_at) VALUES (?, ?, ?, ?)",
            (title, event_date, description, now_text())
        )
        db.commit()

        admin_state.pop(
            msg.from_user.id,
            None
        )

        await log_admin_activity(
            msg.from_user,
            "افزودن رویداد",
            title
        )

        await msg.reply(
            f"✅ رویداد «{title}» اضافه شد."
        ,
            reply_markup=admin_result_kb('admin_events')
        )

        return

    if mode == "broadcast":

        text = (msg.text or "").strip()

        if not text:

            await msg.reply(
                "❌ متن اطلاعیه نمی‌تواند خالی باشد."
            )

            return

        admin_state.pop(
            msg.from_user.id,
            None
        )

        try:
            rows = db.execute(
                "SELECT user_id FROM users"
            ).fetchall()
        except Exception as e:
            print("BROADCAST USERS ERROR:", repr(e))
            await msg.reply("❌ فهرست کاربران قابل دریافت نیست.")
            return

        sent = 0
        failed = 0

        for (uid,) in rows:
            try:
                await bot.send_message(
                    uid,
                    "📢 اطلاعیه روستا\n\n" + text
                )
                sent += 1
            except Exception:
                failed += 1

        await log_admin_activity(
            msg.from_user,
            "ارسال اطلاعیه",
            f"موفق: {sent} - ناموفق: {failed}"
        )

        await msg.reply(
            f"✅ اطلاعیه ارسال شد.\n\n📨 موفق: {sent}\n❌ ناموفق: {failed}"
        )

        return


# =========================================================
# ADMIN COMMAND
# =========================================================

@dp.message(Command("admin"))
async def admin_command(
    msg: types.Message
):

    if not is_admin(
        msg.from_user.id
    ):

        return

    await log_admin_activity(
        msg.from_user,
        "ورود به پنل مدیریت"
    )

    await msg.answer(
        "⚙️ پنل مدیریت:",
        reply_markup=admin_panel()
    )


# =========================================================
# ERROR HANDLER
# =========================================================

@dp.error()
async def errors_handler(
    event
):

    print(
        "BOT ERROR:",
        repr(event.exception)
    )

    return True


# =========================================================
# COMMANDS
# =========================================================

async def setup_commands():

    await bot.set_my_commands(
        [
            BotCommand(
                "start",
                "🏘 شروع ربات"
            ),
            BotCommand(
                "search",
                "🔎 جستجو"
            )
        ],
        scope=BotCommandScopeDefault()
    )

    await bot.set_my_commands(
        [
            BotCommand(
                "start",
                "🏘 شروع ربات"
            ),
            BotCommand(
                "search",
                "🔎 جستجو"
            ),
            BotCommand(
                "admin",
                "⚙️ پنل مدیریت"
            ),
            BotCommand(
                "done",
                "✅ پایان عملیات"
            ),
            BotCommand(
                "add_event",
                "📅 افزودن رویداد"
            ),
            BotCommand(
                "admin_users",
                "👥 لیست کاربران"
            ),
        ],
        scope=BotCommandScopeChat(
            chat_id=OWNER
        )
    )


# =========================================================
# STARTUP
# =========================================================

async def on_startup():

    db.execute(
        "INSERT OR IGNORE INTO admins(user_id, role, created_at) VALUES(?, ?, ?)",
        (OWNER, "owner", now_text())
    )
    db.commit()

    print(
        "==================================="
    )

    print(
        "✅ ربات روستا فعال شد"
    )

    print(
        "✅ Database: village.db"
    )

    print(
        "✅ Admin:",
        OWNER
    )

    print(
        "✅ Start Log Group:",
        START_LOG_GROUP_ID
    )

    print(
        "✅ Activity Log Group:",
        ACTIVITY_LOG_GROUP_ID
    )

    print(
        "✅ Admin Log Group:",
        ADMIN_LOG_GROUP_ID
    )

    print(
        "==================================="
    )

    await setup_commands()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    async def main():

        await bot.delete_webhook(drop_pending_updates=True)

        await on_startup()

        await dp.start_polling(bot)

    asyncio.run(main())
