import logging
import os
import psycopg2
from datetime import datetime
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
        "cancel": "🛑 *عملیات لغو شد*\nبرای شروع مجدد، دستور /start را وارد کنید.",
        "confirmed": (
            "✅ *تراکنش تأیید شد!*\n"
            "واریز شما با موفقیت تأیید شد.\n"
            "📈 سرمایه‌گذاری شما اکنون فعال است!"
        ),
        "rejected": (
            "❌ *تراکنش رد شد!*\n"
            "واریز شما تأیید نشد.\n"
            "📩 لطفاً با پشتیبانی تماس بگیرید."
        ),
        "wallet_balance": lambda balance: (
            f"💼 *موجودی کیف پول شما*\n"
            f"────────────────────\n"
            f"💰 *مقدار*: `{balance}` تتر\n"
            f"────────────────────\n"
            f"📌 برای افزایش موجودی، از /start استفاده کنید."
        ),
        "wallet_empty": (
            "💼 *کیف پول خالی است!*\n"
            "هنوز هیچ واریزی تأیید نشده است.\n"
            "📌 برای واریز، از /start استفاده کنید."
        ),
        "history": lambda transactions: (
            f"📜 *تاریخچه تراکنش‌ها*\n"
            f"────────────────────\n"
            f"{transactions}\n"
            f"────────────────────\n"
            f"📌 برای واریز جدید، از /start استفاده کنید."
        ),
        "no_history": (
            "📜 *بدون تاریخچه تراکنش*\n"
            "هنوز هیچ تراکنشی ثبت نشده است.\n"
            "📌 برای واریز، از /start استفاده کنید."
        ),
        "unauthorized": (
            "🚫 *خطا*: شما اجازه دسترسی به این دستور را ندارید!\n"
            "📩 لطفاً با ادمین تماس بگیرید."
        )
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
        "cancel": "🛑 *Operation Cancelled*\nTo start over, use the /start command.",
        "confirmed": (
            "✅ *Transaction Confirmed!*\n"
            "Your deposit has been successfully confirmed.\n"
            "📈 Your investment is now active!"
        ),
        "rejected": (
            "❌ *Transaction Rejected!*\n"
            "Your deposit was not approved.\n"
            "📩 Please contact support for more details."
        ),
        "wallet_balance": lambda balance: (
            f"💼 *Your Wallet Balance*\n"
            f"────────────────────\n"
            f"💰 *Amount*: `{balance}` USDT\n"
            f"────────────────────\n"
            f"📌 To increase your balance, use /start."
        ),
        "wallet_empty": (
            "💼 *Wallet is Empty!*\n"
            "No deposits have been confirmed yet.\n"
            "📌 To deposit, use /start."
        ),
        "history": lambda transactions: (
            f"📜 *Transaction History*\n"
            f"────────────────────\n"
            f"{transactions}\n"
            f"────────────────────\n"
            f"📌 For a new deposit, use /start."
        ),
        "no_history": (
            "📜 *No Transaction History*\n"
            "No transactions have been recorded yet.\n"
            "📌 To deposit, use /start."
        ),
        "unauthorized": (
            "🚫 *Error*: You are not authorized to access this command!\n"
            "📩 Please contact the admin."
        )
    }
}

wallet_addresses = {
    "TRC20": "TXExampleTRC20Wallet123",
    "BEP20": "0xExampleBEP20Wallet456"
}

# توابع مدیریت دیتابیس
DATABASE_URL = os.getenv("DATABASE_URL")

def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        # ایجاد جدول کاربران
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                language TEXT DEFAULT 'en',
                balance REAL DEFAULT 0.0
            )
        ''')
        # ایجاد جدول تراکنش‌ها
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount REAL,
                network TEXT,
                status TEXT,
                created_at TEXT,
                message_id BIGINT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        conn.commit()
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise
    finally:
        conn.close()

def get_user(user_id):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute('SELECT language, balance FROM users WHERE user_id = %s', (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def upsert_user(user_id, language='en', balance=0.0):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute('''
        INSERT INTO users (user_id, language, balance)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET language = %s, balance = %s
    ''', (user_id, language, balance, language, balance))
    conn.commit()
    conn.close()

def update_balance(user_id, amount):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute('UPDATE users SET balance = balance + %s WHERE user_id = %s', (amount, user_id))
    conn.commit()
    conn.close()

def insert_transaction(user_id, amount, network, status, message_id):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    created_at = datetime.utcnow().isoformat()
    c.execute('''
        INSERT INTO transactions (user_id, amount, network, status, created_at, message_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (user_id, amount, network, status, created_at, message_id))
    conn.commit()
    conn.close()

