import os
import json
import random
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler
)
from google import genai

# بارگذاری متغیرهای محیطی
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# راه‌اندازی کلاینت هوش مصنوعی جمینای
client = genai.Client(api_key=GEMINI_API_KEY)

WORDS_FILE = "words.json"


def load_words():
    if os.path.exists(WORDS_FILE):
        with open(WORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_words(words):
    with open(WORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=4)


def get_smart_distractors(target_word: str, correct_meaning: str):
    """تولید ۳ گزینه اشتباه ولی منطقی با استفاده از جمینای"""
    prompt = f"""
    برای کلمه انگلیسی "{target_word}" که ترجمه درست آن به فارسی "{correct_meaning}" است:
    دقیقا ۳ گزینه اشتباه ولی منطقی و مرتبط به زبان فارسی تولید کن که به عنوان گزینه‌های انحرافی در آزمون ۴ گزینه‌ای استفاده شوند.
    پاسخ تو فقط و فقط باید ۳ کلمه یا عبارت فارسی باشد که با ویرگول انگلیسی (,) از هم جدا شده‌اند، بدون هیچ متن اضافی.
    مثال خروجی:
    گزینه اول, گزینه دوم, گزینه سوم
    """
    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        distractors = [w.strip()
                       for w in response.text.strip().split(',') if w.strip()]
        if len(distractors) >= 3:
            return distractors[:3]
    except Exception as e:
        print(f"Error calling Gemini: {e}")

    # اگر هوش مصنوعی در دسترس نبود، از گزینه‌های پیش‌فرض استفاده می‌شود
    return ["گزینه فرعی ۱", "گزینه فرعی ۲", "گزینه فرعی ۳"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "سلام امیر عزیز! خوش اومدی به ربات جعبه لایتنر هوشمند.\n\n"
        "دستورات ربات:\n"
        "➕ اضافه کردن لغت:\n"
        "`/add word - معنی فارسی`\n\n"
        "📝 شروع کوییز هوشمند:\n"
        "`/quiz`\n\n"
        "📊 وضعیت لغات:\n"
        "`/status`\n\n"
        "🗑 حذف لغت:\n"
        "`/remove word`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def add_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if "-" not in text:
        await update.message.reply_text("فرمت اشتباه است! لطفا اینطور وارد کن:\n`/add apple - سیب`", parse_mode="Markdown")
        return

    word, meaning = text.split("-", 1)
    word = word.strip().lower()
    meaning = meaning.strip()

    words = load_words()
    words[word] = {
        "meaning": meaning,
        "level": 1,
        "correct_count": 0
    }
    save_words(words)

    await update.message.reply_text(f"✅ لغت *{word}* با معنی «{meaning}» به لول ۱ اضافه شد!", parse_mode="Markdown")


async def remove_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("لطفا کلمه را وارد کن:\n`/remove word`", parse_mode="Markdown")
        return

    word = context.args[0].strip().lower()
    words = load_words()

    if word in words:
        del words[word]
        save_words(words)
        await update.message.reply_text(f"🗑 کلمه *{word}* با موفقیت حذف شد.", parse_mode="Markdown")
    else:
        await update.message.reply_text("این کلمه در دیتابیس وجود ندارد.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words = load_words()
    if not words:
        await update.message.reply_text("هنوز هیچ لغتی اضافه نکردی!")
        return

    levels = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for data in words.values():
        lvl = data.get("level", 1)
        levels[lvl] = levels.get(lvl, 0) + 1

    report = "📊 *وضعیت جعبه لایتنر شما:*\n\n"
    for lvl, count in levels.items():
        report += f"🔹 جعبه {lvl}: {count} لغت\n"
    report += f"\nمجموع کل لغات: {len(words)}"

    await update.message.reply_text(report, parse_mode="Markdown")


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words = load_words()
    if not words:
        await update.message.reply_text("ابتدا با دستور `/add` چند لغت اضافه کن!", parse_mode="Markdown")
        return

    # اولویت پرسیدن لغات با سطوح پایین‌تر
    candidates = []
    for w, data in words.items():
        weight = 6 - data.get("level", 1)
        candidates.extend([w] * weight)

    target_word = random.choice(candidates)
    correct_meaning = words[target_word]["meaning"]

    # ارسال پیام موقت در حین ساخت گزینه‌ها با جمینای
    wait_msg = await update.message.reply_text("🧠 در حال تولید گزینه‌های هوشمند با جمینای...")

    # دریافت گزینه‌های انحرافی هوشمند
    distractors = get_smart_distractors(target_word, correct_meaning)
    options = [correct_meaning] + distractors
    random.shuffle(options)

    keyboard = []
    for opt in options:
        is_correct = "1" if opt == correct_meaning else "0"
        callback_data = f"q:{target_word}:{is_correct}"
        keyboard.append([InlineKeyboardButton(
            opt, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await wait_msg.delete()
    await update.message.reply_text(
        f"معنی لغت *{target_word}* چیست؟",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data_parts = query.data.split(":")
    target_word = data_parts[1]
    is_correct = data_parts[2] == "1"

    words = load_words()
    if target_word not in words:
        await query.edit_message_text("این لغت دیگر در سیستم موجود نیست.")
        return

    current_level = words[target_word].get("level", 1)
    correct_meaning = words[target_word]["meaning"]

    if is_correct:
        new_level = min(5, current_level + 1)
        words[target_word]["level"] = new_level
        words[target_word]["correct_count"] = words[target_word].get(
            "correct_count", 0) + 1
        save_words(words)

        res_text = (
            f"✅ *کاملاً درسته!*\n\n"
            f"کلمه: *{target_word}*\n"
            f"معنی: {correct_meaning}\n"
            f"📈 پیشرفت: لول {current_level} ⬅️ لول {new_level}\n\n"
            f"برای ادامه: /quiz"
        )
    else:
        words[target_word]["level"] = 1
        save_words(words)

        res_text = (
            f"❌ *اشتباه پاسخ دادی!*\n\n"
            f"کلمه: *{target_word}*\n"
            f"معنی صحیح: *{correct_meaning}*\n"
            f"📉 کلمه به لول ۱ بازگشت تا بیشتر مرور شود.\n\n"
            f"برای ادامه: /quiz"
        )

    await query.edit_message_text(res_text, parse_mode="Markdown")


def main():
    if not BOT_TOKEN or not GEMINI_API_KEY:
        print("خطا: توکن تلگرام یا کلید جمینای در فایل .env تنظیم نشده است!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_word))
    app.add_handler(CommandHandler("remove", remove_word))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^q:"))

    print("ربات با هوش مصنوعی جمینای راه‌اندازی شد و در حال گوش دادن به پیام‌ها است...")
    app.run_polling()


if __name__ == "__main__":
    main()
