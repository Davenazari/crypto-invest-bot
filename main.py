from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

LANGUAGE, AMOUNT = range(2)

langs = {
    "فارسی": "fa",
    "English": "en"
}

messages = {
    "fa": {
        "start": "سلام! زبان مورد نظر را انتخاب کن:",
        "ask_amount": "لطفا مقدار سرمایه‌گذاری را وارد کن (مثلا 100 تتر):",
        "result": lambda amount: f"اگر {amount} تتر سرمایه‌گذاری کنی، سود ماهانه‌ات میشه {round(amount * 0.1, 2)} تتر 💰"
    },
    "en": {
        "start": "Hello! Please choose your language:",
        "ask_amount": "Please enter the investment amount (e.g. 100 USDT):",
        "result": lambda amount: f"If you invest {amount} USDT, your monthly profit will be {round(amount * 0.1, 2)} USDT 💰"
    }
}

user_lang = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[k] for k in langs.keys()]
    await update.message.reply_text(
        "Select language / زبان را انتخاب کن:",
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return LANGUAGE

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang_name = update.message.text
    if lang_name not in langs:
        await update.message.reply_text("زبان معتبر نیست / Invalid language")
        return LANGUAGE

    lang = langs[lang_name]
    user_lang[update.effective_user.id] = lang
    await update.message.reply_text(messages[lang]["ask_amount"])
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = user_lang.get(update.effective_user.id, "en")
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("عدد نامعتبر / Invalid number")
        return AMOUNT

    await update.message.reply_text(messages[lang]["result"](amount))
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لغو شد / Cancelled")
    return ConversationHandler.END

if __name__ == '__main__':
    import os
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_language)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app.add_handler(conv)
    app.run_polling()
