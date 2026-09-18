import os
import json
import random
import logging

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# =========================================================
# تنظیمات
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MY_CHAT_ID = os.getenv("MY_CHAT_ID")
HANANEH_CHAT_ID = os.getenv("HANANEH_CHAT_ID")


if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN در فایل .env تنظیم نشده است.")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY در فایل .env تنظیم نشده است.")

if not HANANEH_CHAT_ID or not HANANEH_CHAT_ID.isdigit():
    raise ValueError("HANANEH_CHAT_ID در فایل .env تنظیم نشده است.")


HANANEH_ID = int(HANANEH_CHAT_ID)


# =========================================================
# افراد مجاز
# =========================================================

ADMIN_IDS = set()

if MY_CHAT_ID and MY_CHAT_ID.isdigit():
    ADMIN_IDS.add(int(MY_CHAT_ID))

ADMIN_IDS.add(HANANEH_ID)


# =========================================================
# لاگ
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# Gemini
# =========================================================

ai_client = genai.Client(
    api_key=GEMINI_API_KEY
)

GEMINI_MODEL = "gemini-2.5-flash"


# =========================================================
# فایل‌ها
# =========================================================

WORDS_FILE = "words.json"
DAILY_QUIZ_FILE = "daily_quiz.json"


# =========================================================
# دسترسی
# =========================================================