def update_transaction_status(transaction_id, user_id, message_id, status):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute('''
        UPDATE transactions
        SET status = %s
        WHERE user_id = %s AND message_id = %s AND status = 'pending'
    ''', (status, user_id, message_id))
    conn.commit()
    conn.close()

def get_transaction(user_id, message_id):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute('''
        SELECT amount, network, status
        FROM transactions
        WHERE user_id = %s AND message_id = %s AND status = 'pending'
    ''', (user_id, message_id))
    transaction = c.fetchone()
    conn.close()
    return transaction

def get_transaction_history(user_id):
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    c.execute('''
        SELECT amount, network, status, created_at
        FROM transactions
        WHERE user_id = %s
        ORDER BY created_at DESC
    ''', (user_id,))
    transactions = c.fetchall()
    conn.close()
    return transactions

# مقداردهی اولیه دیتابیس
try:
    init_db()
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    exit(1)

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
    user_id = update.effective_user.id
    upsert_user(user_id, language=lang)
    await update.message.reply_text(
        messages[lang]["ask_amount"],
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_start")]
        ])
    )
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"

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

    # ذخیره مقدار سرمایه‌گذاری
    context.user_data["amount"] = amount

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
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"

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
        # ذخیره شبکه انتخاب‌شده
        context.user_data["network"] = query.data
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

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = int(os.getenv("ADMIN_ID", "536587863"))

    logger.info(f"Received callback: {query.data} from user: {query.from_user.id}")

    if query.data.startswith("confirm_") or query.data.startswith("reject_"):
        # فقط ادمین می‌تواند تأیید یا رد کند
        if query.from_user.id != admin_id:
            user = get_user(query.from_user.id)
            lang = user[0] if user else "en"
            await query.message.reply_text(
                messages[lang]["unauthorized"],
                parse_mode="Markdown"
            )
            return

        try:
            action, user_id, message_id = query.data.split("_")
            user_id = int(user_id)
            message_id = int(message_id)
        except ValueError as e:
            logger.error(f"Error parsing callback_data: {query.data}, error: {e}")
            await query.message.reply_text(
                "⚠️ *خطا*: فرمت داده نامعتبر است!" if lang == "fa" else
                "⚠️ *Error*: Invalid data format!",
                parse_mode="Markdown"
            )
            return

        # بررسی وجود تراکنش
        transaction = gett_transaction(user_id, message_id)
        if not transaction:
            await query.message.reply_text(
                "⚠️ *خطا*: این تراکنش دیگر معتبر نیست!" if lang == "fa" else
                "⚠️ *Error*: This transaction is no longer valid!",
                parse_mode="Markdown"
            )
            return

        # دریافت اطلاعات تراکنش
        amount, network, status = transaction
        user = get_user(user_id)
        user_lang_id = user[0] if user else "en"

        try:
            if action == "confirm":
                # به‌روزرسانی موجودی کاربر
                update_balance(user_id, amount)
                # به‌روزرسانی وضعیت تراکنش
                update_transaction_status(None, user_id, message_id, "confirmed")
                # دریافت موجودی جدید
                user = get_user(user_id)
                balance = user[1] if user else 0
                # اطلاع‌رسانی به کاربر
                await context.bot.send_message(
                    chat_id=user_id,
                    text=messages[user_lang_id]["confirmed"],
                    parse_mode="Markdown"
                )
                # اطلاع‌رسانی به ادمین
                await query.message.reply_text(
                    f"✅ *تراکنش تأیید شد!*\nکاربر: {user_id}\nمقدار: {amount} تتر\nشبکه: {network}\nموجودی جدید: {balance} تتر",
                    parse_mode="Markdown"
                )
            else:  # reject
                # به‌روزرسانی وضعیت تراکنش
                update_transaction_status(None, user_id, message_id, "rejected")
                # اطلاع‌رسانی به کاربر
                await context.bot.send_message(
                    chat_id=user_id,
                    text=messages[user_lang_id]["rejected"],
                    parse_mode="Markdown"
                )
                # اطلاع‌رسانی به ادمین
                await query.message.reply_text(
                    f"❌ *تراکنش رد شد!*\nکاربر: {user_id}\nمقدار: {amount} تتر\nشبکه: {network}",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            await query.message.reply_text(
                "❌ *خطا*: مشکلی در پردازش درخواست رخ داد!" if lang == "fa" else
                "❌ *Error*: An issue occurred while processing the request!",
                parse_mode="Markdown"
            )

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_id = int(os.getenv("ADMIN_ID", "536587863"))
    user = get_user(user_id)
    lang = user[0] if user else "en"

    # بررسی دسترسی ادمین
    if user_id != admin_id:
        await update.message.reply_text(
            messages[lang]["unauthorized"],
            parse_mode="Markdown"
        )
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        user_count = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM transactions')
        transaction_count = c.fetchone()[0]
        conn.close()
        await update.message.reply_text(
            f"🛠 *وضعیت دیتابیس*\n"
            f"────────────────────\n"
            f"👤 *تعداد کاربران*: {user_count}\n"
            f"📝 *تعداد تراکنش‌ها*: {transaction_count}\n"
            f"────────────────────" if lang == "fa" else
            f"🛠 *Database Status*\n"
            f"────────────────────\n"
            f"👤 *Number of Users*: {user_count}\n"
            f"📝 *Number of Transactions*: {transaction_count}\n"
            f"────────────────────",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error accessing database: {e}")
        await update.message.reply_text(
            "❌ *خطا*: مشکلی در دسترسی به دیتابیس رخ داد!" if lang == "fa" else
            "❌ *Error*: An issue occurred while accessing the database!",
            parse_mode="Markdown"
        )

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    balance = user[1] if user else 0

    if balance == 0:
        await update.message.reply_text(
            messages[lang]["wallet_empty"],
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            messages[lang]["wallet_balance"](balance),
            parse_mode="Markdown"
        )

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"

    transactions = get_transaction_history(user_id)
    if not transactions:
        await update.message.reply_text(
            messages[lang]["no_history"],
            parse_mode="Markdown"
        )
        return

    # فرمت‌بندی تاریخچه تراکنش‌ها
    transaction_text = ""
    status_map = {
        "pending": ("⏳ در انتظار", "⏳ Pending"),
        "confirmed": ("✅ تأییدشده", "✅ Confirmed"),
        "rejected": ("❌ ردشده", "❌ Rejected")
    }
    for amount, network, status, created_at in transactions:
        status_text = status_map[status][0] if lang == "fa" else status_map[status][1]
        transaction_text += (
            f"💰 *مقدار*: `{amount}` تتر\n"
            f"📲 *شبکه*: {network}\n"
            f"📅 *وضعیت*: {status_text}\n"
            f"⏰ *زمان*: {created_at}\n"
            f"────────────────────\n"
        ) if lang == "fa" else (
            f"💰 *Amount*: `{amount}` USDT\n"
            f"📲 *Network*: {network}\n"
            f"📅 *Status*: {status_text}\n"
            f"⏰ *Time*: {created_at}\n"
            f"────────────────────\n"
        )

    await update.message.reply_text(
        messages[lang]["history"](transaction_text),
        parse_mode="Markdown"
    )

async def receive_txid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    admin_id = int(os.getenv("ADMIN_ID", "536587863"))
    message_id = update.message.message_id

    try:
        # فوروارد کردن پیام کاربر به ادمین
        await context.bot.forward_message(
            chat_id=admin_id,
            from_chat_id=update.effective_chat.id,
            message_id=message_id
        )

        # ذخیره اطلاعات تراکنش
        amount = context.user_data.get("amount", 0)
        network = context.user_data.get("network", "Unknown")
        insert_transaction(user_id, amount, network, "pending", message_id)

        # ارسال اطلاعات اضافی و دکمه‌های تأیید/رد به ادمین
        await context.bot.send_message(
            chat_id=admin_id,
            text=(
                f"📝 *تراکنش جدید*\n"
                f"────────────────────\n"
                f"👤 *کاربر*: {update.effective_user.first_name} ({user_id})\n"
                f"🌐 *زبان*: {lang}\n"
                f"💰 *مقدار*: {amount} تتر\n"
                f"📲 *شبکه*: {network}\n"
                f"⏰ *زمان*: {update.message.date}\n"
                f"────────────────────\n"
                f"✅ لطفاً وضعیت تراکنش را مشخص کنید:"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ تأیید", callback_data=f"confirm_{user_id}_{message_id}"),
                    InlineKeyboardButton("❌ رد", callback_data=f"reject_{user_id}_{message_id}")
                ]
            ])
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
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
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

    # اضافه کردن Handler‌ها
    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^(confirm_|reject_)"))
    app.add_handler(CommandHandler("wallet", wallet))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(conv)

    logger.info("🚀 Starting bot polling...")
    app.run_polling()
