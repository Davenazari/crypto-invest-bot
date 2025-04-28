import logging
import os
import psycopg2
from datetime import datetime
import datetime as dt
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
import telegram.error
import uuid
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ConversationHandler states
DEPOSIT_AMOUNT, DEPOSIT_NETWORK, DEPOSIT_TXID, WITHDRAW_AMOUNT, WITHDRAW_ADDRESS = range(5)

# Default admin ID
DEFAULT_ADMIN_ID = "536587863"

# Supported languages
langs = {
    "فارسی": "fa",
    "English": "en"
}

# Localized messages
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
            "لطفاً مقدار سرمایه‌گذاری خود را به *تتر (USDT)* وارد کنید (حداقل 15 تتر، مثال: 100):\n"
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
        "min_deposit_error": (
            "⚠️ *خطا*: مقدار واریز باید حداقل 15 تتر باشد!\n"
            "لطفاً مقدار معتبر (بیشتر یا برابر با 15) وارد کنید."
        ),
        "min_withdraw_error": (
            "⚠️ *خطا*: مقدار برداشت باید حداقل 15 تتر باشد!\n"
            "لطفاً مقدار معتبر (بیشتر یا برابر با 15) وارد کنید."
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
        "wallet_balance": lambda balance, total_profit, transaction_count, last_transaction: (
            f"💼 *کیف پول شما*\n"
            f"────────────────────\n"
            f"💰 *موجودی*: `{balance}` تتر\n"
            f"📈 *کل سود کسب‌شده*: `{total_profit}` تتر\n"
            f"📝 *تراکنش‌های موفق*: `{transaction_count}`\n"
            f"⏰ *آخرین تراکنش*: {'ندارد' if not last_transaction else last_transaction}\n"
            f"────────────────────\n"
            f"📌 برای واریز یا برداشت، گزینه‌های زیر را انتخاب کنید."
        ) if balance > 0 else (
            f"💼 *کیف پول شما*\n"
            f"────────────────────\n"
            f"💰 *موجودی*: `{balance}` تتر\n"
            f"📈 *کل سود کسب‌شده*: `{total_profit}` تتر\n"
            f"📝 *تراکنش‌های موفق*: `{transaction_count}`\n"
            f"⏰ *آخرین تراکنش*: {'ندارد' if not last_transaction else last_transaction}\n"
            f"────────────────────\n"
            f"📌 برای واریز، گزینه واریز را انتخاب کنید."
        ),
        "withdraw": "💸 *برداشت*",
        "ask_withdraw_amount": (
            "💰 *مقدار برداشت*\n"
            "لطفاً مقدار تتر (USDT) مورد نظر برای برداشت را وارد کنید (حداقل 15 تتر، مثال: 100):\n"
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
        "language_error": (
            "❌ *خطا در تغییر زبان!*\n"
            "زبان انتخاب‌شده نامعتبر است یا مشکلی پیش آمده.\n"
            "🔄 لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
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
        ),
        "referral_menu": (
            "🤝 *دعوت دوستان*\n"
            "لطفاً یک گزینه را انتخاب کنید:"
        ),
        "referral_info": lambda link, level1, level2, level3, total_profit, transactions: (
            f"🤝 *سیستم رفرال*\n"
            f"────────────────────\n"
            f"🔗 *لینک دعوت شما*: `{link}`\n"
            f"👥 *کاربران دعوت‌شده*:\n"
            f"  📌 سطح ۱: `{level1}` نفر (۵٪ سود)\n"
            f"  📌 سطح ۲: `{level2}` نفر (۳٪ سود)\n"
            f"  📌 سطح ۳: `{level3}` نفر (۱٪ سود)\n"
            f"💰 *کل سود کسب‌شده*: `{total_profit}` تتر\n"
            f"────────────────────\n"
            f"📜 *تراکنش‌های زیرمجموعه‌ها*:\n{transactions}\n"
            f"────────────────────\n"
            f"📌 لینک خود را به اشتراک بگذارید تا سود بیشتری کسب کنید!"
        ),
        "no_referrals": (
            "🤝 *بدون رفرال*\n"
            "هنوز هیچ کاربری از طریق شما دعوت نشده است.\n"
            f"🔗 *لینک دعوت شما*: `YOUR_LINK_WILL_BE_HERE`\n"
            f"📌 لینک خود را به اشتراک بگذارید تا سود کسب کنید!"
        ),
        "profit_credited": lambda amount, period: (
            f"🎉 *سود سرمایه‌گذاری واریز شد!*\n"
            f"💰 *مقدار*: `{amount}` تتر\n"
            f"📅 *دوره*: {period}\n"
            f"────────────────────\n"
            f"📌 برای مشاهده موجودی، به بخش ولت من بروید."
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
            "Please enter your investment amount in *USDT* (minimum 15 USDT, e.g., 100):\n"
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
        "min_deposit_error": (
            "⚠️ *Error*: Deposit amount must be at least 15 USDT!\n"
            "Please enter a valid amount (greater than or equal to 15)."
        ),
        "min_withdraw_error": (
            "⚠️ *Error*: Withdrawal amount must be at least 15 USDT!\n"
            "Please enter a valid amount (greater than or equal to 15)."
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
        "wallet_balance": lambda balance, total_profit, transaction_count, last_transaction: (
            f"💼 *Your Wallet*\n"
            f"────────────────────\n"
            f"💰 *Balance*: `{balance}` USDT\n"
            f"📈 *Total Profit Earned*: `{total_profit}` USDT\n"
            f"📝 *Successful Transactions*: `{transaction_count}`\n"
            f"⏰ *Last Transaction*: {'None' if not last_transaction else last_transaction}\n"
            f"────────────────────\n"
            f"📌 Choose an option below to deposit or withdraw."
        ) if balance > 0 else (
            f"💼 *Your Wallet*\n"
            f"────────────────────\n"
            f"💰 *Balance*: `{balance}` USDT\n"
            f"📈 *Total Profit Earned*: `{total_profit}` USDT\n"
            f"📝 *Successful Transactions*: `{transaction_count}`\n"
            f"⏰ *Last Transaction*: {'None' if not last_transaction else last_transaction}\n"
            f"────────────────────\n"
            f"📌 To deposit, select the Deposit option."
        ),
        "withdraw": "💸 *Withdraw*",
        "ask_withdraw_amount": (
            "💰 *Withdrawal Amount*\n"
            "Please enter the amount of USDT you want to withdraw (minimum 15 USDT, e.g., 100):\n"
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
        "language_error": (
            "❌ *Language Change Error!*\n"
            "The selected language is invalid or an issue occurred.\n"
            "🔄 Please try again or contact support."
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
        ),
        "referral_menu": (
            "🤝 *Invite Friends*\n"
            "Please select an option:"
        ),
        "referral_info": lambda link, level1, level2, level3, total_profit, transactions: (
            f"🤝 *Referral System*\n"
            f"────────────────────\n"
            f"🔗 *Your Referral Link*: `{link}`\n"
            f"👥 *Invited Users*:\n"
            f"  📌 Level 1: `{level1}` users (5% profit)\n"
            f"  📌 Level 2: `{level2}` users (3% profit)\n"
            f"  📌 Level 3: `{level3}` users (1% profit)\n"
            f"💰 *Total Profit Earned*: `{total_profit}` USDT\n"
            f"────────────────────\n"
            f"📜 *Subordinates' Transactions*:\n{transactions}\n"
            f"────────────────────\n"
            f"📌 Share your link to earn more profits!"
        ),
        "no_referrals": (
            "🤝 *No Referrals*\n"
            "You haven't invited any users yet.\n"
            f"🔗 *Your Referral Link*: `YOUR_LINK_WILL_BE_HERE`\n"
            f"📌 Share your link to start earning!"
        ),
        "profit_credited": lambda amount, period: (
            f"🎉 *Investment Profit Credited!*\n"
            f"💰 *Amount*: `{amount}` USDT\n"
            f"📅 *Period*: {period}\n"
            f"────────────────────\n"
            f"📌 Check your balance in the My Wallet section."
        )
    }
}

# Wallet addresses for deposits
wallet_addresses = {
    "TRC20": "TXExampleTRC20Wallet123",
    "BEP20": "0xExampleBEP20Wallet456"
}

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.error("DATABASE_URL not found in environment variables")
    exit(1)

# Database initialization
def init_db():
    """Initialize database tables."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        language TEXT DEFAULT 'en',
                        balance REAL DEFAULT 0.0
                    )
                ''')
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
                c.execute('''
                    CREATE TABLE IF NOT EXISTS referrals (
                        id SERIAL PRIMARY KEY,
                        referrer_id BIGINT,
                        referred_id BIGINT,
                        level INTEGER,
                        FOREIGN KEY (referrer_id) REFERENCES users (user_id),
                        FOREIGN KEY (referred_id) REFERENCES users (user_id)
                    )
                ''')
                c.execute('''
                    CREATE TABLE IF NOT EXISTS referral_profits (
                        id SERIAL PRIMARY KEY,
                        referrer_id BIGINT,
                        referred_id BIGINT,
                        transaction_id INTEGER,
                        level INTEGER,
                        profit_amount REAL,
                        created_at TEXT,
                        FOREIGN KEY (referrer_id) REFERENCES users (user_id),
                        FOREIGN KEY (referred_id) REFERENCES users (user_id),
                        FOREIGN KEY (transaction_id) REFERENCES transactions (id)
                    )
                ''')
                c.execute('''
                    CREATE TABLE IF NOT EXISTS profits (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        amount REAL,
                        period TEXT,
                        created_at TEXT,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                conn.commit()
                logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

# Database helper functions
def get_user(user_id):
    """Retrieve user data from database."""
    logger.info(f"Fetching user {user_id} from database")
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('SELECT language, balance FROM users WHERE user_id = %s', (user_id,))
                return c.fetchone()
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return None

def upsert_user(user_id, language='en', referred_by=None):
    """Insert or update user in database."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
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

def update_balance(user_id, amount):
    """Update user balance."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('UPDATE users SET balance = balance + %s WHERE user_id = %s', (amount, user_id))
                conn.commit()
                logger.info(f"Updated balance for user {user_id}: added {amount}")
    except Exception as e:
        logger.error(f"Error updating balance for user {user_id}: {e}")
        raise

def insert_transaction(user_id, amount, network, status, type, message_id, address=None):
    """Insert a transaction into the database."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                created_at = dt.datetime.now(dt.UTC).isoformat()
                c.execute('''
                    INSERT INTO transactions (user_id, amount, network, status, type, created_at, message_id, address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (user_id, amount, network, status, type, created_at, message_id, address))
                transaction_id = c.fetchone()[0]
                conn.commit()
                logger.info(f"Inserted transaction for user {user_id}: amount {amount}, network {network}, status {status}, type {type}, id {transaction_id}")
                return transaction_id
    except Exception as e:
        logger.error(f"Error inserting transaction for user {user_id}: {e}")
        raise

def insert_profit(user_id, amount, period):
    """Insert a profit record into the database."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                created_at = dt.datetime.now(dt.UTC).isoformat()
                c.execute('''
                    INSERT INTO profits (user_id, amount, period, created_at)
                    VALUES (%s, %s, %s, %s)
                ''', (user_id, amount, period, created_at))
                conn.commit()
                logger.info(f"Inserted profit for user {user_id}: amount {amount}, period {period}")
    except Exception as e:
        logger.error(f"Error inserting profit for user {user_id}: {e}")
        raise

def update_transaction_status(transaction_id, user_id, message_id, status):
    """Update transaction status."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
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

def get_transaction(user_id, message_id):
    """Retrieve a transaction."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    SELECT amount, network, status, type, address
                    FROM transactions
                    WHERE user_id = %s AND message_id = %s AND status = 'pending'
                ''', (user_id, message_id))
                return c.fetchone()
    except Exception as e:
        logger.error(f"Error getting transaction for user {user_id}: {e}")
        return None

def get_transaction_history(user_id):
    """Retrieve transaction history for a user."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    SELECT amount, network, status, type, created_at
                    FROM transactions
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT 10
                ''', (user_id,))
                transactions = c.fetchall()
                logger.info(f"Retrieved {len(transactions)} transactions for user {user_id}")
                return transactions
    except Exception as e:
        logger.error(f"Error getting transaction history for user {user_id}: {e}")
        return []

def add_referral(referrer_id, referred_id, level):
    """Add a referral entry."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    INSERT INTO referrals (referrer_id, referred_id, level)
                    VALUES (%s, %s, %s)
                ''', (referrer_id, referred_id, level))
                conn.commit()
                logger.info(f"Added referral: referrer {referrer_id}, referred {referred_id}, level {level}")
    except Exception as e:
        logger.error(f"Error adding referral for referrer {referrer_id}: {e}")
        raise

def record_referral_profit(referrer_id, referred_id, transaction_id, level, profit_amount):
    """Record referral profit."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                created_at = dt.datetime.now(dt.UTC).isoformat()
                c.execute('''
                    INSERT INTO referral_profits (referrer_id, referred_id, transaction_id, level, profit_amount, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (referrer_id, referred_id, transaction_id, level, profit_amount, created_at))
                conn.commit()
                logger.info(f"Recorded referral profit: referrer {referrer_id}, referred {referred_id}, profit {profit_amount}, level {level}")
    except Exception as e:
        logger.error(f"Error recording referral profit for referrer {referrer_id}: {e}")
        raise

def get_referral_stats(user_id):
    """Get referral statistics."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    SELECT level, COUNT(*) 
                    FROM referrals 
                    WHERE referrer_id = %s 
                    GROUP BY level
                ''', (user_id,))
                level_counts = {1: 0, 2: 0, 3: 0}
                for level, count in c.fetchall():
                    level_counts[level] = count
                c.execute('''
                    SELECT SUM(profit_amount) 
                    FROM referral_profits 
                    WHERE referrer_id = %s
                ''', (user_id,))
                total_profit = c.fetchone()[0] or 0.0
                c.execute('''
                    SELECT t.amount, t.network, t.status, t.type, t.created_at, r.level
                    FROM transactions t
                    JOIN referrals r ON t.user_id = r.referred_id
                    WHERE r.referrer_id = %s AND t.type = 'deposit' AND t.status = 'confirmed'
                    ORDER BY t.created_at DESC
                    LIMIT 10
                ''', (user_id,))
                transactions = c.fetchall()
                return level_counts[1], level_counts[2], level_counts[3], total_profit, transactions
    except Exception as e:
        logger.error(f"Error getting referral stats for user {user_id}: {e}")
        return 0, 0, 0, 0.0, []

def get_referral_chain(user_id):
    """Get referral chain for a user."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                chain = []
                current_id = user_id
                for level in range(1, 4):
                    c.execute('SELECT user_id FROM users WHERE user_id = %s', (current_id,))
                    result = c.fetchone()
                    if result:
                        chain.append((result[0], level))
                        current_id = result[0]
                    else:
                        break
                return chain
    except Exception as e:
        logger.error(f"Error getting referral chain for user {user_id}: {e}")
        return []

# Initialize database
try:
    init_db()
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    exit(1)

# Menu generation
def get_main_menu(lang):
    """Generate main menu keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💸 واریز" if lang == "fa" else "💸 Deposit", callback_data="deposit"),
            InlineKeyboardButton("💼 ولت من" if lang == "fa" else "💼 My Wallet", callback_data="wallet")
        ],
        [
            InlineKeyboardButton("🤝 دعوت دوستان" if lang == "fa" else "🤝 Invite Friends", callback_data="referral"),
            InlineKeyboardButton("🌐 زبان" if lang == "fa" else "🌐 Language", callback_data="language")
        ],
        [
            InlineKeyboardButton("📩 پشتیبانی" if lang == "fa" else "📩 Support", callback_data="support")
        ]
    ])

def get_referral_menu(lang):
    """Generate referral menu keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")
        ]
    ])

