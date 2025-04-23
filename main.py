import logging
import os
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler

# تنظیم لاگ‌گیری
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

LANGUAGE, AMOUNT, DEPOSIT, TXID = range(4)

langs = {
    "فارسی": "fa",
    "English": "en"
}

messages = {
    "fa": {
        "start": (
            "🌟 *خوش آمدید!*\n"
            "لطفاً *زبان* مورد نظر خود را انتخاب کنید:\n"
            "👇 یکی از گزینه‌های زیر را انتخاب کنید 👇"
        ),
        "ask_amount": (
            "💰 *مقدار سرمایه‌گذاری*\n"
            "لطفاً مقدار سرمایه‌گذاری خود را به *تتر (USDT)* وارد کنید (مثال: 100):\n"
            "📌 عدد معتبر وارد کنید."
        ),
        "result": lambda amount: (
            f"💵 *سرمایه‌گذاری شما: {amount} تتر*\n"
            f"────────────────────\n"
            f"📆 *سود روزانه*: `{round(amount * 0.5 / 30, 2)}` تتر → *مجموع*: `{round(amount + amount * 0.5 / 30, 2)}` تتر\n"
            f"📅 *سود هفتگی*: `{round(amount * 0.5 / 4, 2)}` تتر → *مجموع*: `{round(amount + amount * 0.5 / 4, 2)}` تتر\n"
            f"🗓️ *سود ماهانه*: `{round(amount * 0.5, 2)}` تتر → *مجموع*: `{round(amount + amount * 0.5, 2)}` تتر\n"
            f"────────────────────\n"
            f"💸 آماده واریز هستید؟"
        ),
        "deposit": "💸 *واریز USDT*",
        "choose_network": (
            "📲 *انتخاب شبکه*\n"
            "لطفاً شبکه مورد نظر برای واریز را انتخاب کنید:\n"
            "👇 یکی از گزینه‌های زیر را انتخاب کنید 👇"
        ),
        "wallet": lambda network, address: (
            f"✅ *آدرس کیف پول {network}*\n"
            f"لطفاً واریز را به این آدرس انجام دهید:\n"
            f"📋 `{address}`\n"
            f"⚠️ *توجه*: فقط از شبکه *{network}* استفاده کنید!"
        ),
        "ask_txid": (
            "📝 *ارسال TXID یا اسکرین‌شات*\n"
            "لطفاً *TXID* تراکنش یا *اسکرین‌شات* واریز خود را ارسال کنید:\n"
            "📌 TXID را کپی کنید یا تصویر واضحی ارسال کنید."
        ),
        "invalid_language": "⚠️ *خطا*: زبان انتخاب‌شده معتبر نیست!\nلطفاً یکی از زبان‌های موجود را انتخاب کنید.",
        "invalid_amount": "⚠️ *خطا*: مقدار واردشده معتبر نیست!\nلطفاً یک عدد معتبر (مثل 100) وارد کنید.",
        "success": (
            "🎉 *واریز ثبت شد!*\n"
            "تراکنش شما با موفقیت ثبت شد.\n"
            "⏳ لطفاً منتظر تأیید توسط تیم ما باشید."
        ),
        "error": (
            "❌ *خطا رخ داد!*\n"
            "مشکلی در ثبت تراکنش پیش آمد.\n"
            "🔄 لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
        ),
        "cancel": "🛑 *عملیات لغو شد*\nبرای شروع مجدد، دستور /start را وارد کنید."
    },
    "en": {
        "start": (
            "🌟 *Welcome!*\n"
            "Please select your preferred *language*:\n"
            "👇 Choose one of the options below 👇"
        ),
        "ask_amount": (
            "💰 *Investment Amount*\n"
            "Please enter your investment amount in *USDT* (e.g., 100):\n"
            "📌 Enter a valid number."
        ),
        "result": lambda amount: (
            f"💵 *Your Investment: {amount} USDT*\n"
            f"────────────────────\n"
            f"📆 *Daily Profit*: `{round(amount * 0.5 / 30, 2)}` USDT → *Total*: `{round(amount + amount * 0.5 / 30, 2)}` USDT\n"
            f"📅 *Weekly Profit*: `{round(amount * 0.5 / 4, 2)}` USDT → *Total*: `{round(amount + amount * 0.5 / 4, 2)}` USDT\n"
            f"🗓️ *Monthly Profit*: `{round(amount * 0.5, 2)}` USDT → *Total*: `{round(amount + amount * 0.5, 2)}` USDT\n"
            f"────────────────────\n"
            f"💸 Ready to deposit?"
        ),
        "deposit": "💸 *Deposit USDT*",
        "choose_network": (
            "📲 *Select Network*\n"
            "Please choose the network for your deposit:\n"
            "👇 Choose one of the options below 👇"
        ),
        "wallet": lambda network, address: (
            f"✅ *{network} Wallet Address*\n"
            "Please send your deposit to this address:\n"
            f"📋 `{address}`\n"
            f"⚠️ *Note*: Only use the *{network}* network!"
        ),
        "ask_txid": (
            "📝 *Send TXID or Screenshot*\n"
            "Please send the *TXID* of your transaction or a *screenshot* of the deposit:\n"
            "📌 Copy the TXID or send a clear image."
        ),
        "invalid_language": "⚠️ *Error*: Selected language is invalid!\nPlease choose one of the available languages.",
        "invalid_amount": "⚠️ *Error*: Invalid amount entered!\nPlease enter a valid number (e.g., 100).",
        "success": (
            "🎉 *Deposit Recorded!*\n"
            "Your transaction has been successfully recorded.\n"
            "⏳ Please wait for confirmation from our team."
        ),
        "error": (
            "❌ *Error Occurred!*\n"
            "There was an issue processing your transaction.\n"
            "🔄 Please try again or contact support."
        ),
        "cancel": "🛑 *Operation Cancelled*\nTo start over, use the /start command."
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
        messages["fa" if update.effective_user.language_code == "fa" else "en"]["start"],
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return LANGUAGE

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang_name = update.message.text
    if lang_name not in langs:
        await update.message.reply_text(
            messages["fa" if update.effective_user.language_code == "fa" else "en"]["invalid_language"],
            parse_mode="Markdown"
        )
        return LANGUAGE

    lang = langs[lang_name]
    user_lang[update.effective_user.id] = lang
    await update.message.reply_text(
        messages[lang]["ask_amount"],
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_start")]
        ])
    )
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = user_lang.get(update.effective_user.id, "en")
    try:
        amount = float(update.message.text)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except ValueError:
        await update.message.reply_text(
            messages[lang]["invalid_amount"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_start")]
            ])
        )
        return AMOUNT

    await update.message.reply_text(
        messages[lang]["result"](amount),
        parse_mode="Markdown"
    )

    deposit_button = [[InlineKeyboardButton(messages[lang]["deposit"], callback_data="deposit")]]
    await update.message.reply_text(
        "👇 *اقدام بعدی* 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(deposit_button)
    )

    return DEPOSIT

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = user_lang.get(query.from_user.id, "en")

    if query.data == "back_to_start":
        kb = [[k] for k in langs.keys()]
        await query.message.reply_text(
            messages[lang]["start"],
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
        )
        return LANGUAGE

    if query.data == "deposit":
        buttons = [
            [InlineKeyboardButton("TRC20", callback_data="TRC20")],
            [InlineKeyboardButton("BEP20", callback_data="BEP20")],
            [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_amount")]
        ]
        await query.message.reply_text(
            messages[lang]["choose_network"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return DEPOSIT

    elif query.data == "back_to_amount":
        await query.message.reply_text(
            messages[lang]["ask_amount"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_start")]
            ])
        )
        return AMOUNT

    elif query.data in ["TRC20", "BEP20"]:
        address = wallet_addresses[query.data]
        await query.message.reply_text(
            messages[lang]["wallet"](query.data, address),
            parse_mode="Markdown"
        )
        await query.message.reply_text(
            messages[lang]["ask_txid"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_deposit")]
            ])
        )
        return TXID

    elif query.data == "back_to_deposit":
        buttons = [
            [InlineKeyboardButton("TRC20", callback_data="TRC20")],
            [InlineKeyboardButton("BEP20", callback_data="BEP20")],
            [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_amount")]
        ]
        await query.message.reply_text(
            messages[lang]["choose_network"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return DEPOSIT

async def receive_txid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = user_lang.get(update.effective_user.id, "en")
    admin_id = int(os.getenv("ADMIN_ID", "536587863"))  # آیدی ادمین از متغیر محیطی

    try:
        # فوروارد کردن پیام کاربر (متن، عکس یا هر نوع پیام دیگر) به ادمین
        await context.bot.forward_message(
            chat_id=admin_id,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )

        # ارسال اطلاعات اضافی به ادمین
        await context.bot.send_message(
            chat_id=admin_id,
            text=(
                f"📝 *کاربر*: {update.effective_user.first_name} ({update.effective_user.id})\n"
                f"🌐 *زبان*: {lang}\n"
                f"⏰ *زمان*: {update.message.date}"
            ),
            parse_mode="Markdown"
        )

        # پاسخ به کاربر
        await update.message.reply_text(
            messages[lang]["success"],
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error forwarding message to admin: {e}")
        await update.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown"
        )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = user_lang.get(update.effective_user.id, "en") or "en"
    await update.message.reply_text(
        messages[lang]["cancel"],
        parse_mode="Markdown"
    )
    return ConversationHandler.END

if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        logger.error("BOT_TOKEN not found in environment variables")
        exit(1)

    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_language)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            DEPOSIT: [CallbackQueryHandler(handle_callback)],
            TXID: [
                MessageHandler(filters.ALL & ~filters.COMMAND, receive_txid),
                CallbackQueryHandler(handle_callback)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app.add_handler(conv)
    logger.info("🚀 Starting bot polling...")
    app.run_polling()