def is_authorized(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def check_access(update: Update) -> bool:

    user = update.effective_user

    if not user:
        return False

    if is_authorized(user.id):
        return True

    message = "دست نزن جیزه، دسترسی نداری 😈"

    if update.callback_query:
        await update.callback_query.answer(
            message,
            show_alert=True
        )

    elif update.message:
        await update.message.reply_text(message)

    return False


# =========================================================
# مدیریت فایل لغات
# =========================================================

def load_words():

    if not os.path.exists(WORDS_FILE):
        return {}

    try:

        with open(
            WORDS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        logger.error(
            f"خطا در خواندن words.json: {e}"
        )

        return {}


def save_words(words):

    with open(
        WORDS_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            words,
            f,
            ensure_ascii=False,
            indent=4
        )


# =========================================================
# مدیریت فایل آزمون موقت
# =========================================================

def load_daily_quiz():

    if not os.path.exists(DAILY_QUIZ_FILE):
        return None

    try:

        with open(
            DAILY_QUIZ_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        logger.error(
            f"خطا در خواندن daily_quiz.json: {e}"
        )

        return None


def save_daily_quiz(data):

    with open(
        DAILY_QUIZ_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4
        )


def delete_daily_quiz():

    if os.path.exists(DAILY_QUIZ_FILE):

        try:

            os.remove(DAILY_QUIZ_FILE)

        except Exception as e:

            logger.error(
                f"خطا در حذف daily_quiz.json: {e}"
            )


# =========================================================
# ساخت گزینه‌های انحرافی با Gemini
# =========================================================

class Distractors(BaseModel):
    options: list[str]


def generate_distractors(
    word,
    meaning,
    all_words
):

    prompt = f"""
You are creating a multiple-choice English vocabulary quiz.

English word:
{word}

Correct Persian meaning:
{meaning}

Generate exactly 3 different Persian meanings as WRONG options.

Rules:
1. They must NOT be synonyms of the correct answer.
2. They must NOT be the correct answer.
3. They should be plausible vocabulary answers.
4. They must be in Persian.
5. Do not write "گزینه ۱", "گزینه ۲",
   "گزینه فرعی ۱" or similar labels.
6. Do not explain anything.
7. Return exactly 3 options.
"""

    try:

        response = ai_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": Distractors,
            },
        )

        result = response.parsed

        if result and len(result.options) == 3:

            options = []

            for option in result.options:

                option = str(option).strip()

                if (
                    option
                    and option != meaning
                    and option not in options
                ):
                    options.append(option)

            if len(options) == 3:
                return options

    except Exception as e:

        logger.warning(
            f"Gemini error for '{word}': {e}"
        )

    # =====================================================
    # Fallback 1:
    # استفاده از معنی سایر لغات
    # =====================================================

    other_meanings = []

    for other_word, info in all_words.items():

        if other_word.lower() == word.lower():
            continue

        if not isinstance(info, dict):
            continue

        other_meaning = info.get("meaning")

        if (
            other_meaning
            and other_meaning != meaning
            and other_meaning not in other_meanings
        ):
            other_meanings.append(
                other_meaning
            )

    if len(other_meanings) >= 3:

        return random.sample(
            other_meanings,
            3
        )

    # =====================================================
    # Fallback 2:
    # گزینه‌های آماده
    # =====================================================

    fallback = [
        "توسعه و پیشرفت",
        "ارزیابی و بررسی",
        "اقدام و عمل",
        "تمرکز و توجه",
        "تعهد و مسئولیت",
        "تغییر و تحول",
        "ارتباط و تعامل",
        "احساس و عاطفه",
    ]

    fallback = [
        x
        for x in fallback
        if x != meaning
    ]

    random.shuffle(fallback)

    return fallback[:3]


# =========================================================
# ساخت آزمون
# =========================================================

def prepare_quiz():

    words = load_words()

    # فقط لغات فعال
    active_words = []

    for word, info in words.items():

        if info.get("status") == "active":
            active_words.append(
                (word, info)
            )

    # پنج لغت اول صف
    selected = active_words[:5]

    if not selected:
        return None

    items = []

    for word, info in selected:

        meaning = info["meaning"]

        # ساخت گزینه‌های انحرافی
        distractors = generate_distractors(
            word,
            meaning,
            words
        )

        options = distractors + [meaning]

        # حذف موارد تکراری
        options = list(
            dict.fromkeys(options)
        )

        # اطمینان از داشتن ۴ گزینه
        backup_options = [
            "توسعه",
            "بررسی",
            "ارتباط",
            "تغییر",
            "پیشرفت",
            "تمرکز",
        ]

        for option in backup_options:

            if (
                len(options) >= 4
            ):
                break

            if (
                option != meaning
                and option not in options
            ):
                options.append(option)

        options = options[:4]

        random.shuffle(options)

        correct_index = options.index(
            meaning
        )

        items.append({
            "word": word,
            "meaning": meaning,
            "options": options,
            "correct_index": correct_index,
        })

    quiz = {
        "items": items,
        "current_index": 0,
        "score": 0,
    }

    save_daily_quiz(quiz)

    return quiz


# =========================================================
# ارسال سؤال بعدی
# =========================================================

async def send_next_question(
    chat_id,
    context: ContextTypes.DEFAULT_TYPE
):

    quiz = load_daily_quiz()

    if not quiz:
        return

    current_index = quiz["current_index"]

    # =====================================================
    # پایان آزمون
    # =====================================================

    if current_index >= len(quiz["items"]):

        score = quiz["score"]
        total = len(quiz["items"])

        delete_daily_quiz()

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "🎉 آزمون تموم شد!\n\n"
                f"📊 نتیجه:\n"
                f"{score} از {total} پاسخ درست بود.\n\n"
                "اگر خواستی دوباره تست بگیری، "
                "هر وقت آماده بودی /quiz رو بزن."
            )
        )

        return

    # =====================================================
    # سؤال فعلی
    # =====================================================

    item = quiz["items"][current_index]

    keyboard = []

    for index, option in enumerate(
        item["options"]
    ):

        keyboard.append([
            InlineKeyboardButton(
                option,
                callback_data=f"answer_{index}"
            )
        ])

    reply_markup = InlineKeyboardMarkup(
        keyboard
    )

    text = (
        f"📝 لغت {current_index + 1} "
        f"از {len(quiz['items'])}\n\n"

        f"🇬🇧 {item['word']}\n\n"

        "معنی کدام است؟"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup
    )


# =========================================================
# جابه‌جایی لغت به انتهای صف
# =========================================================

def move_word_to_end(
    words,
    word
):

    if word not in words:
        return

    info = words.pop(word)

    words[word] = info


# =========================================================
# پردازش پاسخ
# =========================================================