async def distribute_profits(context: ContextTypes.DEFAULT_TYPE):
    """Distribute daily profits to users with positive balances."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('SELECT user_id, balance, language FROM users WHERE balance > 0')
                users = c.fetchall()
                for user_id, balance, lang in users:
                    profit = round(balance * 0.5 / 30, 2)  # Daily profit (0.5% monthly / 30)
                    if profit > 0:
                        update_balance(user_id, profit)
                        insert_profit(user_id, profit, "Daily")
                        # Insert profit as a transaction
                        insert_transaction(user_id, profit, None, "confirmed", "profit", None)
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=messages[lang]["profit_credited"](profit, "روزانه" if lang == "fa" else "Daily"),
                            parse_mode="Markdown"
                        )
                        logger.info(f"Credited {profit} USDT daily profit to user {user_id}")
    except Exception as e:
        logger.error(f"Error distributing profits: {e}")

# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user_id = update.effective_user.id
    args = context.args
    logger.info(f"User {user_id} called /start with args: {args}")
    
    context.user_data.clear()
    
    referred_by = None
    if args and args[0].startswith("ref_"):
        try:
            referred_by = int(args[0].split("_")[1])
            if referred_by == user_id:
                referred_by = None
        except (IndexError, ValueError):
            logger.warning(f"Invalid referral code for user {user_id}: {args[0]}")
    
    user = get_user(user_id)
    lang = user[0] if user else "en"
    if not user:
        upsert_user(user_id, language="en", referred_by=referred_by)
        if referred_by:
            add_referral(referred_by, user_id, 1)
            chain = get_referral_chain(referred_by)
            for referrer_id, level in chain:
                if level < 3:
                    add_referral(referrer_id, user_id, level + 1)
    
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    await update.message.reply_text(
        messages[lang]["welcome"],
        parse_mode="Markdown",
        reply_markup=get_main_menu(lang)
    )
    return ConversationHandler.END

async def handle_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language selection."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} triggered language callback: {query.data}")

    try:
        if query.data in ["lang_fa", "lang_en"]:
            new_lang = query.data.split("_")[1]
            if new_lang not in ["fa", "en"]:
                logger.error(f"Invalid language selected by user {user_id}: {new_lang}")
                await query.message.reply_text(
                    messages[lang]["language_error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            upsert_user(user_id, language=new_lang)
            logger.info(f"Language updated for user {user_id} to {new_lang}")
            context.user_data.clear()
            await query.message.reply_text(
                messages[new_lang]["language_updated"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(new_lang)
            )
            return ConversationHandler.END
        else:
            logger.warning(f"Unexpected language callback data for user {user_id}: {query.data}")
            await query.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang)
            )
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_language_callback for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["language_error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu button callbacks."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} triggered menu callback: {query.data}")

    try:
        if query.data == "deposit":
            context.user_data.clear()
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
            try:
                with psycopg2.connect(DATABASE_URL) as conn:
                    with conn.cursor() as c:
                        # Get total profit from profits table
                        c.execute('SELECT SUM(amount) FROM profits WHERE user_id = %s', (user_id,))
                        total_profit = c.fetchone()[0] or 0.0
                        # Get count of successful transactions
                        c.execute('SELECT COUNT(*) FROM transactions WHERE user_id = %s AND status = %s', (user_id, 'confirmed'))
                        transaction_count = c.fetchone()[0]
                        # Get last transaction date
                        c.execute('SELECT created_at FROM transactions WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT 1', (user_id, 'confirmed'))
                        last_transaction = c.fetchone()[0] if c.rowcount > 0 else None
            except psycopg2.Error as e:
                logger.error(f"Database error retrieving wallet stats for user {user_id}: {e}")
                await query.message.reply_text(
                    messages[lang]["db_error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END

            await query.message.reply_text(
                messages[lang]["wallet_balance"](balance, total_profit, transaction_count, last_transaction),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("💸 واریز" if lang == "fa" else "💸 Deposit", callback_data="deposit"),
                        InlineKeyboardButton("📜 تاریخچه" if lang == "fa" else "📜 History", callback_data="history")
                    ],
                    [
                        InlineKeyboardButton("💸 برداشت" if lang == "fa" else "💸 Withdraw", callback_data="withdraw") if balance > 0 else
                        InlineKeyboardButton("💸 برداشت" if lang == "fa" else "💸 Withdraw", callback_data="no_balance")
                    ],
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return ConversationHandler.END

        elif query.data == "withdraw":
            context.user_data.clear()
            await query.message.reply_text(
                messages[lang]["ask_withdraw_amount"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
                ])
            )
            return WITHDRAW_AMOUNT

        elif query.data == "history":
            try:
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
                    "withdrawal": ("برداشت", "Withdrawal"),
                    "profit": ("سود", "Profit")
                }
                for transaction in transactions:
                    amount, network, status, type, created_at = transaction
                    logger.info(f"Processing transaction for user {user_id}: amount={amount}, network={network}, status={status}, type={type}, created_at={created_at}")
                    if not all([amount, status, type, created_at]):
                        logger.warning(f"Invalid transaction data for user {user_id}: {transaction}")
                        continue
                    # Set network display for profit transactions
                    network_display = network if network else ("بدون شبکه" if lang == "fa" else "No Network")
                    status_text = status_map[status][0] if lang == "fa" else status_map[status][1]
                    type_text = type_map[type][0] if lang == "fa" else type_map[type][1]
                    transaction_text += (
                        f"💰 *{type_text}*: `{amount}` تتر\n"
                        f"📲 *شبکه*: {network_display}\n"
                        f"📅 *وضعیت*: {status_text}\n"
                        f"⏰ *زمان*: {created_at}\n"
                        f"────────────────────\n"
                    ) if lang == "fa" else (
                        f"💰 *{type_text}*: `{amount}` USDT\n"
                        f"📲 *Network*: {network_display}\n"
                        f"📅 *Status*: {status_text}\n"
                        f"⏰ *Time*: {created_at}\n"
                        f"────────────────────\n"
                    )

                if not transaction_text:
                    transaction_text = "📜 بدون تراکنش معتبر" if lang == "fa" else "📜 No valid transactions"

                await query.message.reply_text(
                    messages[lang]["history"](transaction_text),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
                    ])
                )
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error retrieving history for user {user_id}: {e}")
                await query.message.reply_text(
                    messages[lang]["db_error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END

        elif query.data == "referral":
            try:
                level1, level2, level3, total_profit, transactions = get_referral_stats(user_id)
                bot_username = (await context.bot.get_me()).username
                referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
                
                if level1 == 0 and level2 == 0 and level3 == 0:
                    await query.message.reply_text(
                        messages[lang]["no_referrals"].replace("YOUR_LINK_WILL_BE_HERE", referral_link),
                        parse_mode="Markdown",
                        reply_markup=get_referral_menu(lang)
                    )
                else:
                    transaction_text = ""
                    status_map = {
                        "confirmed": ("✅ تأییدشده", "✅ Confirmed")
                    }
                    type_map = {
                        "deposit": ("واریز", "Deposit")
                    }
                    for amount, network, status, type, created_at, level in transactions:
                        status_text = status_map[status][0] if lang == "fa" else status_map[status][1]
                        type_text = type_map[type][0] if lang == "fa" else type_map[type][1]
                        network_display = network if network else ("بدون شبکه" if lang == "fa" else "No Network")
                        transaction_text += (
                            f"💰 *{type_text}*: `{amount}` تتر\n"
                            f"📲 *شبکه*: {network_display}\n"
                            f"📅 *وضعیت*: {status_text}\n"
                            f"📊 *سطح*: {level}\n"
                            f"⏰ *زمان*: {created_at}\n"
                            f"────────────────────\n"
                        ) if lang == "fa" else (
                            f"💰 *{type_text}*: `{amount}` USDT\n"
                            f"📲 *Network*: {network_display}\n"
                            f"📅 *Status*: {status_text}\n"
                            f"📊 *Level*: {level}\n"
                            f"⏰ *Time*: {created_at}\n"
                            f"────────────────────\n"
                        )
                    if not transaction_text:
                        transaction_text = "📜 بدون تراکنش" if lang == "fa" else "📜 No transactions"

                    await query.message.reply_text(
                        messages[lang]["referral_info"](referral_link, level1, level2, level3, total_profit, transaction_text),
                        parse_mode="Markdown",
                        reply_markup=get_referral_menu(lang)
                    )
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error retrieving referral stats for user {user_id}: {e}")
                await query.message.reply_text(
                    messages[lang]["error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
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
    
        elif query.data == "no_balance":
            await query.message.reply_text(
                messages[lang]["insufficient_balance"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
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

        else:
            logger.warning(f"Unhandled callback data for user {user_id}: {query.data}")
            await query.message.reply_text(
                messages[lang]["error"],
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
        context.user_data.clear()
        return ConversationHandler.END

async def get_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit amount input."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    text = update.message.text.strip()  # حذف فاصله‌های اضافی
    logger.info(f"Entering get_deposit_amount for user {user_id}, input: '{text}'")

    try:
        # جایگزینی کاما با نقطه و حذف فاصله‌ها
        cleaned_text = text.replace(',', '.').replace(' ', '')
        amount = float(cleaned_text)
        if amount <= 0:
            logger.warning(f"Negative or zero deposit amount by user {user_id}: {amount}")
            await update.message.reply_text(
                messages[lang]["invalid_amount"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return DEPOSIT_AMOUNT
        if amount < 15:
            logger.warning(f"Deposit amount below minimum by user {user_id}: {amount}")
            await update.message.reply_text(
                messages[lang]["min_deposit_error"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return DEPOSIT_AMOUNT
        # ذخیره مقدار و ادامه
        context.user_data["amount"] = amount
        logger.info(f"Valid deposit amount for user {user_id}: {amount}")
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
    except ValueError as ve:
        logger.warning(f"Invalid deposit amount format by user {user_id}: '{text}', error: {ve}")
        await update.message.reply_text(
            messages[lang]["invalid_amount"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
            ])
        )
        return DEPOSIT_AMOUNT
    except Exception as e:
        logger.error(f"Unexpected error in get_deposit_amount for user {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

async def handle_deposit_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit network selection."""
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
        else:
            logger.warning(f"Invalid network callback data for user {user_id}: {query.data}")
            await query.message.reply_text(
                messages[lang]["error"],
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
        context.user_data.clear()
        return ConversationHandler.END

async def receive_deposit_txid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit TXID or screenshot."""
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
        logger.info(f"Attempting to forward message {message_id} to admin {admin_id}")
        await context.bot.forward_message(
            chat_id=admin_id,
            from_chat_id=update.effective_chat.id,
            message_id=message_id
        )
        logger.info(f"Message {message_id} forwarded to admin {admin_id}")

        transaction_id = insert_transaction(user_id, amount, network, "pending", "deposit", message_id)
        logger.info(f"Transaction recorded for user {user_id}, transaction_id: {transaction_id}")

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
                    InlineKeyboardButton("✅ تأیید", callback_data=f"confirm_deposit_{user_id}_{message_id}_{transaction_id}"),
                    InlineKeyboardButton("❌ رد", callback_data=f"reject_deposit_{user_id}_{message_id}_{transaction_id}")
                ]
            ])
        )
        logger.info(f"Notification sent to admin {admin_id}")

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
    """Handle withdrawal amount input."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    balance = user[1] if user else 0
    text = update.message.text.strip()  # حذف فاصله‌های اضافی
    logger.info(f"Entering get_withdraw_amount for user {user_id}, input: '{text}'")

    try:
        # جایگزینی کاما با نقطه و حذف فاصله‌ها
        cleaned_text = text.replace(',', '.').replace(' ', '')
        amount = float(cleaned_text)
        if amount <= 0:
            logger.warning(f"Negative or zero withdrawal amount by user {user_id}: {amount}")
            await update.message.reply_text(
                messages[lang]["invalid_amount"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
                ])
            )
            return WITHDRAW_AMOUNT
        if amount < 15:
            logger.warning(f"Withdrawal amount below minimum by user {user_id}: {amount}")
            await update.message.reply_text(
                messages[lang]["min_withdraw_error"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
                ])
            )
            return WITHDRAW_AMOUNT
        if amount > balance:
            logger.warning(f"Insufficient balance for withdrawal by user {user_id}: amount={amount}, balance={balance}")
            await update.message.reply_text(
                messages[lang]["insufficient_balance"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
                ])
            )
            return WITHDRAW_AMOUNT
        # ذخیره مقدار و ادامه
        context.user_data["withdraw_amount"] = amount
        logger.info(f"Valid withdrawal amount for user {user_id}: {amount}")
        await update.message.reply_text(
            messages[lang]["ask_withdraw_address"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
            ])
        )
        return WITHDRAW_ADDRESS
    except ValueError as ve:
        logger.warning(f"Invalid withdrawal amount format by user {user_id}: '{text}', error: {ve}")
        await update.message.reply_text(
            messages[lang]["invalid_amount"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
            ])
        )
        return WITHDRAW_AMOUNT
    except Exception as e:
        logger.error(f"Unexpected error in get_withdraw_amount for user {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

async def receive_withdraw_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal address input."""
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
        logger.info(f"Attempting to forward message {message_id} to admin {admin_id}")
        await context.bot.forward_message(
            chat_id=admin_id,
            from_chat_id=update.effective_chat.id,
            message_id=message_id
        )
        logger.info(f"Message {message_id} forwarded to admin {admin_id}")

        transaction_id = insert_transaction(user_id, amount, "Unknown", "pending", "withdrawal", message_id, address)
        logger.info(f"Withdrawal transaction recorded for user {user_id}, transaction_id: {transaction_id}")

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
                    InlineKeyboardButton("✅ تأیید", callback_data=f"confirm_withdrawal_{user_id}_{message_id}_{transaction_id}"),
                    InlineKeyboardButton("❌ رد", callback_data=f"reject_withdrawal_{user_id}_{message_id}_{transaction_id}")
                ]
            ])
        )
        logger.info(f"Notification sent to admin {admin_id}")

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
    """Handle admin actions for transaction confirmation/rejection."""
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
            action, type, user_id, message_id, transaction_id = query.data.split("_")
            user_id = int(user_id)
            message_id = int(message_id)
            transaction_id = int(transaction_id)
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
                    update_transaction_status(transaction_id, user_id, message_id, "confirmed")
                    referral_rates = {1: 0.05, 2: 0.03, 3: 0.01}
                    with psycopg2.connect(DATABASE_URL) as conn:
                        with conn.cursor() as c:
                            c.execute('''
                                SELECT referrer_id, level 
                                FROM referrals 
                                WHERE referred_id = %s
                            ''', (user_id,))
                            referrals = c.fetchall()
                    for referrer_id, level in referrals:
                        if level in referral_rates:
                            profit = amount * referral_rates[level]
                            update_balance(referrer_id, profit)
                            record_referral_profit(referrer_id, user_id, transaction_id, level, profit)
                            user_lang = get_user(referrer_id)[0] if get_user(referrer_id) else "en"
                            await context.bot.send_message(
                                chat_id=referrer_id,
                                text=(
                                    f"🎉 *سود رفرال جدید!*\n"
                                    f"💰 *مقدار*: {profit} تتر\n"
                                    f"📊 *سطح*: {level}\n"
                                    f"👤 *کاربر دعوت‌شده*: {user_id}\n"
                                    f"────────────────────\n"
                                    f"📌 برای مشاهده آمار، به بخش دعوت دوستان بروید."
                                ) if user_lang == "fa" else (
                                    f"🎉 *New Referral Profit!*\n"
                                    f"💰 *Amount*: {profit} USDT\n"
                                    f"📊 *Level*: {level}\n"
                                    f"👤 *Invited User*: {user_id}\n"
                                    f"────────────────────\n"
                                    f"📌 Check the Invite Friends section for stats."
                                ),
                                parse_mode="Markdown"
                            )

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
                    update_transaction_status(transaction_id, user_id, message_id, "confirmed")
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
            else:
                update_transaction_status(transaction_id, user_id, message_id, "rejected")
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
async def test_profit_distribution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test profit distribution manually."""
    user_id = update.effective_user.id
    admin_id = os.getenv("ADMIN_ID", DEFAULT_ADMIN_ID)
    if not admin_id or not admin_id.isdigit():
        await update.message.reply_text("Invalid ADMIN_ID configuration", parse_mode="Markdown")
        return

    admin_id = int(admin_id)
    user = get_user(user_id)
    lang = user[0] if user else "en"

    if user_id != admin_id:
        await update.message.reply_text(messages[lang]["unauthorized"], parse_mode="Markdown")
        return

    await distribute_profits(context)
    await update.message.reply_text("✅ Profit distribution executed!", parse_mode="Markdown")

async def test_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test admin notification."""
    user_id = update.effective_user.id
    admin_id = os.getenv("ADMIN_ID", DEFAULT_ADMIN_ID)
    if not admin_id or not admin_id.isdigit():
        logger.error(f"Invalid or missing ADMIN_ID: {admin_id}")
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
    """Debug database status."""
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
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('SELECT COUNT(*) FROM users')
                user_count = c.fetchone()[0]
                c.execute('SELECT COUNT(*) FROM transactions')
                transaction_count = c.fetchone()[0]
                c.execute('SELECT COUNT(*) FROM referrals')
                referral_count = c.fetchone()[0]
                c.execute('SELECT COUNT(*) FROM referral_profits')
                profit_count = c.fetchone()[0]
                c.execute('SELECT COUNT(*) FROM profits')
                profit_records = c.fetchone()[0]
        await update.message.reply_text(
            f"🛠 *وضعیت دیتابیس*\n"
            f"────────────────────\n"
            f"👤 *تعداد کاربران*: {user_count}\n"
            f"📝 *تعداد تراکنش‌ها*: {transaction_count}\n"
            f"🤝 *تعداد رفرال‌ها*: {referral_count}\n"
            f"💰 *تعداد سودهای رفرال*: {profit_count}\n"
            f"💸 *تعداد سودهای سرمایه‌گذاری*: {profit_records}\n"
            f"────────────────────" if lang == "fa" else
            f"🛠 *Database Status*\n"
            f"────────────────────\n"
            f"👤 *Number of Users*: {user_count}\n"
            f"📝 *Number of Transactions*: {transaction_count}\n"
            f"🤝 *Number of Referrals*: {referral_count}\n"
            f"💰 *Number of Referral Profits*: {profit_count}\n"
            f"💸 *Number of Investment Profits*: {profit_records}\n"
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
    """Test database connection."""
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
        with psycopg2.connect(DATABASE_URL) as conn:
            await update.message.reply_text("✅ Connection to PostgreSQL successful!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error connecting to database: {e}", parse_mode="Markdown")

async def reset_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset database tables."""
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
    """Cancel ongoing conversation."""
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
    """Handle unexpected messages."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    text = update.message.text
    logger.warning(f"User {user_id} sent unexpected message: {text}")

    await update.message.reply_text(
        messages[lang]["unexpected_message"],
        parse_mode="Markdown",
        reply_markup=get_main_menu(lang)
    )
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
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
        context.user_data.clear()

if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        logger.error("BOT_TOKEN not found in environment variables")
        exit(1)

    app = ApplicationBuilder().token(TOKEN).build()

    # برنامه‌ریزی توزیع سود روزانه
    def schedule_daily_profits(app):
        """Schedule daily profit distribution."""
        job_queue = app.job_queue
        if job_queue is None:
            logger.error("JobQueue is not available. Ensure 'python-telegram-bot[job-queue]' is installed in requirements.txt.")
            exit(1)
        try:
            job_queue.run_daily(
                distribute_profits,
                time=dt.time(hour=20, minute=30, tzinfo=dt.timezone.utc),  # اجرا در ساعت 20:30 UTC (00:00 IRST)
                days=(0, 1, 2, 3, 4, 5, 6)  # هر روز هفته
            )
            logger.info("Scheduled daily profit distribution at 20:30 UTC (00:00 IRST)")
        except Exception as e:
            logger.error(f"Failed to schedule daily profit distribution: {e}")
            exit(1)

    schedule_daily_profits(app)

    conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CallbackQueryHandler(handle_menu_callback, pattern="^(deposit|withdraw|wallet|history|referral|language|support|back_to_menu|no_balance)$"),
            CallbackQueryHandler(handle_language_callback, pattern="^(lang_fa|lang_en)$")
        ],
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_deposit_amount)],
            DEPOSIT_NETWORK: [CallbackQueryHandler(handle_deposit_network)],
            DEPOSIT_TXID: [MessageHandler(filters.ALL & ~filters.COMMAND, receive_deposit_txid)],
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_withdraw_amount)],
            WITHDRAW_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_withdraw_address)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message)
        ],
        per_message=True  # اضافه کردن این خط برای رفع هشدار
    )

    app.add_handler(CommandHandler('start', start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^(confirm_|reject_)"))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CommandHandler("test_db", test_db))
    app.add_handler(CommandHandler("test_admin", test_admin))
    app.add_handler(CommandHandler("reset_db", reset_db))
    app.add_handler(CommandHandler("test_profit", test_profit_distribution))
    app.add_error_handler(error_handler)
async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    logger.info(f"Received message from user {user_id}: '{text}'")
    return

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, log_message), group=1)

    logger.info("🚀 Starting bot polling...")
    app.run_polling()
