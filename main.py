import logging
import os
import psycopg2
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
import telegram.error

# تنظیم لاگ‌گیری
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# تعریف مراحل برای ConversationHandler
DEPOSIT_AMOUNT, DEPOSIT_NETWORK, DEPOSIT_TXID, WITHDRAW_AMOUNT, WITHDRAW_ADDRESS = range(5)

# تنظیم پیش‌فرض ADMIN_ID
DEFAULT_ADMIN_ID = "536587863"

langs = {
    "فارسی": "fa",
    "English": "en"
}

messages = {
    "fa": {
        "welcome": (
            "🌟 *خوش آمدید به بات سرمایه‌گذاری!*\n"
            "با این بات می‌توانید با واریز USDT سرمایه‌گذاری کنید، موجودی کیف پول خود را مشاهده کنید و سود روزانه، هفتگی یا ماهانه کسب کنید. برای کمک با پشتیبانی تماس بگیرید!\n"
            "👇 گزینه مورد نظر خود را انتخاب کنید 👇"
        ),
        "main_menu": "📋 *منوی اصلی*\nلطفاً یک گزینه را انتخاب کنید:",
        "deposit": "💸 *واریز USDT*",
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
        "invalid_amount": "⚠️ *خطا*: مقدار واردشده معتبر نیست!\nلطفاً یک عدد معتبر (مثل 100) وارد کنید.",
        "success": (
            "🎉 *واریز ثبت شد!*\n"
            "تراکنش شما با موفقیت ثبت شد.\n"
            "⏳ لطفاً منتظر تأیید توسط تیم ما باشید."
        ),
        "error": (
            "❌ *خطا رخ داد!*\n"
            "مشکلی در ثبت درخواست پیش آمد.\n"
            "🔄 لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
        ),
        "db_error": (
            "❌ *خطای دیتابیس!*\n"
            "مشکلی در ثبت تراکنش رخ داد.\n"
            "📩 لطفاً با پشتیبانی تماس بگیرید."
        ),
        "admin_error": (
            "❌ *خطای ارتباط با ادمین!*\n"
            "نمی‌توان درخواست را به ادمین ارسال کرد.\n"
            "📩 لطفاً با پشتیبانی تماس بگیرید."
        ),
        "cancel": "🛑 *عملیات لغو شد*\nبرای بازگشت به منوی اصلی، /start را وارد کنید.",
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
        "wallet_menu": "💼 *ولت من*\nلطفاً یک گزینه را انتخاب کنید:",
        "wallet_balance": lambda balance: (
            f"💼 *موجودی کیف پول شما*\n"
            f"────────────────────\n"
            f"💰 *مقدار*: `{balance}` تتر\n"
            f"────────────────────\n"
            f"📌 برای واریز یا برداشت، گزینه‌های زیر را انتخاب کنید."
        ),
        "wallet_empty": (
            "💼 *کیف پول خالی است!*\n"
            "هنوز هیچ واریزی تأیید نشده است.\n"
            "📌 برای واریز، از منوی اصلی گزینه واریز را انتخاب کنید."
        ),
        "withdraw": "💸 *برداشت*",
        "ask_withdraw_amount": (
            "💰 *مقدار برداشت*\n"
            "لطفاً مقدار تتر (USDT) مورد نظر برای برداشت را وارد کنید:\n"
            "📌 مقدار باید کمتر یا برابر با موجودی شما باشد."
        ),
        "insufficient_balance": (
            "⚠️ *خطا*: موجودی کافی نیست!\n"
            "لطفاً مقداری کمتر یا برابر با موجودی خود وارد کنید."
        ),
        "ask_withdraw_address": (
            "📋 *آدرس کیف پول*\n"
            "لطفاً آدرس کیف پول USDT خود را برای برداشت وارد کنید:\n"
            "📌 آدرس را با دقت وارد کنید."
        ),
        "withdraw_success": (
            "🎉 *درخواست برداشت ثبت شد!*\n"
            "درخواست شما با موفقیت ثبت شد.\n"
            "⏳ لطفاً منتظر تأیید توسط تیم ما باشید."
        ),
        "withdraw_confirmed": (
            "✅ *برداشت تأیید شد!*\n"
            "درخواست برداشت شما با موفقیت تأیید شد.\n"
            "📤 وجه به زودی به کیف پول شما ارسال می‌شود!"
        ),
        "withdraw_rejected": (
            "❌ *برداشت رد شد!*\n"
            "درخواست برداشت شما تأیید نشد.\n"
            "📩 لطفاً با پشتیبانی تماس بگیرید."
        ),
        "language_menu": (
            "🌐 *انتخاب زبان*\n"
            "لطفاً زبان مورد نظر خود را انتخاب کنید:\n"
            "👇 یکی از گزینه‌های زیر را انتخاب کنید 👇"
        ),
        "language_updated": (
            "✅ *زبان به‌روزرسانی شد!*\n"
            "اکنون از منوی اصلی می‌توانید ادامه دهید."
        ),
        "support": (
            "📩 *پشتیبانی*\n"
            "برای دریافت کمک، با پشتیبانی ما تماس بگیرید:\n"
            "👤 @farzadnazari"
        ),
        "history": lambda transactions: (
            f"📜 *تاریخچه تراکنش‌ها*\n"
            f"────────────────────\n"
            f"{transactions}\n"
            f"────────────────────\n"
            f"📌 برای واریز یا برداشت جدید، به منوی اصلی بروید."
        ),
        "no_history": (
            "📜 *بدون تاریخچه تراکنش*\n"
            "هنوز هیچ تراکنشی ثبت نشده است.\n"
            "📌 برای واریز، به منوی اصلی بروید."
        ),
        "unauthorized": (
            "🚫 *خطا*: شما اجازه دسترسی به این دستور را ندارید!\n"
            "📩 لطفاً با پشتیبانی تماس بگیرید."
        ),
        "unexpected_message": (
            "⚠️ *پیام نامعتبر*\n"
            "لطفاً از دکمه‌های منو استفاده کنید یا مقدار معتبری وارد کنید.\n"
            "برای بازگشت به منوی اصلی، /start را وارد کنید."
        ),
        "invalid_data": (
            "⚠️ *داده نامعتبر!*\n"
            "داده‌های لازم برای ثبت تراکنش موجود نیست.\n"
            "🔄 لطفاً دوباره از ابتدا شروع کنید."
        )
    },
    "en": {
        "welcome": (
            "🌟 *Welcome to the Investment Bot!*\n"
            "Invest in USDT, track your wallet, and earn daily, weekly, or monthly profits. Contact support for assistance!\n"
            "👇 Choose an option below 👇"
        ),
        "main_menu": "📋 *Main Menu*\nPlease select an option:",
        "deposit": "💸 *Deposit USDT*",
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
        "invalid_amount": "⚠️ *Error*: Invalid amount entered!\nPlease enter a valid number (e.g., 100).",
        "success": (
            "🎉 *Deposit Recorded!*\n"
            "Your transaction has been successfully recorded.\n"
            "⏳ Please wait for confirmation from our team."
        ),
        "error": (
            "❌ *Error Occurred!*\n"
            "There was an issue processing your request.\n"
            "🔄 Please try again or contact support."
        ),
        "db_error": (
            "❌ *Database Error!*\n"
            "There was an issue recording the transaction.\n"
            "📩 Please contact support."
        ),
        "admin_error": (
            "❌ *Admin Communication Error!*\n"
            "Unable to send the request to the admin.\n"
            "📩 Please contact support."
        ),
        "cancel": "🛑 *Operation Cancelled*\nTo return to the main menu, use /start.",
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
        "wallet_menu": "💼 *My Wallet*\nPlease select an option:",
        "wallet_balance": lambda balance: (
            f"💼 *Your Wallet Balance*\n"
            f"────────────────────\n"
            f"💰 *Amount*: `{balance}` USDT\n"
            f"────────────────────\n"
            f"📌 Choose an option below to deposit or withdraw."
        ),
        "wallet_empty": (
            "💼 *Wallet is Empty!*\n"
            "No deposits have been confirmed yet.\n"
            "📌 To deposit, select Deposit from the main menu."
        ),
        "withdraw": "💸 *Withdraw*",
        "ask_withdraw_amount": (
            "💰 *Withdrawal Amount*\n"
            "Please enter the amount of USDT you want to withdraw:\n"
            "📌 The amount must be less than or equal to your balance."
        ),
        "insufficient_balance": (
            "⚠️ *Error*: Insufficient balance!\n"
            "Please enter an amount less than or equal to your balance."
        ),
        "ask_withdraw_address": (
            "📋 *Wallet Address*\n"
            "Please enter your USDT wallet address for withdrawal:\n"
            "📌 Enter the address carefully."
        ),
        "withdraw_success": (
            "🎉 *Withdrawal Request Recorded!*\n"
            "Your request has been successfully recorded.\n"
            "⏳ Please wait for confirmation from our team."
        ),
        "withdraw_confirmed": (
            "✅ *Withdrawal Confirmed!*\n"
            "Your withdrawal request has been successfully confirmed.\n"
            "📤 The funds will be sent to your wallet soon!"
        ),
        "withdraw_rejected": (
            "❌ *Withdrawal Rejected!*\n"
            "Your withdrawal request was not approved.\n"
            "📩 Please contact support for more details."
        ),
        "language_menu": (
            "🌐 *Select Language*\n"
            "Please choose your preferred language:\n"
            "👇 Choose one of the options below 👇"
        ),
        "language_updated": (
            "✅ *Language Updated!*\n"
            "You can now continue from the main menu."
        ),
        "support": (
            "📩 *Support*\n"
            "For assistance, contact our support team:\n"
            "👤 @farzadnazari"
        ),
        "history": lambda transactions: (
            f"📜 *Transaction History*\n"
            f"────────────────────\n"
            f"{transactions}\n"
            f"────────────────────\n"
            f"📌 For a new deposit or withdrawal, go to the main menu."
        ),
        "no_history": (
            "📜 *No Transaction History*\n"
            "No transactions have been recorded yet.\n"
            "📌 To deposit, go to the main menu."
        ),
        "unauthorized": (
            "🚫 *Error*: You are not authorized to access this command!\n"
            "📩 Please contact support."
        ),
        "unexpected_message": (
            "⚠️ *Invalid Message*\n"
            "Please use the menu buttons or enter a valid amount.\n"
            "To return to the main menu, use /start."
        ),
        "invalid_data": (
            "⚠️ *Invalid Data!*\n"
            "Required data for the transaction is missing.\n"
            "🔄 Please start over."
        )
    }
}

