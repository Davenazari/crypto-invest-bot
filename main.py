from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler

LANGUAGE, AMOUNT = range(2)

langs = {
    "فارسی": "fa",
    "English": "en"
}

messages = {
    "fa": {
        "start": "سلام! زبان مورد نظر را انتخاب کن:",
        "ask_amount": "لطفا مقدار سرمایه‌گذاری را وارد کن (مثلا 100 تتر):",
        "result": lambda amount: (
            f"💵 با سرمایه‌گذاری {amount} تتر:\n"
            f"📆 سود روزانه: {round(amount * 0.5 / 30, 2)} تتر → مجموع: {round(amount + amount * 0.5 / 30, 2)} تتر\n"
            f"📅 سود هفتگی: {round(amount * 0.5 / 4, 2)} تتر → مجموع: {round(amount + amount * 0.5 / 4, 2)} تتر\n"
            f"🗓️ سود ماهانه: {round(amount * 0.5, 2)} تتر → مجموع: {round(amount + amount * 0.5, 2)} تتر 💰"
        ),
        "deposit": "💸 واریز USDT",
        "choose_network": "📲 لطفا شبکه مورد نظر را انتخاب کن:",
        "wallet": lambda network, address: f"✅ آدرس کیف پول برای {network}:\n`{address}`"
    },
    "en": {
        "start": "Hello! Please choose your language:",
        "ask_amount": "Please enter the investment amount (e.g. 100 USDT):",
        "result": lambda amount: (
            f"💵 If you invest {amount} USDT:\n"
            f"📆 Daily profit: {round(amount * 0.5 / 30, 2)} USDT → Total: {round(amount + amount * 0.5 / 30, 2)} USDT\n"
            f"📅 Weekly profit: {round(amount * 0.5 / 4, 2)} USDT → Total: {round(amount + amount * 0.5 / 4, 2)} USDT\n"
            f"🗓️ Monthly profit: {round(amount * 0.5, 2)} USDT → Total: {round(amount + amount * 0.5, 2)} USDT 💰"
        ),
        "deposit": "💸 Deposit USDT",
        "choose_network": "📲 Please choose the network:",
        "wallet": lambda network, address: f"✅ Wallet address for {network}:\n`{address}`"
    }
}

wallet_addresses = {
    "TRC20": "TXExampleTRC20Wallet123",
    "BEP20": "0xExampleBEP20Wallet456"
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

    deposit_button = [[InlineKeyboardButton(messages[lang]["deposit"], callback_data="deposit")]]
    await update.message.reply_text("👇", reply_markup=InlineKeyboardMarkup(deposit_button))

    return ConversationHandler.END

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = user_lang.get(query.from_user.id, "en")

    if query.data == "deposit":
        buttons = [
            [InlineKeyboardButton("TRC20", callback_data="TRC20")],
            [InlineKeyboardButton("BEP20", callback_data="BEP20")]
        ]
        await query.message.reply_text(messages[lang]["choose_network"], reply_markup=InlineKeyboardMarkup(buttons))

    elif query.data in ["TRC20", "BEP20"]:
        address = wallet_addresses[query.data]
        await query.message.reply_text(
            messages[lang]["wallet"](query.data, address),
            parse_mode="Markdown"
        )

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

    # هندلر اضافه برای تشخیص زبان هر وقت فرستاده شد
    lang_keys = list(langs.keys())
    
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()