async def handle_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await check_access(update):
        return

    query = update.callback_query

    await query.answer()

    data = query.data

    chat_id = update.effective_chat.id

    # =====================================================
    # پاسخ به سؤال
    # =====================================================

    if not data.startswith("answer_"):
        return

    quiz = load_daily_quiz()

    if not quiz:

        await query.answer(
            "این آزمون دیگر فعال نیست.",
            show_alert=True
        )

        return

    current_index = quiz["current_index"]

    if current_index >= len(
        quiz["items"]
    ):
        return

    item = quiz["items"][current_index]

    selected_index = int(
        data.split("_")[1]
    )

    correct_index = item[
        "correct_index"
    ]

    word = item["word"]

    meaning = item["meaning"]

    words = load_words()

    if word not in words:

        await query.edit_message_text(
            "❌ این لغت دیگر در بانک لغات وجود ندارد."
        )

        quiz["current_index"] += 1

        save_daily_quiz(quiz)

        await send_next_question(
            chat_id,
            context
        )

        return

    # =====================================================
    # پاسخ درست
    # =====================================================

    if selected_index == correct_index:

        quiz["score"] += 1

        words[word]["review_count"] = (
            words[word].get(
                "review_count",
                0
            ) + 1
        )

        review_count = words[word][
            "review_count"
        ]

        if review_count >= 3:

            # بعد از سومین مرور غیرفعال شود
            words[word]["status"] = "inactive"

        else:

            # هنوز فعال است
            words[word]["status"] = "active"

        # همیشه به انتهای صف منتقل شود
        move_word_to_end(
            words,
            word
        )

        save_words(words)

        await query.edit_message_text(
            (
                "✅ درست بود! 🎉\n\n"
                f"🇬🇧 {word}\n"
                f"🇮🇷 {meaning}\n\n"
                f"🔄 مرور: {review_count} از ۳"
            )
        )

    # =====================================================
    # پاسخ غلط
    # =====================================================

    else:

        selected_answer = item[
            "options"
        ][selected_index]

        words[word]["review_count"] = (
            words[word].get(
                "review_count",
                0
            ) + 1
        )

        review_count = words[word][
            "review_count"
        ]

        if review_count >= 3:

            words[word]["status"] = "inactive"

        else:

            words[word]["status"] = "active"

        # انتقال به انتهای صف
        move_word_to_end(
            words,
            word
        )

        save_words(words)

        await query.edit_message_text(
            (
                "❌ اشتباه بود.\n\n"
                f"انتخاب تو:\n"
                f"❌ {selected_answer}\n\n"

                f"پاسخ صحیح:\n"
                f"✅ {meaning}\n\n"

                f"🔄 مرور: {review_count} از ۳"
            )
        )

    # =====================================================
    # رفتن به سؤال بعد
    # =====================================================

    quiz["current_index"] += 1

    save_daily_quiz(quiz)

    await send_next_question(
        chat_id,
        context
    )


# =========================================================
# /start
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await check_access(update):
        return

    text = (
        "سلام حنانه جان 🌱\n\n"
        "ربات یادآوری لغات آماده‌ست. ❤️\n\n"

        "📌 دستورات:\n\n"

        "➕ اضافه کردن لغت:\n"
        "/add apple سیب\n\n"

        "🗑 حذف لغت:\n"
        "/remove apple\n\n"

        "📚 لغات فعال:\n"
        "/list\n\n"

        "🎓 لغات غیرفعال:\n"
        "/inactive\n\n"

        "🎯 شروع آزمون:\n"
        "/quiz"
    )

    await update.message.reply_text(
        text
    )


# =========================================================
# /add
# =========================================================

async def add_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await check_access(update):
        return

    if len(context.args) < 2:

        await update.message.reply_text(
            "فرمت صحیح:\n\n"
            "/add apple سیب"
        )

        return

    word = context.args[0].lower().strip()

    meaning = " ".join(
        context.args[1:]
    ).strip()

    words = load_words()

    # اگر قبلاً وجود داشته
    if word in words:

        await update.message.reply_text(
            f"⚠️ لغت {word} قبلاً وجود دارد."
        )

        return

    # لغت جدید
    words[word] = {
        "meaning": meaning,
        "status": "active",
        "review_count": 0,
    }

    save_words(words)

    await update.message.reply_text(
        (
            f"✅ لغت {word} اضافه شد.\n\n"
            "📌 تعداد مرور: ۰ از ۳\n"
            "📍 در انتهای صف قرار گرفت."
        )
    )


# =========================================================
# /remove
# =========================================================

async def remove_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await check_access(update):
        return

    if not context.args:

        await update.message.reply_text(
            "مثال:\n"
            "/remove apple"
        )

        return

    word = context.args[0].lower().strip()

    words = load_words()

    if word not in words:

        await update.message.reply_text(
            f"❌ لغت {word} پیدا نشد."
        )

        return

    del words[word]

    save_words(words)

    await update.message.reply_text(
        f"🗑 لغت {word} حذف شد."
    )