wallet_addresses = {
    "TRC20": "TXExampleTRC20Wallet123",
    "BEP20": "0xExampleBEP20Wallet456"
}

# توابع مدیریت دیتابیس
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.error("DATABASE_URL not found in environment variables")
    exit(1)

def init_db():
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        # ایجاد جدول users
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                language TEXT DEFAULT 'en',
                balance REAL DEFAULT 0.0
            )
        ''')
        # ایجاد جدول transactions
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount REAL,
                network TEXT,
                status TEXT,
                type TEXT,
                created_at TEXT,
                message_id BIGINT,
                address TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        # بررسی و اضافه کردن ستون type اگر وجود ندارد
        c.execute('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'transactions' AND column_name = 'type'
        ''')
        if not c.fetchone():
            c.execute('ALTER TABLE transactions ADD COLUMN type TEXT')
            logger.info("Added missing 'type' column to transactions table")
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()

def get_user(user_id):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute('SELECT language, balance FROM users WHERE user_id = %s', (user_id,))
        user = c.fetchone()
        return user
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()

def upsert_user(user_id, language='en'):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute('''
            INSERT INTO users (user_id, language, balance)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET language = %s
        ''', (user_id, language, 0.0, language))
        conn.commit()
        logger.info(f"Upserted user {user_id} with language {language}")
    except Exception as e:
        logger.error(f"Error upserting user {user_id}: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()

def update_balance(user_id, amount):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute('UPDATE users SET balance = balance + %s WHERE user_id = %s', (amount, user_id))
        conn.commit()
        logger.info(f"Updated balance for user {user_id}: added {amount}")
    except Exception as e:
        logger.error(f"Error updating balance for user {user_id}: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()

def insert_transaction(user_id, amount, network, status, type, message_id, address=None):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        created_at = datetime.utcnow().isoformat()
        c.execute('''
            INSERT INTO transactions (user_id, amount, network, status, type, created_at, message_id, address)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (user_id, amount, network, status, type, created_at, message_id, address))
        conn.commit()
        logger.info(f"Inserted transaction for user {user_id}: amount {amount}, network {network}, status {status}, type {type}")
    except Exception as e:
        logger.error(f"Error inserting transaction for user {user_id}: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()

def update_transaction_status(transaction_id, user_id, message_id, status):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute('''
            UPDATE transactions
            SET status = %s
            WHERE user_id = %s AND message_id = %s AND status = 'pending'
        ''', (status, user_id, message_id))
        conn.commit()
        logger.info(f"Updated transaction status for user {user_id}, message_id {message_id} to {status}")
    except Exception as e:
        logger.error(f"Error updating transaction status for user {user_id}: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()

def get_transaction(user_id, message_id):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute('''
            SELECT amount, network, status, type, address
            FROM transactions
            WHERE user_id = %s AND message_id = %s AND status = 'pending'
        ''', (user_id, message_id))
        transaction = c.fetchone()
        return transaction
    except Exception as e:
        logger.error(f"Error getting transaction for user {user_id}: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()

def get_transaction_history(user_id):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute('''
            SELECT amount, network, status, type, created_at
            FROM transactions
            WHERE user_id = %s
            ORDER BY created_at DESC
        ''', (user_id,))
        transactions = c.fetchall()
        logger.info(f"Retrieved {len(transactions)} transactions for user {user_id}")
        return transactions
    except Exception as e:
        logger.error(f"Error getting transaction history for user {user_id}: {e}")
        return []
    finally:
        if conn is not None:
            conn.close()

# مقداردهی اولیه دیتابیس
try:
    init_db()
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    exit(1)

# نمایش منوی اصلی
def get_main_menu(lang):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💸 واریز" if lang == "fa" else "💸 Deposit", callback_data="deposit"),
            InlineKeyboardButton("💼 ولت من" if lang == "fa" else "💼 My Wallet", callback_data="wallet")
        ],
        [
            InlineKeyboardButton("🌐 زبان" if lang == "fa" else "🌐 Language", callback_data="language"),
            InlineKeyboardButton("📩 پشتیبانی" if lang == "fa" else "📩 Support", callback_data="support")
        ]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"User {user_id} called /start")
    
    # پاک‌سازی داده‌های قبلی کاربر
    context.user_data.clear()
    
    # تنظیم زبان پیش‌فرض انگلیسی برای کاربران جدید
    user = get_user(user_id)
    lang = user[0] if user else "en"
    if not user:
        upsert_user(user_id, language="en")
    
    await update.message.reply_text(
        messages[lang]["welcome"],
        parse_mode="Markdown",
        reply_markup=get_main_menu(lang)
    )
    return ConversationHandler.END

async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} triggered callback: {query.data}")

    try:
        if query.data == "deposit":
            context.user_data["conversation_state"] = DEPOSIT_AMOUNT
            await query.message.reply_text(
                messages[lang]["ask_amount"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return DEPOSIT_AMOUNT

        elif query.data == "wallet":
            balance = user[1] if user else 0
            if balance == 0:
                await query.message.reply_text(
                    messages[lang]["wallet_empty"],
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("💸 واریز" if lang == "fa" else "💸 Deposit", callback_data="deposit"),
                            InlineKeyboardButton("📜 تاریخچه" if lang == "fa" else "📜 History", callback_data="history")
                        ],
                        [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                    ])
                )
            else:
                await query.message.reply_text(
                    messages[lang]["wallet_balance"](balance),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("💸 برداشت" if lang == "fa" else "💸 Withdraw", callback_data="withdraw"),
                            InlineKeyboardButton("📜 تاریخچه" if lang == "fa" else "📜 History", callback_data="history")
                        ],
                        [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                    ])
                )
            return ConversationHandler.END

        elif query.data == "withdraw":
            context.user_data["conversation_state"] = WITHDRAW_AMOUNT
            await query.message.reply_text(
                messages[lang]["ask_withdraw_amount"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
                ])
            )
            return WITHDRAW_AMOUNT

        elif query.data == "history":
            transactions = get_transaction_history(user_id)
            if not transactions:
                await query.message.reply_text(
                    messages[lang]["no_history"],
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
                    ])
                )
                return ConversationHandler.END

            transaction_text = ""
            status_map = {
                "pending": ("⏳ در انتظار", "⏳ Pending"),
                "confirmed": ("✅ تأییدشده", "✅ Confirmed"),
                "rejected": ("❌ ردشده", "❌ Rejected")
            }
            type_map = {
                "deposit": ("واریز", "Deposit"),
                "withdrawal": ("برداشت", "Withdrawal")
            }
            for amount, network, status, type, created_at in transactions:
                status_text = status_map[status][0] if lang == "fa" else status_map[status][1]
                type_text = type_map[type][0] if lang == "fa" else type_map[type][1]
                transaction_text += (
                    f"💰 *{type_text}*: `{amount}` تتر\n"
                    f"📲 *شبکه*: {network}\n"
                    f"📅 *وضعیت*: {status_text}\n"
                    f"⏰ *زمان*: {created_at}\n"
                    f"────────────────────\n"
                ) if lang == "fa" else (
                    f"💰 *{type_text}*: `{amount}` USDT\n"
                    f"📲 *Network*: {network}\n"
                    f"📅 *Status*: {status_text}\n"
                    f"⏰ *Time*: {created_at}\n"
                    f"────────────────────\n"
                )

            await query.message.reply_text(
                messages[lang]["history"](transaction_text),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
                ])
            )
            return ConversationHandler.END

        elif query.data == "language":
            await query.message.reply_text(
                messages[lang]["language_menu"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("فارسی", callback_data="lang_fa"),
                        InlineKeyboardButton("English", callback_data="lang_en")
                    ],
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return ConversationHandler.END

        elif query.data.startswith("lang_"):
            new_lang = query.data.split("_")[1]
            upsert_user(user_id, language=new_lang)
            await query.message.reply_text(
                messages[new_lang]["language_updated"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(new_lang)
            )
            return ConversationHandler.END

        elif query.data == "support":
            await query.message.reply_text(
                messages[lang]["support"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return ConversationHandler.END

        elif query.data == "back_to_menu":
            context.user_data.clear()
            await query.message.reply_text(
                messages[lang]["main_menu"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang)
            )
            return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in handle_menu_callback for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        return ConversationHandler.END

async def get_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    text = update.message.text
    logger.info(f"User {user_id} entered deposit amount: {text}")

    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except ValueError:
        logger.warning(f"Invalid deposit amount entered by user {user_id}: {text}")
        await update.message.reply_text(
            messages[lang]["invalid_amount"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
            ])
        )
        return DEPOSIT_AMOUNT

    try:
        context.user_data["amount"] = amount
        await update.message.reply_text(
            messages[lang]["result"](amount),
            parse_mode="Markdown"
        )
        await update.message.reply_text(
            messages[lang]["choose_network"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("TRC20", callback_data="TRC20"),
                    InlineKeyboardButton("BEP20", callback_data="BEP20")
                ],
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
            ])
        )
        return DEPOSIT_NETWORK
    except Exception as e:
        logger.error(f"Error in get_deposit_amount for user {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        return ConversationHandler.END

async def handle_deposit_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} triggered deposit callback: {query.data}")

    try:
        if query.data in ["TRC20", "BEP20"]:
            address = wallet_addresses[query.data]
            context.user_data["network"] = query.data
            await query.message.reply_text(
                messages[lang]["wallet"](query.data, address),
                parse_mode="Markdown"
            )
            await query.message.reply_text(
                messages[lang]["ask_txid"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return DEPOSIT_TXID
        elif query.data == "back_to_menu":
            context.user_data.clear()
            await query.message.reply_text(
                messages[lang]["main_menu"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang)
            )
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_deposit_network for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        return ConversationHandler.END

async def receive_deposit_txid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    admin_id = os.getenv("ADMIN_ID", DEFAULT_ADMIN_ID)
    message_id = update.message.message_id
    logger.info(f"User {user_id} sent deposit TXID or screenshot, message_id: {message_id}, admin_id: {admin_id}")

    if not admin_id or not admin_id.isdigit():
        logger.error(f"Invalid or missing ADMIN_ID: {admin_id}")
        await update.message.reply_text(
            messages[lang]["admin_error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

    admin_id = int(admin_id)
    amount = context.user_data.get("amount")
    network = context.user_data.get("network", "Unknown")

    if not amount or amount <= 0 or not network:
        logger.error(f"Invalid data for user {user_id}: amount={amount}, network={network}")
        await update.message.reply_text(
            messages[lang]["invalid_data"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

    try:
        # فوروارد پیام به ادمین
        logger.info(f"Attempting to forward message {message_id} to admin {admin_id}")
        await context.bot.forward_message(
            chat_id=admin_id,
            from_chat_id=update.effective_chat.id,
            message_id=message_id
        )
        logger.info(f"Message {message_id} forwarded to admin {admin_id}")

        # ثبت تراکنش در دیتابیس
        insert_transaction(user_id, amount, network, "pending", "deposit", message_id)
        logger.info(f"Transaction recorded for user {user_id}")

        # ارسال پیام به ادمین
        logger.info(f"Attempting to send notification to admin {admin_id}")
        await context.bot.send_message(
            chat_id=admin_id,
            text=(
                f"📝 *تراکنش جدید (واریز)*\n"
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
                    InlineKeyboardButton("✅ تأیید", callback_data=f"confirm_deposit_{user_id}_{message_id}"),
                    InlineKeyboardButton("❌ رد", callback_data=f"reject_deposit_{user_id}_{message_id}")
                ]
            ])
        )
        logger.info(f"Notification sent to admin {admin_id}")

        # ارسال پیام موفقیت به کاربر
        await update.message.reply_text(
            messages[lang]["success"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

    except psycopg2.Error as db_error:
        logger.error(f"Database error in receive_deposit_txid for user {user_id}: {db_error}")
        await update.message.reply_text(
            messages[lang]["db_error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

    except telegram.error.TelegramError as tg_error:
        logger.error(f"Telegram error in receive_deposit_txid for user {user_id}: {tg_error}")
        await update.message.reply_text(
            messages[lang]["admin_error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Unexpected error in receive_deposit_txid for user {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["admin_error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

async def get_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    balance = user[1] if user else 0
    text = update.message.text
    logger.info(f"User {user_id} entered withdraw amount: {text}")

    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if amount > balance:
            raise ValueError("Insufficient balance")
    except ValueError as e:
        logger.warning(f"Invalid withdraw amount entered by user {user_id}: {text}")
        error_message = messages[lang]["insufficient_balance"] if str(e) == "Insufficient balance" else messages[lang]["invalid_amount"]
        await update.message.reply_text(
            error_message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
            ])
        )
        return WITHDRAW_AMOUNT

    try:
        context.user_data["withdraw_amount"] = amount
        await update.message.reply_text(
            messages[lang]["ask_withdraw_address"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
            ])
        )
        return WITHDRAW_ADDRESS
    except Exception as e:
        logger.error(f"Error in get_withdraw_amount for user {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        return ConversationHandler.END

async def receive_withdraw_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    admin_id = os.getenv("ADMIN_ID", DEFAULT_ADMIN_ID)
    message_id = update.message.message_id
    address = update.message.text
    logger.info(f"User {user_id} sent withdraw address: {address}, message_id: {message_id}, admin_id: {admin_id}")

    if not admin_id or not admin_id.isdigit():
        logger.error(f"Invalid or missing ADMIN_ID: {admin_id}")
        await update.message.reply_text(
            messages[lang]["admin_error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

    admin_id = int(admin_id)
    amount = context.user_data.get("withdraw_amount")

    if not amount or amount <= 0:
        logger.error(f"Invalid withdraw amount for user {user_id}: amount={amount}")
        await update.message.reply_text(
            messages[lang]["invalid_data"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

    try:
        # فوروارد پیام به ادمین
        logger.info(f"Attempting to forward message {message_id} to admin {admin_id}")
        await context.bot.forward_message(
            chat_id=admin_id,
            from_chat_id=update.effective_chat.id,
            message_id=message_id
        )
        logger.info(f"Message {message_id} forwarded to admin {admin_id}")

        # ثبت تراکنش در دیتابیس
        insert_transaction(user_id, amount, "Unknown", "pending", "withdrawal", message_id, address)
        logger.info(f"Withdrawal transaction recorded for user {user_id}")

        # ارسال پیام به ادمین
        logger.info(f"Attempting to send notification to admin {admin_id}")
        await context.bot.send_message(
            chat_id=admin_id,
            text=(
                f"📝 *درخواست برداشت جدید*\n"
                f"────────────────────\n"
                f"👤 *کاربر*: {update.effective_user.first_name} ({user_id})\n"
                f"🌐 *زبان*: {lang}\n"
                f"💰 *مقدار*: {amount} تتر\n"
                f"📋 *آدرس کیف پول*: {address}\n"
                f"⏰ *زمان*: {update.message.date}\n"
                f"────────────────────\n"
                f"✅ لطفاً وضعیت درخواست را مشخص کنید:"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ تأیید", callback_data=f"confirm_withdrawal_{user_id}_{message_id}"),
                    InlineKeyboardButton("❌ رد", callback_data=f"reject_withdrawal_{user_id}_{message_id}")
                ]
            ])
        )
        logger.info(f"Notification sent to admin {admin_id}")

        # ارسال پیام موفقیت به کاربر
        await update.message.reply_text(
            messages[lang]["withdraw_success"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

    except psycopg2.Error as db_error:
        logger.error(f"Database error in receive_withdraw_address for user {user_id}: {db_error}")
        await update.message.reply_text(
            messages[lang]["db_error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

    except telegram.error.TelegramError as tg_error:
        logger.error(f"Telegram error in receive_withdraw_address for user {user_id}: {tg_error}")
        await update.message.reply_text(
            messages[lang]["admin_error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Unexpected error in receive_withdraw_address for user {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["admin_error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = os.getenv("ADMIN_ID", DEFAULT_ADMIN_ID)
    if not admin_id or not admin_id.isdigit():
        logger.error(f"Invalid or missing ADMIN_ID in handle_admin_callback: {admin_id}")
        return

    admin_id = int(admin_id)
    logger.info(f"Received admin callback: {query.data} from user: {query.from_user.id}")

    if query.data.startswith("confirm_") or query.data.startswith("reject_"):
        if query.from_user.id != admin_id:
            user = get_user(query.from_user.id)
            lang = user[0] if user else "en"
            await query.message.reply_text(
                messages[lang]["unauthorized"],
                parse_mode="Markdown"
            )
            return

        try:
            action, type, user_id, message_id = query.data.split("_")
            user_id = int(user_id)
            message_id = int(message_id)
        except ValueError as e:
            logger.error(f"Error parsing callback_data: {query.data}, error: {e}")
            await query.message.reply_text(
                messages["en"]["error"],
                parse_mode="Markdown"
            )
            return

        transaction = get_transaction(user_id, message_id)
        if not transaction:
            await query.message.reply_text(
                messages["en"]["error"],
                parse_mode="Markdown"
            )
            return

        amount, network, status, type, address = transaction
        user = get_user(user_id)
        user_lang_id = user[0] if user else "en"

        try:
            if action == "confirm":
                if type == "deposit":
                    update_balance(user_id, amount)
                    update_transaction_status(None, user_id, message_id, "confirmed")
                    user = get_user(user_id)
                    balance = user[1] if user else 0
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=messages[user_lang_id]["confirmed"],
                        parse_mode="Markdown"
                    )
                    await query.message.reply_text(
                        f"✅ *تراکنش واریز تأیید شد!*\nکاربر: {user_id}\nمقدار: {amount} تتر\nشبکه: {network}\nموجودی جدید: {balance} تتر",
                        parse_mode="Markdown"
                    )
                elif type == "withdrawal":
                    update_balance(user_id, -amount)
                    update_transaction_status(None, user_id, message_id, "confirmed")
                    user = get_user(user_id)
                    balance = user[1] if user else 0
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=messages[user_lang_id]["withdraw_confirmed"],
                        parse_mode="Markdown"
                    )
                    await query.message.reply_text(
                        f"✅ *تراکنش برداشت تأیید شد!*\nکاربر: {user_id}\nمقدار: {amount} تتر\nآدرس: {address}\nموجودی جدید: {balance} تتر",
                        parse_mode="Markdown"
                    )
            else:  # reject
                update_transaction_status(None, user_id, message_id, "rejected")
                await context.bot.send_message(
                    chat_id=user_id,
                    text=messages[user_lang_id]["rejected"] if type == "deposit" else messages[user_lang_id]["withdraw_rejected"],
                    parse_mode="Markdown"
                )
                await query.message.reply_text(
                    f"❌ *تراکنش {type} رد شد!*\nکاربر: {user_id}\nمقدار: {amount} تتر\nشبکه: {network}",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error in handle_admin_callback for user {user_id}: {e}")
            await query.message.reply_text(
                messages["en"]["error"],
                parse_mode="Markdown"
            )

async def test_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_id = os.getenv("ADMIN_ID", DEFAULT_ADMIN_ID)
    if not admin_id or not admin_id.isdigit():
        logger.error(f"Invalid or missing ADMIN_ID in test_admin: {admin_id}")
        await update.message.reply_text("Invalid ADMIN_ID configuration", parse_mode="Markdown")
        return

    admin_id = int(admin_id)
    user = get_user(user_id)
    lang = user[0] if user else "en"

    if user_id != admin_id:
        await update.message.reply_text(
            messages[lang]["unauthorized"],
            parse_mode="Markdown"
        )
        return

    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text="Test message from bot"
        )
        await update.message.reply_text(
            "✅ Test message sent to admin successfully!",
            parse_mode="Markdown"
        )
    except telegram.error.TelegramError as tg_error:
        logger.error(f"Failed to send test message to admin {admin_id}: {tg_error}")
        await update.message.reply_text(
            f"❌ Failed to send test message: {tg_error}",
            parse_mode="Markdown"
        )

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_id = os.getenv("ADMIN_ID", DEFAULT_ADMIN_ID)
    if not admin_id or not admin_id.isdigit():
        logger.error(f"Invalid or missing ADMIN_ID in debug: {admin_id}")
        return

    admin_id = int(admin_id)
    user = get_user(user_id)
    lang = user[0] if user else "en"

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
        logger.error(f"Error accessing database in debug: {e}")
        await update.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown"
        )

async def test_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_id = os.getenv("ADMIN_ID", DEFAULT_ADMIN_ID)
    if not admin_id or not admin_id.isdigit():
        logger.error(f"Invalid or missing ADMIN_ID in test_db: {admin_id}")
        return

    admin_id = int(admin_id)
    user = get_user(user_id)
    lang = user[0] if user else "en"
    if user_id != admin_id:
        await update.message.reply_text(messages[lang]["unauthorized"], parse_mode="Markdown")
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        await update.message.reply_text("✅ Connection to PostgreSQL successful!")
        conn.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Error connecting to database: {e}", parse_mode="Markdown")

async def reset_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_id = os.getenv("ADMIN_ID", DEFAULT_ADMIN_ID)
    if not admin_id or not admin_id.isdigit():
        logger.error(f"Invalid or missing ADMIN_ID in reset_db: {admin_id}")
        await update.message.reply_text("Invalid ADMIN_ID configuration", parse_mode="Markdown")
        return

    admin_id = int(admin_id)
    user = get_user(user_id)
    lang = user[0] if user else "en"
    if user_id != admin_id:
        await update.message.reply_text(messages[lang]["unauthorized"], parse_mode="Markdown")
        return
    try:
        init_db()
        await update.message.reply_text("✅ Database reset successfully!", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        await update.message.reply_text(f"❌ Error resetting database: {e}", parse_mode="Markdown")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} cancelled conversation")

    await update.message.reply_text(
        messages[lang]["cancel"],
        parse_mode="Markdown",
        reply_markup=get_main_menu(lang)
    )
    context.user_data.clear()
    return ConversationHandler.END

async def handle_unexpected_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    text = update.message.text
    logger.warning(f"User {user_id} sent unexpected message: {text}, conversation state: {context.user_data.get('conversation_state')}")

    await update.message.reply_text(
        messages[lang]["unexpected_message"],
        parse_mode="Markdown",
        reply_markup=get_main_menu(lang)
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_message:
        user_id = update.effective_user.id
        user = get_user(user_id)
        lang = user[0] if user else "en"
        await update.effective_message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )

if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        logger.error("BOT_TOKEN not found in environment variables")
        exit(1)

    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CallbackQueryHandler(handle_menu_callback, pattern="^(deposit|withdraw)$")
        ],
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_deposit_amount)],
            DEPOSIT_NETWORK: [CallbackQueryHandler(handle_deposit_network)],
            DEPOSIT_TXID: [MessageHandler(filters.ALL & ~filters.COMMAND, receive_deposit_txid)],
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_withdraw_amount)],
            WITHDRAW_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_withdraw_address)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=True
    )

    # ترتیب هندلرها: ابتدا ConversationHandler، سپس CallbackQueryHandlerهای خاص
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^(confirm_|reject_)"))
    app.add_handler(CallbackQueryHandler(handle_menu_callback, pattern="^(wallet|history|language|lang_|support|back_to_menu)$"))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CommandHandler("test_db", test_db))
    app.add_handler(CommandHandler("test_admin", test_admin))
    app.add_handler(CommandHandler("reset_db", reset_db))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message))
    app.add_error_handler(error_handler)

    logger.info("🚀 Starting bot polling...")
    app.run_polling()