# =========================================================
# /list
# =========================================================

async def list_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await check_access(update):
        return

    words = load_words()

    active_words = [
        (word, info)
        for word, info in words.items()
        if info.get("status") == "active"
    ]

    if not active_words:

        await update.message.reply_text(
            "📚 هیچ لغت فعالی وجود ندارد."
        )

        return

    lines = [
        "📚 لغات فعال:\n"
    ]

    for index, (word, info) in enumerate(
        active_words,
        start=1
    ):

        meaning = info.get(
            "meaning",
            "-"
        )

        review_count = info.get(
            "review_count",
            0
        )

        lines.append(
            f"{index}. 🇬🇧 {word}\n"
            f"   🇮🇷 {meaning}\n"
            f"   🔄 مرور: "
            f"{review_count}/3\n"
        )

    lines.append(
        f"📊 مجموع لغات فعال: "
        f"{len(active_words)}"
    )

    await update.message.reply_text(
        "\n".join(lines)
    )


# =========================================================
# /inactive
# =========================================================

async def inactive_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await check_access(update):
        return

    words = load_words()

    inactive_words = [
        (word, info)
        for word, info in words.items()
        if info.get("status") == "inactive"
    ]

    if not inactive_words:

        await update.message.reply_text(
            "🎓 هنوز هیچ لغتی غیرفعال نشده."
        )

        return

    lines = [
        "🎓 لغات غیرفعال‌شده:\n"
    ]

    for index, (word, info) in enumerate(
        inactive_words,
        start=1
    ):

        meaning = info.get(
            "meaning",
            "-"
        )

        review_count = info.get(
            "review_count",
            0
        )

        lines.append(
            f"{index}. 🇬🇧 {word}\n"
            f"   🇮🇷 {meaning}\n"
            f"   ✅ مرور شده: "
            f"{review_count}/3\n"
        )

    lines.append(
        f"📊 مجموع لغات غیرفعال: "
        f"{len(inactive_words)}"
    )

    await update.message.reply_text(
        "\n".join(lines)
    )


# =========================================================
# /quiz
# =========================================================

async def quiz_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await check_access(update):
        return

    chat_id = update.effective_chat.id

    # اگر یک آزمون نیمه‌تمام وجود دارد
    existing_quiz = load_daily_quiz()

    if existing_quiz:

        await update.message.reply_text(
            "🔄 یک آزمون نیمه‌تمام وجود دارد.\n"
            "از همان‌جا ادامه می‌دهیم."
        )

        await send_next_question(
            chat_id,
            context
        )

        return

    # ساخت آزمون جدید
    quiz = prepare_quiz()

    if not quiz:

        await update.message.reply_text(
            "📚 در حال حاضر هیچ لغت فعالی برای آزمون وجود ندارد."
        )

        return

    count = len(
        quiz["items"]
    )

    await update.message.reply_text(
        (
            f"🎯 آزمون آماده شد!\n\n"
            f"امروز {count} لغت داریم.\n"
            "بزن بریم 🚀"
        )
    )

    await send_next_question(
        chat_id,
        context
    )


# =========================================================
# پیام افراد غیرمجاز
# =========================================================

async def unauthorized_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await check_access(update)


# =========================================================
# اجرای ربات
# =========================================================

def main():

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # دستورات
    app.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    app.add_handler(
        CommandHandler(
            "add",
            add_command
        )
    )

    app.add_handler(
        CommandHandler(
            "remove",
            remove_command
        )
    )

    app.add_handler(
        CommandHandler(
            "list",
            list_command
        )
    )

    app.add_handler(
        CommandHandler(
            "inactive",
            inactive_command
        )
    )

    app.add_handler(
        CommandHandler(
            "quiz",
            quiz_command
        )
    )

    # دکمه‌های آزمون
    app.add_handler(
        CallbackQueryHandler(
            handle_callback
        )
    )

    # پیام‌های معمولی
    app.add_handler(
        MessageHandler(
            filters.ALL,
            unauthorized_message
        )
    )

    logger.info(
        "Bot is running..."
    )

    app.run_polling()


# =========================================================
# شروع
# =========================================================

if __name__ == "__main__":
    main()
