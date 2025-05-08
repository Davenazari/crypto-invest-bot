import logging
import os
import psycopg2
import asyncio
from datetime import datetime, timedelta
import datetime as dt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)
import telegram.error
import uuid
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ConversationHandler states
SELECT_SEED, DEPOSIT_AMOUNT, DEPOSIT_NETWORK, DEPOSIT_TXID, WITHDRAW_AMOUNT, WITHDRAW_NETWORK, WITHDRAW_ADDRESS, PLANT_SEED, HARVEST_SEED, CONFIRM_BALANCE_PURCHASE = range(10)

# Default admin ID
DEFAULT_ADMIN_ID = 536587863  # Changed to integer

# Supported languages
langs = {"فارسی": "fa", "English": "en"}

# 🌱 **لیست بذرهای مزرعه** 🌾
SEEDS = [
    {"name": "Tomato", "name_fa": "گوجه", "price": 15, "daily_profit_rate": 0.05556, "emoji": "🍅"},
    {"name": "Cucumber", "name_fa": "خیار", "price": 30, "daily_profit_rate": 0.05778, "emoji": "🥒"},
    {"name": "Orange", "name_fa": "پرتغال", "price": 50, "daily_profit_rate": 0.05, "emoji": "🍊"},
    {"name": "Apple", "name_fa": "سیب", "price": 120, "daily_profit_rate": 0.04306, "emoji": "🍎"},
    {"name": "Banana", "name_fa": "موز", "price": 320, "daily_profit_rate": 0.04688, "emoji": "🍌"},
    {"name": "Mango", "name_fa": "انبه", "price": 550, "daily_profit_rate": 0.04545, "emoji": "🥭"},
]

# Localized messages
messages = {
    "fa": {
        "welcome": (
            "🌟 *خوش اومدید به مزرعه USDT!* 🌱\n"
            "اینجا می‌تونید بذر میوه بخرید، هر روز بکارید و سود تضمین‌شده برداشت کنید. "
            "برای شروع، یک بذر انتخاب کنید یا مزرعه خودتون رو بررسی کنید!\n"
            "👇 گزینه مورد نظرتون رو انتخاب کنید 👇"
        ),
        "main_menu": "🌾 *منوی مزرعه*\nلطفاً یک گزینه انتخاب کنید:",
        "select_seed": (
            "🌱 **انتخاب بذر** 🌾\n"
            "لطفاً **بذر** مورد نظر برای خرید را انتخاب کنید:\n"
            "👇 از **بذرهای** زیر یکی را انتخاب کنید 👇"
        ),
        "seed_info": lambda name, price, daily_profit, weekly_profit, monthly_profit, total_monthly, emoji: (
            f"🌾 **بذر {name}** {emoji}\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"💰 **قیمت**: `{price}` تتر\n"
            f"📆 **سود روزانه**: `{daily_profit}` تتر\n"
            f"📅 **سود هفتگی**: `{weekly_profit}` تتر\n"
            f"🗓️ **سود ماهانه**: `{monthly_profit}` تتر\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"🌱 **آماده خرید این بذر هستید؟**"
        ),
        "ask_amount": (
            "💰 *واریز برای خرید بذر*\n"
            "لطفاً مقدار دقیق قیمت بذر ({}) تتر رو واریز کنید:\n"
            "📌 عدد معتبر وارد کنید."
        ),
        "choose_network": (
            "📲 *انتخاب شبکه*\n"
            "لطفاً شبکه مورد نظر برای واریز رو انتخاب کنید:\n"
            "👇 یکی از گزینه‌های زیر رو انتخاب کنید 👇"
        ),
        "wallet": lambda network, address: (
            f"✅ *آدرس کیف پول {network}*\n"
            f"لطفاً واریز رو به این آدرس انجام بدید:\n"
            f"📋 `{address}`\n"
            f"⚠️ *توجه*: فقط از شبکه *{network}* استفاده کنید!"
        ),
        "ask_txid": (
            "📝 *ارسال TXID یا اسکرین‌شات*\n"
            "لطفاً *TXID* تراکنش یا *اسکرین‌شات* واریز خودتون رو ارسال کنید:\n"
            "📌 TXID رو کپی کنید یا تصویر واضحی ارسال کنید."
        ),
        "invalid_amount": "⚠️ *خطا*: مقدار واردشده معتبر نیست!\nلطفاً قیمت دقیق بذر ({}) تتر رو وارد کنید.",
        "success": (
            "🎉 *واریز ثبت شد!*\n"
            "تراکنش شما با موفقیت ثبت شد.\n"
            "⏳ لطفاً منتظر تأیید توسط تیم ما باشید."
        ),
        "error": (
            "❌ *خطا رخ داد!*\n"
            "مشکلی پیش اومد.\n"
            "🔄 لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
        ),
        "db_error": (
            "❌ *خطای دیتابیس!*\n"
            "مشکلی در ثبت تراکنش رخ داد.\n"
            "📩 لطفاً با پشتیبانی تماس بگیرید."
        ),
        "admin_error": (
            "❌ *خطای ارتباط با ادمین!*\n"
            "نمی‌تونیم درخواست رو به ادمین ارسال کنیم.\n"
            "📩 لطفاً با پشتیبانی تماس بگیرید."
        ),
        "cancel": "🛑 *عملیات لغو شد*\nبرای بازگشت به منوی مزرعه، /start رو وارد کنید.",
        "confirmed": (
            "✅ *بذر خریداری شد!*\n"
            "بذر شما با موفقیت به مزرعه اضافه شد.\n"
            "🌱 حالا می‌تونید هر روز بکارید و سود برداشت کنید!"
        ),
        "rejected": (
            "❌ *تراکنش رد شد!*\n"
            "واریز شما تأیید نشد.\n"
            "📩 لطفاً با پشتیبانی تماس بگیرید."
        ),
        "wallet_menu": "🌾 *مزرعه من*\nلطفاً یک گزینه انتخاب کنید:",
        "wallet_balance": lambda balance, seeds, total_profit, transaction_count, last_transaction: (
            f"🌾 **مزرعه شما** 🌱\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"💰 **موجودی**: `{balance}` تتر\n"
            f"🌱 **بذرهای شما**: {seeds or 'هیچ بذری ندارید'}\n"
            f"📈 **کل سود کسب‌شده**: `{total_profit}` تتر\n"
            f"📝 **تراکنش‌های موفق**: `{transaction_count}`\n"
            f"⏰ **آخرین تراکنش**: {'ندارد' if not last_transaction else last_transaction}\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"📌 برای **کاشت**، **برداشت** یا **خرید بذر جدید**، گزینه‌های زیر را انتخاب کنید."
        ),
        "withdraw": "🚜 *برداشت سود*",
        "ask_withdraw_amount": (
            "💰 *مقدار برداشت*\n"
            "لطفاً مقدار تتر (USDT) مورد نظر برای برداشت رو وارد کنید (حداقل 15 تتر):\n"
            "📌 مقدار باید کمتر یا برابر با موجودی شما باشه."
        ),
        "insufficient_balance": (
            "⚠️ *خطا*: موجودی کافی نیست!\n"
            "لطفاً مقداری کمتر یا برابر با موجودی مزرعه‌تون وارد کنید."
        ),
        "ask_withdraw_address": (
            "📋 *آدرس کیف پول*\n"
            "لطفاً آدرس کیف پول USDT خودتون رو برای برداشت وارد کنید:\n"
            "📌 آدرس رو با دقت وارد کنید."
        ),
        "choose_network_withdraw": (
            "📲 *انتخاب شبکه برای برداشت*\n"
            "لطفاً شبکه مورد نظر برای برداشت رو انتخاب کنید:\n"
            "👇 یکی از گزینه‌های زیر رو انتخاب کنید 👇"
        ),
        "withdraw_success": (
            "🎉 *درخواست برداشت ثبت شد!*\n"
            "درخواست شما با موفقیت ثبت شد.\n"
            "⏳ لطفاً منتظر تأیید توسط تیم ما باشید."
        ),
        "withdraw_confirmed": (
            "✅ *برداشت تأیید شد!*\n"
            "درخواست برداشت شما با موفقیت تأیید شد.\n"
            "📤 وجه به زودی به کیف پول شما ارسال می‌شه!"
        ),
        "withdraw_rejected": (
            "❌ *برداشت رد شد!*\n"
            "درخواست برداشت شما تأیید نشد.\n"
            "📩 لطفاً با پشتیبانی تماس بگیرید."
        ),
        "language_menu": (
            "🌐 *انتخاب زبان*\n"
            "لطفاً زبان مورد نظر خودتون رو انتخاب کنید:\n"
            "👇 یکی از گزینه‌های زیر رو انتخاب کنید 👇"
        ),
        "language_updated": (
            "✅ *زبان به‌روزرسانی شد!*\n"
            "حالا می‌تونید از منوی مزرعه ادامه بدید."
        ),
        "language_error": (
            "❌ *خطا در تغییر زبان!*\n"
            "زبان انتخاب‌شده نامعتبره یا مشکلی پیش اومده.\n"
            "🔄 لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
        ),
        "support": (
            "📩 *پشتیبانی*\n"
            "برای دریافت کمک، با پشتیبانی ما تماس بگیرید:\n"
            "👤 @farzadnazari"
        ),
        "history": lambda transactions: (
            f"📜 *تاریخچه مزرعه*\n"
            f"────────────────────\n"
            f"{transactions}\n"
            f"────────────────────\n"
            f"📌 برای خرید بذر یا برداشت، به منوی مزرعه برید."
        ),
        "no_history": (
            "📜 *بدون تاریخچه*\n"
            "هنوز هیچ تراکنشی ثبت نشده.\n"
            "📌 برای خرید بذر، به منوی مزرعه برید."
        ),
        "unauthorized": (
            "🚫 *خطا*: شما اجازه دسترسی به این دستور رو ندارید!\n"
            "📩 لطفاً با پشتیبانی تماس بگیرید."
        ),
        "unexpected_message": (
            "⚠️ *پیام نامعتبر*\n"
            "لطفاً از دکمه‌های منو استفاده کنید یا مقدار معتبری وارد کنید.\n"
            "برای بازگشت به منوی مزرعه، /start رو وارد کنید."
        ),
        "invalid_data": (
            "⚠️ *داده نامعتبر!*\n"
            "داده‌های لازم برای ثبت تراکنش موجود نیست.\n"
            "🔄 لطفاً دوباره از ابتدا شروع کنید."
        ),
        "referral_menu": (
            "🤝 *کارگرهای مزرعه شما*\n"
            "لطفاً یکی از کارگرهای دعوت‌شده رو برای مشاهده جزئیات انتخاب کنید:"
        ),
        "referral_details": lambda username, join_date, seeds, profit, transactions: (
            f"👤 *کارگر: @{username}*\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"📅 *تاریخ ورود*: {join_date}\n"
            f"🌱 *بذرهای خریداری‌شده*:\n{seeds or 'هیچ بذری خریداری نشده'}\n"
            f"💰 *سود کسب‌شده برای شما*: `{profit}` تتر\n"
            f"📜 *تراکنش‌ها*:\n{transactions or 'بدون تراکنش'}\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌"
        ),
        "referral_info": lambda link, level1, level2, level3, total_profit, transactions: (
            f"🤝 *کارگرهای مزرعه*\n"
            f"────────────────────\n"
            f"🔗 *لینک دعوت شما*: `{link}`\n"
            f"👥 *کارگرهای دعوت‌شده*:\n"
            f"  📌 سطح ۱: `{level1}` نفر (۵٪ سود)\n"
            f"  📌 سطح ۲: `{level2}` نفر (۳٪ سود)\n"
            f"  📌 سطح ۳: `{level3}` نفر (۱٪ سود)\n"
            f"💰 *کل سود کسب‌شده*: `{total_profit}` تتر\n"
            f"────────────────────\n"
            f"📜 *تراکنش‌های کارگرها*:\n{transactions}\n"
            f"────────────────────\n"
            f"📌 لینک خودتون رو به اشتراک بگذارید تا سود بیشتری کسب کنید!"
        ),
        "no_referrals": (
            "🤝 *بدون کارگر*\n"
            "هنوز هیچ کارگری به مزرعه دعوت نکردید.\n"
            f"🔗 *لینک دعوت شما*: `YOUR_LINK_WILL_BE_HERE`\n"
            f"📌 لینک رو به اشتراک بگذارید تا سود کسب کنید!"
        ),
        "referral_profit_notification": lambda amount, user_id, level: (
            f"🎉 *سود رفرال دریافت شد!*\n"
            f"مقدار: `{amount}` تتر\n"
            f"سطح: `{level}`\n"
            f"از کاربر: `{user_id}`\n"
            f"📌 برای جزئیات بیشتر، به منوی کارگرهای مزرعه برید."
        ),
        "plant_seed": (
            "🌱 **کاشت بذر** 🌿\n"
            "لطفاً **بذری** که می‌خواهید امروز بکارید را انتخاب کنید:\n"
            "👇 یکی از **بذرهای** زیر را انتخاب کنید 👇"
        ),
        "plant_success": (
            "🌱 *بذر کاشته شد!*\n"
            "بذر شما با موفقیت کاشته شد. می‌تونید بعد از ساعت 00:00 (به وقت ایران) سودش رو برداشت کنید."
        ),
        "plant_already_done": (
            "⚠️ *خطا*: این بذر امروز کاشته شده!\n"
            "هر بذر رو فقط یک‌بار در روز می‌تونید بکارید.\n"
            "📌 فردا دوباره تلاش کنید یا بذر دیگه‌ای بکارید."
        ),
        "harvest_seed": (
            "🚜 **برداشت سود** 💰\n"
            "لطفاً **بذری** که می‌خواهید **سودش** را برداشت کنید انتخاب کنید:\n"
            "👇 یکی از **بذرهای** زیر را انتخاب کنید 👇"
        ),
        "harvest_success": lambda amount: (
            f"🎉 *سود برداشت شد!*\n"
            f"💰 *مقدار*: `{amount}` تتر\n"
            f"📌 سود به موجودی مزرعه‌تون اضافه شد."
        ),
        "harvest_not_ready": (
            "⚠️ *خطا*: هنوز نمی‌تونید سود این بذر رو برداشت کنید!\n"
            "📌 لطفاً بعد از ساعت 00:00 (به وقت ایران) یا پس از کاشت بذر تلاش کنید."
        ),
        "no_seeds": (
            "🌱 *بدون بذر*\n"
            "شما هنوز هیچ بذری ندارید.\n"
            "📌 برای خرید بذر، به منوی مزرعه برید."
        ),
        "db_test_success": (
            "✅ *تست دیتابیس موفق!*\n"
            "اتصال به دیتابیس برقرار است و جدول بذرها پر شده است.\n"
            "تعداد بذرها: {}"
        ),
        "db_test_failed": (
            "❌ *تست دیتابیس ناموفق!*\n"
            "مشکل در اتصال به دیتابیس یا جدول بذرها خالی است.\n"
            "جزئیات خطا: {}"
        ),
        "admin_test_success": (
            "✅ *تست ادمین موفق!*\n"
            "پیام تست به ادمین ارسال شد."
        ),
        "admin_test_failed": (
            "❌ *تست ادمین ناموفق!*\n"
            "نمی‌توان پیام را به ادمین ارسال کرد.\n"
            "جزئیات خطا: {}"
        ),
        "no_seed": (
            "⚠️ *خطا*: این بذر متعلق به شما نیست!\n"
            "📌 لطفاً بذر دیگری انتخاب کنید یا به منوی مزرعه برگردید."
        ),
        "seed_not_planted": (
            "⚠️ *خطا*: این بذر هنوز کاشته نشده!\n"
            "📌 لطفاً ابتدا بذر رو بکارید."
        ),
        "no_profit": (
            "⚠️ *خطا*: هیچ سودی برای برداشت وجود نداره!\n"
            "📌 لطفاً بعد از کاشت و زمان مناسب دوباره تلاش کنید."
        ),
    },
    "en": {
        "welcome": (
            "🌟 *Welcome to the USDT Farm!* 🌱\n"
            "Buy fruit seeds, plant them daily, and harvest guaranteed profits. "
            "Start by choosing a seed or checking your farm!\n"
            "👇 Choose an option below 👇"
        ),
        "main_menu": "🌾 *Farm Menu*\nPlease select an option:",
        "select_seed": (
            "🌱 **Select Seed** 🌾\n"
            "Please choose a **seed** to buy:\n"
            "👇 Pick one of the **seeds** below 👇"
        ),
        "seed_info": lambda name, price, daily_profit, weekly_profit, monthly_profit, total_monthly, emoji: (
            f"🌾 **{name} Seed** {emoji}\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"💰 **Price**: `{price}` USDT\n"
            f"📆 **Daily Profit**: `{daily_profit}` USDT\n"
            f"📅 **Weekly Profit**: `{weekly_profit}` USDT\n"
            f"🗓️ **Monthly Profit**: `{monthly_profit}` USDT\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"🌱 **Ready to buy this seed?**"
        ),
        "ask_amount": (
            "💰 *Deposit for Seed Purchase*\n"
            "Please deposit the exact seed price ({}) USDT:\n"
            "📌 Enter a valid number."
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
        "invalid_amount": "⚠️ *Error*: Invalid amount entered!\nPlease enter the exact seed price ({}) USDT.",
        "success": (
            "🎉 *Deposit Recorded!*\n"
            "Your transaction has been successfully recorded.\n"
            "⏳ Please wait for confirmation from our team."
        ),
        "error": (
            "❌ *Error Occurred!*\n"
            "Something went wrong.\n"
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
        "cancel": "🛑 *Operation Cancelled*\nTo return to the farm menu, use /start.",
        "confirmed": (
            "✅ *Seed Purchased!*\n"
            "Your seed has been added to your farm.\n"
            "🌱 You can now plant daily and harvest profits!"
        ),
        "rejected": (
            "❌ *Transaction Rejected!*\n"
            "Your deposit was not approved.\n"
            "📩 Please contact support."
        ),
        "wallet_menu": "🌾 *My Farm*\nPlease select an option:",
        "wallet_balance": lambda balance, seeds, total_profit, transaction_count, last_transaction: (
            f"🌾 **Your Farm** 🌱\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"💰 **Balance**: `{balance}` USDT\n"
            f"🌱 **Your Seeds**: {seeds or 'No seeds yet'}\n"
            f"📈 **Total Profit Earned**: `{total_profit}` USDT\n"
            f"📝 **Successful Transactions**: `{transaction_count}`\n"
            f"⏰ **Last Transaction**: {'None' if not last_transaction else last_transaction}\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"📌 Choose an option to **plant**, **harvest**, or **buy new seeds**."
        ),
        "withdraw": "🚜 *Harvest Profits*",
        "ask_withdraw_amount": (
            "💰 *Withdrawal Amount*\n"
            "Please enter the amount of USDT you want to withdraw (minimum 15 USDT):\n"
            "📌 The amount must be less than or equal to your balance."
        ),
        "insufficient_balance": (
            "⚠️ *Error*: Insufficient balance!\n"
            "Please enter an amount less than or equal to your farm balance."
        ),
        "ask_withdraw_address": (
            "📋 *Wallet Address*\n"
            "Please enter your USDT wallet address for withdrawal:\n"
            "📌 Enter the address carefully."
        ),
        "choose_network_withdraw": (
            "📲 *Select Network for Withdrawal*\n"
            "Please choose the network for your withdrawal:\n"
            "👇 Choose one of the options below 👇"
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
            "📩 Please contact support."
        ),
        "language_menu": (
            "🌐 *Select Language*\n"
            "Please choose your preferred language:\n"
            "👇 Choose one of the options below 👇"
        ),
        "language_updated": (
            "✅ *Language Updated!*\n"
            "You can now continue from the farm menu."
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
            f"📜 *Farm History*\n"
            f"────────────────────\n"
            f"{transactions}\n"
            f"────────────────────\n"
            f"📌 For new seed purchases or withdrawals, go to the farm menu."
        ),
        "no_history": (
            "📜 *No History*\n"
            "No transactions have been recorded yet.\n"
            "📌 To buy a seed, go to the farm menu."
        ),
        "unauthorized": (
            "🚫 *Error*: You are not authorized to access this command!\n"
            "📩 Please contact support."
        ),
        "unexpected_message": (
            "⚠️ *Invalid Message*\n"
            "Please use the menu buttons or enter a valid amount.\n"
            "To return to the farm menu, use /start."
        ),
        "invalid_data": (
            "⚠️ *Invalid Data!*\n"
            "Required data for the transaction is missing.\n"
            "🔄 Please start over."
        ),
        "referral_menu": (
            "🤝 *Your Farm Workers*\n"
            "Please select one of your invited workers to view details:"
        ),
        "referral_details": lambda username, join_date, seeds, profit, transactions: (
            f"👤 *Worker: @{username}*\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"📅 *Join Date*: {join_date}\n"
            f"🌱 *Purchased Seeds*:\n{seeds or 'No seeds purchased'}\n"
            f"💰 *Profit Earned for You*: `{profit}` USDT\n"
            f"📜 *Transactions*:\n{transactions or 'No transactions'}\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌"
        ),
        "referral_info": lambda link, level1, level2, level3, total_profit, transactions: (
            f"🤝 *Farm Workers*\n"
            f"────────────────────\n"
            f"🔗 *Your Referral Link*: `{link}`\n"
            f"👥 *Invited Workers*:\n"
            f"  📌 Level 1: `{level1}` workers (5% profit)\n"
            f"  📌 Level 2: `{level2}` workers (3% profit)\n"
            f"  📌 Level 3: `{level3}` workers (1% profit)\n"
            f"💰 *Total Profit Earned*: `{total_profit}` USDT\n"
            f"────────────────────\n"
            f"📜 *Workers' Transactions*:\n{transactions}\n"
            f"────────────────────\n"
            f"📌 Share your link to earn more profits!"
        ),
        "no_referrals": (
            "🤝 *No Workers*\n"
            "You haven't invited any workers to your farm yet.\n"
            f"🔗 *Your Referral Link*: `YOUR_LINK_WILL_BE_HERE`\n"
            f"📌 Share your link to start earning!"
        ),
        "referral_profit_notification": lambda amount, user_id, level: (
            f"🎉 *Referral Profit Received!*\n"
            f"Amount: `{amount}` USDT\n"
            f"Level: `{level}`\n"
            f"From User: `{user_id}`\n"
            f"📌 Check the farm workers menu for more details."
        ),
        "plant_seed": (
            "🌱 **Plant Seed** 🌿\n"
            "Please choose a **seed** to plant today:\n"
            "👇 Pick one of the **seeds** below 👇"
        ),
        "plant_success": (
            "🌱 *Seed Planted!*\n"
            "Your seed has been successfully planted. You can harvest its profit after 00:00 (IRST)."
        ),
        "plant_already_done": (
            "⚠️ *Error*: This seed has already been planted today!\n"
            "You can only plant each seed once per day.\n"
            "📌 Try again tomorrow or plant another seed."
        ),
        "harvest_seed": (
            "🚜 **Harvest Profit** 💰\n"
            "Please choose a **seed** to harvest its **profit**:\n"
            "👇 Pick one of the **seeds** below 👇"
        ),
        "harvest_success": lambda amount: (
            f"🎉 *Profit Harvested!*\n"
            f"💰 *Amount*: `{amount}` USDT\n"
            f"📌 The profit has been added to your farm balance."
        ),
        "harvest_not_ready": (
            "⚠️ *Error*: You can't harvest this seed yet!\n"
            "📌 Please try after 00:00 (IRST) or after planting the seed."
        ),
        "no_seeds": (
            "🌱 *No Seeds*\n"
            "You don't have any seeds yet.\n"
            "📌 Go to the farm menu to buy a seed."
        ),
        "db_test_success": (
            "✅ *Database Test Successful!*\n"
            "Connection to the database is established, and the seeds table is populated.\n"
            "Number of seeds: {}"
        ),
        "db_test_failed": (
            "❌ *Database Test Failed!*\n"
            "Issue connecting to the database or seeds table is empty.\n"
            "Error details: {}"
        ),
        "admin_test_success": (
            "✅ *Admin Test Successful!*\n"
            "Test message sent to admin."
        ),
        "admin_test_failed": (
            "❌ *Admin Test Failed!*\n"
            "Unable to send message to admin.\n"
            "Error details: {}"
        ),
        "no_seed": (
            "⚠️ *Error*: This seed does not belong to you!\n"
            "📌 Please select another seed or return to the farm menu."
        ),
        "seed_not_planted": (
            "⚠️ *Error*: This seed has not been planted yet!\n"
            "📌 Please plant the seed first."
        ),
        "no_profit": (
            "⚠️ *Error*: No profit available to harvest!\n"
            "📌 Please try again after planting and at the appropriate time."
        ),
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
    """Initialize database tables and update seed profit rates."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # اضافه کردن ستون‌های username و created_at به جدول users
                logger.info("Adding username and created_at columns to users table")
                c.execute('''
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS username TEXT,
                    ADD COLUMN IF NOT EXISTS created_at TEXT
                ''')
                logger.info("Successfully added username and created_at columns to users table")

                # تعریف جدول users با ساختار درست
                logger.info("Creating users table if not exists")
                c.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        language TEXT DEFAULT 'en',
                        balance REAL DEFAULT 0.0,
                        username TEXT,
                        created_at TEXT
                    )
                ''')
                logger.info("Users table created or already exists")

                # تعریف جدول seeds
                logger.info("Creating seeds table if not exists")
                c.execute('''
                    CREATE TABLE IF NOT EXISTS seeds (
                        seed_id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        name_fa TEXT NOT NULL,
                        price REAL NOT NULL,
                        daily_profit_rate REAL NOT NULL
                    )
                ''')
                logger.info("Seeds table created or already exists")

                # تعریف جدول user_seeds
                logger.info("Creating user_seeds table if not exists")
                c.execute('''
                    CREATE TABLE IF NOT EXISTS user_seeds (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        seed_id INTEGER,
                        purchase_date TEXT,
                        last_planted TEXT,
                        last_harvested TEXT,
                        FOREIGN KEY (user_id) REFERENCES users (user_id),
                        FOREIGN KEY (seed_id) REFERENCES seeds (seed_id)
                    )
                ''')
                logger.info("User_seeds table created or already exists")

                # تعریف جدول transactions
                logger.info("Creating transactions table if not exists")
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
                        seed_id INTEGER,
                        FOREIGN KEY (user_id) REFERENCES users (user_id),
                        FOREIGN KEY (seed_id) REFERENCES seeds (seed_id)
                    )
                ''')
                logger.info("Transactions table created or already exists")

                # تعریف جدول referrals
                logger.info("Creating referrals table if not exists")
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
                logger.info("Referrals table created or already exists")

                # تعریف جدول referral_profits
                logger.info("Creating referral_profits table if not exists")
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
                logger.info("Referral_profits table created or already exists")

                # تعریف جدول profits
                logger.info("Creating profits table if not exists")
                c.execute('''
                    CREATE TABLE IF NOT EXISTS profits (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        seed_id INTEGER,
                        amount REAL,
                        period TEXT,
                        created_at TEXT,
                        FOREIGN KEY (user_id) REFERENCES users (user_id),
                        FOREIGN KEY (seed_id) REFERENCES seeds (seed_id)
                    )
                ''')
                logger.info("Profits table created or already exists")

                # پر کردن یا به‌روزرسانی جدول seeds
                logger.info("Checking and updating seeds table")
                c.execute('SELECT COUNT(*) FROM seeds')
                seed_count = c.fetchone()[0]
                if seed_count == 0:
                    logger.info("Populating seeds table")
                    for seed in SEEDS:
                        c.execute('''
                            INSERT INTO seeds (name, name_fa, price, daily_profit_rate)
                            VALUES (%s, %s, %s, %s)
                        ''', (seed["name"], seed["name_fa"], seed["price"], seed["daily_profit_rate"]))
                    logger.info("Successfully populated seeds table")
                else:
                    logger.info("Updating seeds table with new daily_profit_rate")
                    for seed in SEEDS:
                        c.execute('''
                            UPDATE seeds
                            SET daily_profit_rate = %s
                            WHERE name = %s
                        ''', (seed["daily_profit_rate"], seed["name"]))
                    logger.info("Successfully updated daily_profit_rate in seeds table")

                # چک کردن وجود ستون seed_id در جدول transactions
                logger.info("Checking for seed_id column in transactions table")
                c.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'transactions' AND column_name = 'seed_id'
                """)
                if not c.fetchone():
                    logger.info("Adding seed_id column to transactions table")
                    c.execute('''
                        ALTER TABLE transactions
                        ADD COLUMN seed_id INTEGER
                    ''')
                    c.execute('''
                        ALTER TABLE transactions
                        ADD CONSTRAINT transactions_seed_id_fkey
                        FOREIGN KEY (seed_id) REFERENCES seeds (seed_id)
                    ''')
                    logger.info("Successfully added seed_id column and foreign key to transactions table")

                conn.commit()
                logger.info("Database initialized and seeds updated successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}", exc_info=True)
        try:
            bot = telegram.Bot(token=os.getenv("BOT_TOKEN"))
            bot.send_message(
                chat_id=DEFAULT_ADMIN_ID,
                text=f"⚠️ *Error*: Failed to initialize database: {str(e)}",
                parse_mode="Markdown"
            )
        except Exception as admin_e:
            logger.error(f"Failed to notify admin about database initialization error: {admin_e}")
        raise

def fix_users_table():
    """Add username and created_at columns to users table if they don't exist."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                logger.info("Checking and adding username and created_at columns to users table")
                c.execute('''
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS username TEXT,
                    ADD COLUMN IF NOT EXISTS created_at TEXT
                ''')
                conn.commit()
                logger.info("Successfully added username and created_at columns to users table")
    except Exception as e:
        logger.error(f"Error fixing users table: {e}", exc_info=True)
        raise

# Database helper functions
def get_user(user_id):
    """Retrieve user data from database or create a new user."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('SELECT language, balance FROM users WHERE user_id = %s', (user_id,))
                user = c.fetchone()
                if user:
                    return user
                # Create new user if not found
                upsert_user(user_id, language="en")
                return ("en", 0.0)
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return None

def upsert_user(user_id, language='en', username=None, referred_by=None):
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                created_at = datetime.now(pytz.timezone('Asia/Tehran')).isoformat()
                c.execute('''
                    INSERT INTO users (user_id, language, balance, username, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE 
                    SET language = %s, username = %s
                ''', (user_id, language, 0.0, username, created_at, language, username))
                conn.commit()
                logger.info(f"Upserted user {user_id} with language {language}, username {username}")
    except Exception as e:
        logger.error(f"Error upserting user {user_id}: {e}")
        raise

# تابع جدید برای گرفتن جزئیات رفرال
def get_referral_details(referrer_id, referred_id, lang):
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # گرفتن اطلاعات کاربر (username و زمان ورود)
                c.execute('''
                    SELECT username, created_at 
                    FROM users 
                    WHERE user_id = %s
                ''', (referred_id,))
                user_info = c.fetchone()
                if not user_info:
                    return None
                username, join_date = user_info

                # گرفتن بذرهای خریداری‌شده
                c.execute('''
                    SELECT s.name, s.name_fa, t.created_at
                    FROM user_seeds us
                    JOIN seeds s ON us.seed_id = s.seed_id
                    JOIN transactions t ON t.seed_id = s.seed_id AND t.user_id = %s AND t.status = 'confirmed'
                    WHERE us.user_id = %s
                    ORDER BY t.created_at DESC
                ''', (referred_id, referred_id))
                seeds = c.fetchall()
                seeds_text = "\n".join(
                    f"- {row[1] if lang == 'fa' else row[0]} (خرید: {row[2]})"
                    for row in seeds
                ) if seeds else None

                # گرفتن سود رفرال فقط برای referrer_id خاص
                c.execute('''
                    SELECT SUM(profit_amount) 
                    FROM referral_profits 
                    WHERE referrer_id = %s AND referred_id = %s
                ''', (referrer_id, referred_id))
                profit = c.fetchone()[0] or 0.0

                # گرفتن تراکنش‌ها
                c.execute('''
                    SELECT t.amount, t.network, t.status, t.type, t.created_at, s.name, s.name_fa
                    FROM transactions t
                    LEFT JOIN seeds s ON t.seed_id = s.seed_id
                    WHERE t.user_id = %s AND t.type = 'deposit' AND t.status = 'confirmed'
                    ORDER BY t.created_at DESC
                    LIMIT 10
                ''', (referred_id,))
                transactions = c.fetchall()
                transactions_text = "\n".join(
                    f"- {row[5] or row[6] or 'Unknown'}: {row[0]} USDT ({row[4]})"
                    for row in transactions
                ) if transactions else None

                return {
                    "username": username,
                    "join_date": join_date,
                    "seeds": seeds_text,
                    "profit": profit,
                    "transactions": transactions_text
                }
    except Exception as e:
        logger.error(f"Error getting referral details for referrer {referrer_id}, referred {referred_id}: {e}")
        return None    

def update_balance(user_id, amount):
    """Update user balance."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # گرفتن بالانس فعلی
                c.execute('SELECT balance FROM users WHERE user_id = %s', (user_id,))
                current_balance = c.fetchone()[0] or 0.0
                logger.info(f"Current balance for user {user_id} before update: {current_balance}")
                # آپدیت بالانس
                c.execute('UPDATE users SET balance = balance + %s WHERE user_id = %s', (amount, user_id))
                # گرفتن بالانس جدید
                c.execute('SELECT balance FROM users WHERE user_id = %s', (user_id,))
                new_balance = c.fetchone()[0] or 0.0
                logger.info(f"Updated balance for user {user_id}: added {amount}, new balance: {new_balance}")
                conn.commit()
    except Exception as e:
        logger.error(f"Error updating balance for user {user_id}: {e}", exc_info=True)
        raise

def insert_transaction(user_id, amount, network, status, type, message_id, address=None, seed_id=None):
    """Insert a transaction into the database."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                created_at = dt.datetime.now(dt.UTC).isoformat()
                c.execute('''
                    INSERT INTO transactions (user_id, amount, network, status, type, created_at, message_id, address, seed_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (user_id, amount, network, status, type, created_at, message_id, address, seed_id))
                transaction_id = c.fetchone()[0]
                conn.commit()
                logger.info(f"Inserted transaction for user {user_id}: amount {amount}, network {network}, status {status}, type {type}, seed_id {seed_id}, id {transaction_id}")
                return transaction_id
    except Exception as e:
        logger.error(f"Error inserting transaction for user {user_id}: {e}")
        raise

def insert_profit(user_id, seed_id, amount, period):
    """Insert a profit record into the database."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # Check if profit already recorded for this seed today
                today = datetime.now(pytz.timezone('Asia/Tehran')).date().isoformat()
                c.execute('''
                    SELECT COUNT(*) FROM profits
                    WHERE user_id = %s AND seed_id = %s AND period = %s
                    AND DATE(created_at) = %s
                ''', (user_id, seed_id, period, today))
                if c.fetchone()[0] > 0:
                    logger.warning(f"Profit already recorded for user {user_id}, seed_id {seed_id} today")
                    return
                created_at = dt.datetime.now(dt.UTC).isoformat()
                c.execute('''
                    INSERT INTO profits (user_id, seed_id, amount, period, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (user_id, seed_id, amount, period, created_at))
                conn.commit()
                logger.info(f"Inserted profit for user {user_id}: seed_id {seed_id}, amount {amount}, period {period}")
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

def get_transaction(transaction_id):
    """Retrieve a transaction including its ID."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    SELECT id, user_id, amount, network, status, type, address, seed_id
                    FROM transactions
                    WHERE id = %s AND status = 'pending'
                ''', (transaction_id,))
                return c.fetchone()
    except Exception as e:
        logger.error(f"Error getting transaction for transaction_id {transaction_id}: {e}")
        return None

def get_transaction_history(user_id):
    """Retrieve transaction history for a user."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    SELECT t.amount, t.network, t.status, t.type, t.created_at, s.name, s.name_fa
                    FROM transactions t
                    LEFT JOIN seeds s ON t.seed_id = s.seed_id
                    WHERE t.user_id = %s
                    ORDER BY t.created_at DESC
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

def handle_referral(referrer_id, referred_id):
    """Handle referral processing and insert into referrals table."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # چک کردن اینکه کاربر جدید قبلاً رفرال شده یا نه
                c.execute('SELECT id FROM referrals WHERE referred_id = %s', (referred_id,))
                if c.fetchone():
                    logger.info(f"User {referred_id} is already referred, skipping referral processing")
                    return
                
                # ثبت رفرال سطح 1
                logger.info(f"Adding level 1 referral: referrer {referrer_id}, referred {referred_id}")
                add_referral(referrer_id, referred_id, 1)

                # گرفتن زنجیره رفرال برای ثبت سطح‌های 2 و 3
                c.execute('SELECT referrer_id FROM referrals WHERE referred_id = %s', (referrer_id,))
                level_2_referrer = c.fetchone()
                if level_2_referrer:
                    level_2_referrer_id = level_2_referrer[0]
                    logger.info(f"Adding level 2 referral: referrer {level_2_referrer_id}, referred {referred_id}")
                    add_referral(level_2_referrer_id, referred_id, 2)

                    # چک کردن سطح 3
                    c.execute('SELECT referrer_id FROM referrals WHERE referred_id = %s', (level_2_referrer_id,))
                    level_3_referrer = c.fetchone()
                    if level_3_referrer:
                        level_3_referrer_id = level_3_referrer[0]
                        logger.info(f"Adding level 3 referral: referrer {level_3_referrer_id}, referred {referred_id}")
                        add_referral(level_3_referrer_id, referred_id, 3)

                conn.commit()
                logger.info(f"Referral processing completed for referred_id {referred_id}")
    except Exception as e:
        logger.error(f"Error handling referral for referrer {referrer_id}, referred {referred_id}: {e}")
        raise    

def record_referral_profit(referrer_id, referred_id, transaction_id, level, profit_amount):
    """Record referral profit and send notification to referrer."""
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
        
        # ارسال اعلان به رفرر
        try:
            bot = Bot(token=os.getenv("BOT_TOKEN"))
            user = get_user(referrer_id)
            lang = user[0] if user else "en"
            # تابع کمکی برای ارسال پیام به صورت async
            async def send_notification():
                await bot.send_message(
                    chat_id=referrer_id,
                    text=messages[lang]["referral_profit_notification"](
                        round(profit_amount, 2), referred_id, level
                    ),
                    parse_mode="Markdown"
                )
            # اجرای تابع async در یک event loop
            loop = asyncio.get_event_loop()
            loop.run_until_complete(send_notification())
            logger.info(f"Sent referral profit notification to referrer {referrer_id}")
        except telegram.error.TelegramError as e:
            logger.error(f"Failed to send referral profit notification to referrer {referrer_id}: {e}")
        except Exception as e:
            logger.error(f"Error sending notification to referrer {referrer_id}: {e}")
    except Exception as e:
        logger.error(f"Error recording referral profit for referrer {referrer_id}: {e}")
        raise

def get_referral_stats(user_id):
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # تعداد رفرال‌ها در هر سطح
                c.execute('''
                    SELECT level, COUNT(*) 
                    FROM referrals 
                    WHERE referrer_id = %s 
                    GROUP BY level
                ''', (user_id,))
                level_counts = {1: 0, 2: 0, 3: 0}
                for level, count in c.fetchall():
                    level_counts[level] = count

                # کل سود رفرال
                c.execute('''
                    SELECT SUM(profit_amount) 
                    FROM referral_profits 
                    WHERE referrer_id = %s
                ''', (user_id,))
                total_profit = c.fetchone()[0] or 0.0

                # گرفتن رفرال‌ها برای نمایش دکمه‌ها
                c.execute('''
                    SELECT r.referred_id, u.username 
                    FROM referrals r
                    JOIN users u ON r.referred_id = u.user_id
                    WHERE r.referrer_id = %s
                    ORDER BY r.id
                ''', (user_id,))
                referrals = c.fetchall()

                # گرفتن تراکنش‌های رفرال‌ها
                c.execute('''
                    SELECT t.amount, t.network, t.status, t.type, t.created_at, r.level, s.name, s.name_fa
                    FROM transactions t
                    JOIN referrals r ON t.user_id = r.referred_id
                    LEFT JOIN seeds s ON t.seed_id = s.seed_id
                    WHERE r.referrer_id = %s AND t.type = 'deposit' AND t.status = 'confirmed'
                    ORDER BY t.created_at DESC
                    LIMIT 10
                ''', (user_id,))
                transactions = c.fetchall()

                return level_counts[1], level_counts[2], level_counts[3], total_profit, transactions, referrals
    except Exception as e:
        logger.error(f"Error getting referral stats for user {user_id}: {e}")
        return 0, 0, 0, 0.0, [], []

def get_referral_chain(user_id):
    """Get referral chain for a user."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                chain = []
                current_id = user_id
                for level in range(1, 4):
                    c.execute('SELECT referrer_id FROM referrals WHERE referred_id = %s AND level = %s', (current_id, 1))
                    result = c.fetchone()
                    if result:
                        chain.append((result[0], level))
                        current_id = result[0]
                    else:
                        break
                logger.info(f"Referral chain for user {user_id}: {chain}")
                return chain
    except Exception as e:
        logger.error(f"Error getting referral chain for user {user_id}: {e}")
        return []

def has_referrals(user_id):
    """Check if a user has any referrers."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('SELECT COUNT(*) FROM referrals WHERE referred_id = %s', (user_id,))
                count = c.fetchone()[0]
                logger.info(f"User {user_id} has {count} referrers")
                return count > 0
    except Exception as e:
        logger.error(f"Error checking referrals for user {user_id}: {e}")
        return False

def get_user_seeds(user_id):
    """Retrieve all seeds owned by a user."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    SELECT s.name, s.name_fa, s.price, s.daily_profit_rate, 
                           us.last_planted, us.last_harvested, us.id
                    FROM user_seeds us
                    JOIN seeds s ON us.seed_id = s.seed_id
                    WHERE us.user_id = %s
                ''', (user_id,))
                return c.fetchall()
    except Exception as e:
        logger.error(f"Error getting seeds for user {user_id}: {e}")
        return []    

def get_user_seed(user_id, user_seed_id):
    """Retrieve a specific user seed by user_seed_id."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    SELECT us.seed_id, us.last_planted, us.last_harvested, s.price, s.daily_profit_rate
                    FROM user_seeds us
                    JOIN seeds s ON us.seed_id = s.seed_id
                    WHERE us.id = %s AND us.user_id = %s
                ''', (user_seed_id, user_id))
                result = c.fetchone()
                logger.info(f"Retrieved seed for user {user_id}, user_seed_id {user_seed_id}: {result}")
                return result
    except Exception as e:
        logger.error(f"Error getting user seed {user_seed_id} for user {user_id}: {e}")
        return None
    
def debug_user_seeds(user_id):
    """Debug user seeds data for a specific user."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    SELECT id, seed_id, last_planted, last_harvested
                    FROM user_seeds
                    WHERE user_id = %s
                ''', (user_id,))
                results = c.fetchall()
                logger.info(f"User seeds for user {user_id}: {results}")
                return results
    except Exception as e:
        logger.error(f"Error debugging user seeds for user {user_id}: {e}")
        return None

def fix_seed_id(user_id, user_seed_id, correct_seed_id):
    """Fix seed_id for a specific user seed."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    UPDATE user_seeds
                    SET seed_id = %s
                    WHERE user_id = %s AND id = %s
                ''', (correct_seed_id, user_id, user_seed_id))
                conn.commit()
                logger.info(f"Fixed seed_id for user {user_id}, user_seed_id {user_seed_id} to {correct_seed_id}")
    except Exception as e:
        logger.error(f"Error fixing seed_id for user {user_id}, user_seed_id {user_seed_id}: {e}")    

def fix_database(user_id):
    """Fix seed_id in user_seeds and remove duplicate profits for a specific user."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # Fix seed_id in user_seeds (ID: 2 -> seed_id: 2 for tomato, others -> seed_id: 3 for cucumber)
                c.execute('''
                    UPDATE user_seeds
                    SET seed_id = %s
                    WHERE user_id = %s AND id = %s
                ''', (2, user_id, 2))
                c.execute('''
                    UPDATE user_seeds
                    SET seed_id = %s
                    WHERE user_id = %s AND id IN (%s, %s)
                ''', (3, user_id, 1, 3))
                conn.commit()
                logger.info(f"Fixed seed_id for user {user_id}")

                # Remove duplicate profits and adjust balance
                today = datetime.now(pytz.timezone('Asia/Tehran')).date().isoformat()
                c.execute('''
                    SELECT id, amount FROM profits
                    WHERE user_id = %s AND DATE(created_at) = %s
                    ORDER BY created_at
                ''', (user_id, today))
                profits = c.fetchall()
                total_deducted = 0.0
                valid_profit_ids = []
                seen_seed_ids = set()

                for profit_id, amount in profits:
                    c.execute('SELECT seed_id FROM profits WHERE id = %s', (profit_id,))
                    seed_id = c.fetchone()[0]
                    if seed_id not in seen_seed_ids:
                        valid_profit_ids.append(profit_id)
                        seen_seed_ids.add(seed_id)
                    else:
                        total_deducted += amount
                        c.execute('DELETE FROM profits WHERE id = %s', (profit_id,))

                if total_deducted > 0:
                    c.execute('UPDATE users SET balance = balance - %s WHERE user_id = %s', (total_deducted, user_id))
                    conn.commit()
                    logger.info(f"Removed duplicate profits for user {user_id}, deducted {total_deducted} from balance")

    except Exception as e:
        logger.error(f"Error fixing database for user {user_id}: {e}")
        raise            

def add_user_seed(user_id, seed_id):
    """Add a seed to a user's collection."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                created_at = dt.datetime.now(dt.UTC).isoformat()
                c.execute('''
                    INSERT INTO user_seeds (user_id, seed_id, purchase_date)
                    VALUES (%s, %s, %s)
                ''', (user_id, seed_id, created_at))
                conn.commit()
                logger.info(f"Added seed {seed_id} to user {user_id}")
    except Exception as e:
        logger.error(f"Error adding seed for user {user_id}: {e}")
        raise

def update_seed_plant(user_id, user_seed_id):
    """Update the last planted date for a seed."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                created_at = dt.datetime.now(dt.UTC).isoformat()
                c.execute('''
                    UPDATE user_seeds
                    SET last_planted = %s
                    WHERE id = %s AND user_id = %s
                ''', (created_at, user_seed_id, user_id))
                conn.commit()
                logger.info(f"Updated last planted for user {user_id}, seed {user_seed_id}")
    except Exception as e:
        logger.error(f"Error updating seed plant for user {user_id}: {e}")
        raise

def update_seed_harvest(user_id, user_seed_id):
    """Update the last harvested date for a seed."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                created_at = dt.datetime.now(dt.UTC).isoformat()
                c.execute('''
                    UPDATE user_seeds
                    SET last_harvested = %s
                    WHERE id = %s AND user_id = %s
                ''', (created_at, user_seed_id, user_id))
                conn.commit()
                logger.info(f"Updated last harvested for user {user_id}, seed {user_seed_id}")
    except Exception as e:
        logger.error(f"Error updating seed harvest for user {user_id}: {e}")
        raise

def can_plant_seed(last_planted):
    """Check if a seed can be planted today."""
    if not last_planted:
        return True
    last_planted_dt = datetime.fromisoformat(last_planted)
    today = datetime.now(pytz.timezone('Asia/Tehran')).date()
    last_planted_date = last_planted_dt.astimezone(pytz.timezone('Asia/Tehran')).date()
    return last_planted_date < today

def can_harvest_seed(last_planted, last_harvested, seed_id=None):
    """Check if a seed can be harvested."""
    if not last_planted:
        return False
    last_planted_dt = datetime.fromisoformat(last_planted).astimezone(pytz.timezone('Asia/Tehran'))
    now = datetime.now(pytz.timezone('Asia/Tehran'))
    
    if last_harvested:
        last_harvested_dt = datetime.fromisoformat(last_harvested).astimezone(pytz.timezone('Asia/Tehran'))
        if last_harvested_dt.date() >= last_planted_dt.date():
            return False
    
    return now.date() > last_planted_dt.date()
    return now.date() > last_planted_dt.date()

# Menu generation
def get_main_menu(lang):
    """🌾 Generate main menu keyboard with enhanced visuals."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌱 خرید بذر" if lang == "fa" else "🌱 Buy Seed", callback_data="buy_seed"),
            InlineKeyboardButton("🌾 مزرعه من" if lang == "fa" else "🌾 My Farm", callback_data="wallet")
        ],
        [
            InlineKeyboardButton("🤝 دعوت کارگر" if lang == "fa" else "🤝 Invite Workers", callback_data="referral"),
            InlineKeyboardButton("🌐 زبان" if lang == "fa" else "🌐 Language", callback_data="language")
        ],
        [
            InlineKeyboardButton("📩 پشتیبانی" if lang == "fa" else "📩 Support", callback_data="support")
        ]
    ])


def get_wallet_menu(lang, balance, has_seeds):
    """Generate wallet menu keyboard."""
    buttons = [
        [
            InlineKeyboardButton("🌱 کاشت بذر" if lang == "fa" else "🌱 Plant Seed", callback_data="plant_seed"),
            InlineKeyboardButton("🚜 برداشت سود" if lang == "fa" else "🚜 Harvest Profit", callback_data="harvest_seed")
        ],
        [
            InlineKeyboardButton("🌱 خرید بذر" if lang == "fa" else "🌱 Buy Seed", callback_data="buy_seed"),
            InlineKeyboardButton("📜 تاریخچه" if lang == "fa" else "📜 History", callback_data="history")
        ],
        [
            InlineKeyboardButton("💸 برداشت" if lang == "fa" else "💸 Withdraw", callback_data="withdraw")
        ]
    ]
    buttons.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)

def get_referral_menu(lang, referrals):
    buttons = [
        [InlineKeyboardButton(f"👤 @{ref[1] or 'Unknown'}", callback_data=f"referral_{ref[0]}")]
        for ref in referrals
    ]
    buttons.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)

def get_language_menu(lang):
    """Generate language selection keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("فارسی 🇮🇷", callback_data="lang_fa"),
            InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")
        ],
        [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
    ])


# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_user:
        user_id = update.effective_user.id
        user = get_user(user_id)
        lang = user[0] if user else "en"
        try:
            await update.effective_message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang)
            )
        except Exception as e:
            logger.error(f"Error sending error message to user {user_id}: {e}")

# Test handlers
async def db_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test database connection and seeds table."""
    user_id = update.effective_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await update.message.reply_text(
            messages["en"]["unauthorized"],
            parse_mode="Markdown"
        )
        return

    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('SELECT COUNT(*) FROM seeds')
                seed_count = c.fetchone()[0]
                if seed_count > 0:
                    await update.message.reply_text(
                        messages["en"]["db_test_success"].format(seed_count),
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        messages["en"]["db_test_failed"].format("Seeds table is empty"),
                        parse_mode="Markdown"
                    )
    except Exception as e:
        logger.error(f"Database test failed: {e}")
        await update.message.reply_text(
            messages["en"]["db_test_failed"].format(str(e)),
            parse_mode="Markdown"
        )

async def admin_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test sending a message to admin."""
    user_id = update.effective_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await update.message.reply_text(
            messages["en"]["unauthorized"],
            parse_mode="Markdown"
        )
        return

    try:
        await context.bot.send_message(
            chat_id=DEFAULT_ADMIN_ID,
            text="📩 *Test Message*\nThis is a test message from /admintest.",
            parse_mode="Markdown"
        )
        await update.message.reply_text(
            messages["en"]["admin_test_success"],
            parse_mode="Markdown"
        )
    except telegram.error.TelegramError as e:
        logger.error(f"Admin test failed: {e}")
        await update.message.reply_text(
            messages["en"]["admin_test_failed"].format(str(e)),
            parse_mode="Markdown"
        )


# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    args = context.args
    logger.info(f"User {user_id} called /start with args: {args}")
    
    try:
        context.user_data.clear()
        referred_by = None
        if args and args[0].startswith("ref_"):
            try:
                referred_by = int(args[0].split("_")[1])
                if referred_by == user_id:
                    logger.warning(f"User {user_id} tried to refer themselves")
                    referred_by = None
                else:
                    logger.info(f"Referral detected for user {user_id}: referred_by {referred_by}")
            except (IndexError, ValueError):
                logger.warning(f"Invalid referral code for user {user_id}: {args[0]}")
        
        # ثبت یا به‌روزرسانی کاربر
        user = get_user(user_id)
        lang = user[0] if user else "en"
        upsert_user(user_id, language=lang, username=username)
        logger.info(f"User {user_id} upserted with language {lang}, username {username}")

        # پردازش رفرال
        if referred_by:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as c:
                    # چک کردن اینکه کاربر قبلاً رفرال شده یا نه
                    c.execute('SELECT id FROM referrals WHERE referred_id = %s', (user_id,))
                    if c.fetchone():
                        logger.info(f"User {user_id} is already referred, skipping referral processing")
                    else:
                        # ثبت رفرال سطح 1
                        logger.info(f"Adding level 1 referral: referrer {referred_by}, referred {user_id}")
                        add_referral(referred_by, user_id, 1)

                        # ثبت رفرال‌های سطح 2 و 3
                        c.execute('SELECT referrer_id FROM referrals WHERE referred_id = %s', (referred_by,))
                        level_2_referrer = c.fetchone()
                        if level_2_referrer:
                            level_2_referrer_id = level_2_referrer[0]
                            logger.info(f"Adding level 2 referral: referrer {level_2_referrer_id}, referred {user_id}")
                            add_referral(level_2_referrer_id, user_id, 2)

                            c.execute('SELECT referrer_id FROM referrals WHERE referred_id = %s', (level_2_referrer_id,))
                            level_3_referrer = c.fetchone()
                            if level_3_referrer:
                                level_3_referrer_id = level_3_referrer[0]
                                logger.info(f"Adding level 3 referral: referrer {level_3_referrer_id}, referred {user_id}")
                                add_referral(level_3_referrer_id, user_id, 3)
                        conn.commit()
                        logger.info(f"Referral processing completed for user {user_id}")

        # ارسال پیام خوش‌آمدگویی
        await update.message.reply_text(
            messages[lang]["welcome"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        logger.info(f"Sent welcome message to user {user_id}")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in start for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            messages["en"]["error"],
            parse_mode="Markdown"
        )
        return ConversationHandler.END

def get_seed_selection_menu(lang):
    """🌱 Generate seed selection keyboard with emojis."""
    buttons = [
        [InlineKeyboardButton(f"{seed['emoji']} {seed['name_fa' if lang == 'fa' else 'name']}", callback_data=f"seed_{idx}")]
        for idx, seed in enumerate(SEEDS)
    ]
    buttons.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)

async def handle_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
      """Handle language selection callbacks."""
      query = update.callback_query
      await query.answer()
      user_id = query.from_user.id
      user = get_user(user_id)
      lang = user[0] if user else "en"
      logger.info(f"User {user_id} triggered language callback: {query.data}")

      try:
          if query.data.startswith("lang_"):
              new_lang = query.data.split("_")[1]
              if new_lang in ["fa", "en"]:
                  upsert_user(user_id, language=new_lang)
                  logger.info(f"Updated language for user {user_id} to {new_lang}")
                  await query.message.reply_text(
                      messages[new_lang]["language_updated"],
                      parse_mode="Markdown",
                      reply_markup=get_main_menu(new_lang)
                  )
              else:
                  logger.warning(f"Invalid language selected by user {user_id}: {new_lang}")
                  await query.message.reply_text(
                      messages[lang]["error"],
                      parse_mode="Markdown",
                      reply_markup=get_main_menu(lang)
                  )
          else:
              logger.warning(f"Unhandled language callback for user {user_id}: {query.data}")
              await query.message.reply_text(
                  messages[lang]["error"],
                  parse_mode="Markdown",
                  reply_markup=get_main_menu(lang)
              )
          return ConversationHandler.END
      except Exception as e:
          logger.error(f"Error in handle_language_callback for user {user_id}: {e}", exc_info=True)
          await query.message.reply_text(
              messages[lang]["error"],
              parse_mode="Markdown",
              reply_markup=get_main_menu(lang)
          )
          return ConversationHandler.END

async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu button callbacks."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    if not user:
        logger.error(f"Failed to retrieve or create user {user_id}")
        await query.message.reply_text(
            messages["en"]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu("en")
        )
        return ConversationHandler.END
    lang, balance = user
    logger.info(f"User {user_id} triggered menu callback: {query.data}")

    try:
        if query.data == "buy_seed":
            context.user_data.clear()
            await query.message.reply_text(
                messages[lang]["select_seed"],
                parse_mode="Markdown",
                reply_markup=get_seed_selection_menu(lang)
            )
            return SELECT_SEED
        elif query.data == "wallet":
            try:
                with psycopg2.connect(DATABASE_URL) as conn:
                    with conn.cursor() as c:
                        c.execute('SELECT SUM(amount) FROM profits WHERE user_id = %s', (user_id,))
                        total_profit = c.fetchone()[0] or 0.0
                        c.execute('SELECT COUNT(*) FROM transactions WHERE user_id = %s AND status = %s', (user_id, 'confirmed'))
                        transaction_count = c.fetchone()[0]
                        c.execute('SELECT created_at FROM transactions WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT 1', (user_id, 'confirmed'))
                        last_transaction = c.fetchone()[0] if c.rowcount > 0 else None
                        c.execute('''
                            SELECT s.name, s.name_fa
                            FROM user_seeds us
                            JOIN seeds s ON us.seed_id = s.seed_id
                            WHERE us.user_id = %s
                        ''', (user_id,))
                        seeds = [row[1] if lang == "fa" else row[0] for row in c.fetchall()]
                        seeds_text = ", ".join(seeds) if seeds else None
            except psycopg2.Error as e:
                logger.error(f"Database error retrieving wallet stats for user {user_id}: {e}")
                await query.message.reply_text(
                    messages[lang]["db_error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END

            await query.message.reply_text(
                messages[lang]["wallet_balance"](balance, seeds_text, total_profit, transaction_count, last_transaction),
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance, bool(seeds))
            )
            return ConversationHandler.END
        elif query.data == "plant_seed":
            user_seeds = get_user_seeds(user_id)
            if not user_seeds:
                await query.message.reply_text(
                    messages[lang]["no_seeds"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            buttons = [
                [InlineKeyboardButton(seed[1] if lang == "fa" else seed[0], callback_data=f"plant_{seed[6]}")]
                for seed in user_seeds if can_plant_seed(seed[4])
            ]
            if not buttons:
                await query.message.reply_text(
                    messages[lang]["plant_already_done"],
                    parse_mode="Markdown",
                    reply_markup=get_wallet_menu(lang, balance, True)
                )
                return ConversationHandler.END
            buttons.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")])
            await query.message.reply_text(
                messages[lang]["plant_seed"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return PLANT_SEED
        elif query.data == "harvest_seed":
            user_seeds = get_user_seeds(user_id)
            if not user_seeds:
                await query.message.reply_text(
                    messages[lang]["no_seeds"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            buttons = [
                [InlineKeyboardButton(seed[1] if lang == "fa" else seed[0], callback_data=f"harvest_{seed[6]}")]
                for seed in user_seeds if can_harvest_seed(seed[4], seed[5], seed_id=seed[6])
            ]
            if not buttons:
                await query.message.reply_text(
                    messages[lang]["harvest_not_ready"],
                    parse_mode="Markdown",
                    reply_markup=get_wallet_menu(lang, balance, True)
                )
                return ConversationHandler.END
            buttons.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")])
            await query.message.reply_text(
                messages[lang]["harvest_seed"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return HARVEST_SEED
        elif query.data == "withdraw":
            balance = user[1] if user else 0
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
                        reply_markup=get_wallet_menu(lang, balance, bool(get_user_seeds(user_id)))
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
                    amount, network, status, type, created_at, seed_name, seed_name_fa = transaction
                    if not all([amount, status, type, created_at]):
                        logger.warning(f"Invalid transaction data for user {user_id}: {transaction}")
                        continue
                    network_display = network if network else ("بدون شبکه" if lang == "fa" else "No Network")
                    seed_display = (seed_name_fa if lang == "fa" else seed_name) if seed_name else ("بدون بذر" if lang == "fa" else "No Seed")
                    status_text = status_map[status][0] if lang == "fa" else status_map[status][1]
                    type_text = type_map[type][0] if lang == "fa" else type_map[type][1]
                    transaction_text += (
                        f"💰 *{type_text}*: `{amount}` تتر\n"
                        f"🌱 *بذر*: {seed_display}\n"
                        f"📲 *شبکه*: {network_display}\n"
                        f"📅 *وضعیت*: {status_text}\n"
                        f"⏰ *زمان*: {created_at}\n"
                        f"────────────────────\n"
                    ) if lang == "fa" else (
                        f"💰 *{type_text}*: `{amount}` USDT\n"
                        f"🌱 *Seed*: {seed_display}\n"
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
                    reply_markup=get_wallet_menu(lang, balance, bool(get_user_seeds(user_id)))
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
                level1, level2, level3, total_profit, transactions, referrals = get_referral_stats(user_id)
                bot = telegram.Bot(token=os.getenv("BOT_TOKEN"))
                referral_link = f"https://t.me/{(await bot.get_me()).username}?start=ref_{user_id}"
                
                transaction_text = ""
                status_map = {
                    "confirmed": ("✅ تأییدشده", "✅ Confirmed")
                }
                type_map = {
                    "deposit": ("واریز", "Deposit")
                }
                for amount, network, status, type, created_at, level, seed_name, seed_name_fa in transactions:
                    status_text = status_map[status][0] if lang == "fa" else status_map[status][1]
                    type_text = type_map[type][0] if lang == "fa" else type_map[type][1]
                    network_display = network if network else ("بدون شبکه" if lang == "fa" else "No Network")
                    seed_display = (seed_name_fa if lang == "fa" else seed_name) if seed_name else ("بدون بذر" if lang == "fa" else "No Seed")
                    transaction_text += (
                        f"💰 *{type_text}*: `{amount}` تتر\n"
                        f"🌱 *بذر*: {seed_display}\n"
                        f"📲 *شبکه*: {network_display}\n"
                        f"📅 *وضعیت*: {status_text}\n"
                        f"📊 *سطح*: {level}\n"
                        f"⏰ *زمان*: {created_at}\n"
                        f"────────────────────\n"
                    ) if lang == "fa" else (
                        f"💰 *{type_text}*: `{amount}` USDT\n"
                        f"🌱 *Seed*: {seed_display}\n"
                        f"📲 *Network*: {network_display}\n"
                        f"📅 *Status*: {status_text}\n"
                        f"📊 *Level*: {level}\n"
                        f"⏰ *زمان*: {created_at}\n"
                        f"────────────────────\n"
                    )
                if not transaction_text:
                    transaction_text = "📜 بدون تراکنش" if lang == "fa" else "📜 No transactions"

                if not referrals:
                    await query.message.reply_text(
                        messages[lang]["no_referrals"].replace("YOUR_LINK_WILL_BE_HERE", referral_link),
                        parse_mode="Markdown",
                        reply_markup=get_referral_menu(lang, referrals)
                    )
                else:
                    await query.message.reply_text(
                        messages[lang]["referral_info"](referral_link, level1, level2, level3, total_profit, transaction_text),
                        parse_mode="Markdown",
                        reply_markup=get_referral_menu(lang, referrals)
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
        elif query.data.startswith("referral_") and query.data != "referral":
            try:
                referred_id = int(query.data.split("_")[1])
                details = get_referral_details(user_id, referred_id, lang)
                if not details:
                    await query.message.reply_text(
                        messages[lang]["error"],
                        parse_mode="Markdown",
                        reply_markup=get_main_menu(lang)
                    )
                    return ConversationHandler.END
                await query.message.reply_text(
                    messages[lang]["referral_details"](
                        details["username"],
                        details["join_date"],
                        details["seeds"],
                        details["profit"],
                        details["transactions"]
                    ),
                    parse_mode="Markdown",
                    reply_markup=get_referral_menu(lang, get_referral_stats(user_id)[5])
                )
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error retrieving referral details for user {user_id}, referred_id {referred_id}: {e}")
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
        elif query.data == "language":
            await query.message.reply_text(
                messages[lang]["language_menu"],
                parse_mode="Markdown",
                reply_markup=get_language_menu(lang)
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
    
async def test_referral_profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await update.message.reply_text(
            messages["en"]["unauthorized"],
            parse_mode="Markdown"
        )
        return
    
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    SELECT referrer_id, referred_id, profit_amount, level, created_at
                    FROM referral_profits
                    WHERE referrer_id = %s
                    ORDER BY created_at DESC
                    LIMIT 10
                ''', (user_id,))
                profits = c.fetchall()
                if not profits:
                    await update.message.reply_text(
                        "📉 *No Referral Profits*\nNo profits recorded for your referrals.",
                        parse_mode="Markdown"
                    )
                    return
                response = "📈 *Referral Profits*\n"
                for profit in profits:
                    response += (
                        f"- Referred ID: {profit[1]}, Profit: {profit[2]} USDT, "
                        f"Level: {profit[3]}, Date: {profit[4]}\n"
                    )
                await update.message.reply_text(response, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in test_referral_profit for user {user_id}: {e}")
        await update.message.reply_text(
            f"❌ *Error*: {str(e)}",
            parse_mode="Markdown"
        )    

async def handle_seed_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle seed selection for purchase."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    balance = user[1] if user else 0
    logger.info(f"User {user_id} triggered seed selection callback: {query.data}")

    try:
        if query.data.startswith("seed_"):
            seed_idx = int(query.data.split("_")[1])
            if seed_idx < 0 or seed_idx >= len(SEEDS):
                logger.warning(f"Invalid seed index {seed_idx} for user {user_id}")
                await query.message.reply_text(
                    messages[lang]["error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            seed = SEEDS[seed_idx]
            daily_profit = round(seed["price"] * seed["daily_profit_rate"], 3)
            weekly_profit = round(daily_profit * 7, 3)
            monthly_profit = round(daily_profit * 30, 3)
            total_monthly = round(seed["price"] + monthly_profit, 3)
            context.user_data["seed_idx"] = seed_idx
            context.user_data["seed_price"] = seed["price"]
            buttons = [
                [InlineKeyboardButton("💸 پرداخت با واریز" if lang == "fa" else "💸 Pay with Deposit", callback_data="confirm_seed_purchase")]
            ]
            if balance >= seed["price"]:
                buttons.insert(0, [InlineKeyboardButton("💰 پرداخت با موجودی" if lang == "fa" else "💰 Pay with Balance", callback_data="balance_purchase")])
            buttons.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")])
            await query.message.reply_text(
                messages[lang]["seed_info"](
                    seed["name_fa" if lang == "fa" else "name"],
                    seed["price"],
                    daily_profit,
                    weekly_profit,
                    monthly_profit,
                    total_monthly,
                    seed["emoji"]
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return SELECT_SEED
        elif query.data == "confirm_seed_purchase":
            seed_idx = context.user_data.get("seed_idx")
            seed_price = context.user_data.get("seed_price")
            if seed_idx is None or seed_price is None:
                logger.warning(f"Missing seed_idx or seed_price for user {user_id}")
                await query.message.reply_text(
                    messages[lang]["invalid_data"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            await query.message.reply_text(
                messages[lang]["ask_amount"].format(seed_price),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return DEPOSIT_AMOUNT
        elif query.data == "balance_purchase":
            seed_idx = context.user_data.get("seed_idx")
            seed_price = context.user_data.get("seed_price")
            if seed_idx is None or seed_price is None:
                logger.warning(f"Missing seed_idx or seed_price for user {user_id}")
                await query.message.reply_text(
                    messages[lang]["invalid_data"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            seed = SEEDS[seed_idx]
            daily_profit = round(seed["price"] * seed["daily_profit_rate"], 3)
            weekly_profit = round(daily_profit * 7, 3)
            monthly_profit = round(daily_profit * 30, 3)
            total_monthly = round(seed["price"] + monthly_profit, 3)
            await query.message.reply_text(
                messages[lang]["seed_info"](
                    seed["name_fa" if lang == "fa" else "name"],
                    seed["price"],
                    daily_profit,
                    weekly_profit,
                    monthly_profit,
                    total_monthly,
                    seed["emoji"]
                ) + "\n\n" + ("تأیید خرید با موجودی؟" if lang == "fa" else "Confirm purchase with balance?"),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ تأیید" if lang == "fa" else "✅ Confirm", callback_data="confirm_balance_purchase")],
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return CONFIRM_BALANCE_PURCHASE
        else:
            logger.warning(f"Unhandled callback data for user {user_id}: {query.data}")
            await query.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang)
            )
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_seed_selection for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        await context.bot.send_message(
            chat_id=DEFAULT_ADMIN_ID,
            text=f"⚠️ *Error in handle_seed_selection for user {user_id}*: {str(e)}",
            parse_mode="Markdown"
        )
        context.user_data.clear()
        return ConversationHandler.END
    
async def handle_balance_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle seed purchase with balance."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    balance = user[1] if user else 0
    logger.info(f"User {user_id} triggered balance purchase callback: {query.data}")

    try:
        if query.data == "confirm_balance_purchase":
            seed_idx = context.user_data.get("seed_idx")
            seed_price = context.user_data.get("seed_price")
            if seed_idx is None or seed_price is None:
                await query.message.reply_text(
                    messages[lang]["invalid_data"],
                    parse_mode="Markdown",
                    reply_markup=get_wallet_menu(lang, balance, bool(get_user_seeds(user_id)))
                )
                return ConversationHandler.END
            seed = SEEDS[seed_idx]
            if balance < seed_price:
                await query.message.reply_text(
                    messages[lang]["insufficient_balance"],
                    parse_mode="Markdown",
                    reply_markup=get_wallet_menu(lang, balance, bool(get_user_seeds(user_id)))
                )
                return ConversationHandler.END
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as c:
                    c.execute('SELECT seed_id FROM seeds WHERE name = %s', (seed["name"],))
                    seed_id = c.fetchone()[0]
            update_balance(user_id, -seed_price)
            add_user_seed(user_id, seed_id)
            await query.message.reply_text(
                messages[lang]["confirmed"],
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance - seed_price, True)
            )
            context.user_data.clear()
            return ConversationHandler.END
        elif query.data == "wallet":
            context.user_data.clear()
            try:
                with psycopg2.connect(DATABASE_URL) as conn:
                    with conn.cursor() as c:
                        # جمع سود از جدول profits
                        c.execute('SELECT SUM(amount) FROM profits WHERE user_id = %s', (user_id,))
                        seed_profit = c.fetchone()[0] or 0.0
                        # جمع سود از جدول referral_profits
                        c.execute('SELECT SUM(profit_amount) FROM referral_profits WHERE referrer_id = %s', (user_id,))
                        referral_profit = c.fetchone()[0] or 0.0
                        total_profit = seed_profit + referral_profit
                        c.execute('SELECT COUNT(*) FROM transactions WHERE user_id = %s AND status = %s', (user_id, 'confirmed'))
                        transaction_count = c.fetchone()[0]
                        c.execute('SELECT created_at FROM transactions WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT 1', (user_id, 'confirmed'))
                        last_transaction = c.fetchone()[0] if c.rowcount > 0 else None
                        c.execute('''
                            SELECT s.name, s.name_fa
                            FROM user_seeds us
                            JOIN seeds s ON us.seed_id = s.seed_id
                            WHERE us.user_id = %s
                        ''', (user_id,))
                        seeds = [row[1] if lang == "fa" else row[0] for row in c.fetchall()]
                        seeds_text = ", ".join(seeds) if seeds else None
            except psycopg2.Error as e:
                logger.error(f"Database error retrieving wallet stats for user {user_id}: {e}")
                await query.message.reply_text(
                    messages[lang]["db_error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            await query.message.reply_text(
                messages[lang]["wallet_balance"](balance, seeds_text, total_profit, transaction_count, last_transaction),
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance, bool(seeds))
            )
            return ConversationHandler.END
        else:
            await query.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance, bool(get_user_seeds(user_id)))
            )
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_balance_purchase for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_wallet_menu(lang, balance, bool(get_user_seeds(user_id)))
        )
        context.user_data.clear()
        return ConversationHandler.END    

async def handle_plant_seed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle seed planting."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} triggered plant seed callback: {query.data}")

    try:
        if query.data.startswith("plant_"):
            user_seed_id = int(query.data.split("_")[1])
            user_seeds = get_user_seeds(user_id)
            seed = next((s for s in user_seeds if s[6] == user_seed_id), None)
            if not seed or not can_plant_seed(seed[4]):
                await query.message.reply_text(
                    messages[lang]["plant_already_done"],
                    parse_mode="Markdown",
                    reply_markup=get_wallet_menu(lang, user[1], True)
                )
                return ConversationHandler.END
            update_seed_plant(user_id, user_seed_id)
            await query.message.reply_text(
                messages[lang]["plant_success"],
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, user[1], True)
            )
            return ConversationHandler.END
        elif query.data == "wallet":
            balance = user[1] if user else 0
            try:
                with psycopg2.connect(DATABASE_URL) as conn:
                    with conn.cursor() as c:
                        # جمع سود از جدول profits
                        c.execute('SELECT SUM(amount) FROM profits WHERE user_id = %s', (user_id,))
                        seed_profit = c.fetchone()[0] or 0.0
                        # جمع سود از جدول referral_profits
                        c.execute('SELECT SUM(profit_amount) FROM referral_profits WHERE referrer_id = %s', (user_id,))
                        referral_profit = c.fetchone()[0] or 0.0
                        total_profit = seed_profit + referral_profit
                        c.execute('SELECT COUNT(*) FROM transactions WHERE user_id = %s AND status = %s', (user_id, 'confirmed'))
                        transaction_count = c.fetchone()[0]
                        c.execute('SELECT created_at FROM transactions WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT 1', (user_id, 'confirmed'))
                        last_transaction = c.fetchone()[0] if c.rowcount > 0 else None
                        c.execute('''
                            SELECT s.name, s.name_fa
                            FROM user_seeds us
                            JOIN seeds s ON us.seed_id = s.seed_id
                            WHERE us.user_id = %s
                        ''', (user_id,))
                        seeds = [row[1] if lang == "fa" else row[0] for row in c.fetchall()]
                        seeds_text = ", ".join(seeds) if seeds else None
            except psycopg2.Error as e:
                logger.error(f"Database error retrieving wallet stats for user {user_id}: {e}")
                await query.message.reply_text(
                    messages[lang]["db_error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END

            await query.message.reply_text(
                messages[lang]["wallet_balance"](balance, seeds_text, total_profit, transaction_count, last_transaction),
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance, bool(seeds))
            )
            return ConversationHandler.END
        else:
            logger.warning(f"Unhandled plant seed callback data for user {user_id}: {query.data}")
            await query.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, user[1], True)
            )
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_plant_seed for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_wallet_menu(lang, user[1], True)
        )
        context.user_data.clear()
        return ConversationHandler.END

async def handle_harvest_seed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle seed harvesting by user."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    balance = user[1] if user else 0
    logger.info(f"User {user_id} triggered harvest seed callback: {query.data}")

    try:
        if query.data.startswith("harvest_"):
            user_seed_id = int(query.data.split("_")[1])
            user_seed = get_user_seed(user_id, user_seed_id)
            if not user_seed:
                logger.warning(f"User {user_id} does not own seed with user_seed_id {user_seed_id}")
                await query.message.reply_text(
                    messages[lang]["no_seed"],
                    parse_mode="Markdown",
                    reply_markup=get_wallet_menu(lang, balance, True)
                )
                return ConversationHandler.END

            seed_id, last_planted, last_harvested, price, daily_profit_rate = user_seed
            logger.info(f"Checking harvest for user {user_id}, seed_id {seed_id}, user_seed_id {user_seed_id}")

            if not can_harvest_seed(last_planted, last_harvested, seed_id):
                logger.info(f"Seed {seed_id} not ready for harvest by user {user_id}")
                await query.message.reply_text(
                    messages[lang]["harvest_not_ready"],
                    parse_mode="Markdown",
                    reply_markup=get_wallet_menu(lang, balance, True)
                )
                return ConversationHandler.END

            profit_amount = round(price * daily_profit_rate, 3)
            logger.info(f"Calculated profit for user {user_id}, seed_id {seed_id}: {profit_amount}")

            update_seed_harvest(user_id, user_seed_id)
            update_balance(user_id, profit_amount)
            insert_profit(user_id, seed_id, profit_amount, "daily")

            user_seeds = get_user_seeds(user_id)
            buttons = [
                [InlineKeyboardButton(seed[1] if lang == "fa" else seed[0], callback_data=f"harvest_{seed[6]}")]
                for seed in user_seeds if can_harvest_seed(seed[4], seed[5], seed_id=seed[6])
            ]
            buttons.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")])
            await query.message.reply_text(
                messages[lang]["harvest_success"](profit_amount),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            logger.info(f"Sent harvest success message to user {user_id}")
            return HARVEST_SEED
        elif query.data == "wallet":
            try:
                with psycopg2.connect(DATABASE_URL) as conn:
                    with conn.cursor() as c:
                        # جمع سود از جدول profits
                        c.execute('SELECT SUM(amount) FROM profits WHERE user_id = %s', (user_id,))
                        seed_profit = c.fetchone()[0] or 0.0
                        # جمع سود از جدول referral_profits
                        c.execute('SELECT SUM(profit_amount) FROM referral_profits WHERE referrer_id = %s', (user_id,))
                        referral_profit = c.fetchone()[0] or 0.0
                        total_profit = seed_profit + referral_profit
                        c.execute('SELECT COUNT(*) FROM transactions WHERE user_id = %s AND status = %s', (user_id, 'confirmed'))
                        transaction_count = c.fetchone()[0]
                        c.execute('SELECT created_at FROM transactions WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT 1', (user_id, 'confirmed'))
                        last_transaction = c.fetchone()[0] if c.rowcount > 0 else None
                        c.execute('''
                            SELECT s.name, s.name_fa
                            FROM user_seeds us
                            JOIN seeds s ON us.seed_id = s.seed_id
                            WHERE us.user_id = %s
                        ''', (user_id,))
                        seeds = [row[1] if lang == "fa" else row[0] for row in c.fetchall()]
                        seeds_text = ", ".join(seeds) if seeds else None
            except psycopg2.Error as e:
                logger.error(f"Database error retrieving wallet stats for user {user_id}: {e}")
                await query.message.reply_text(
                    messages[lang]["db_error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END

            await query.message.reply_text(
                messages[lang]["wallet_balance"](balance, seeds_text, total_profit, transaction_count, last_transaction),
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance, bool(seeds))
            )
            return ConversationHandler.END
        else:
            logger.warning(f"Unhandled harvest seed callback data for user {user_id}: {query.data}")
            await query.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance, True)
            )
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_harvest_seed for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_wallet_menu(lang, balance, True)
        )
        return ConversationHandler.END
    
async def check_seeds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check seeds for user 5664533861 (temporary for debugging)."""
    user_id = update.effective_user.id
    if user_id != 5664533861:
        await update.message.reply_text("🚫 Unauthorized")
        return
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    SELECT us.id, us.seed_id, us.last_planted, us.last_harvested, s.name_fa
                    FROM user_seeds us
                    JOIN seeds s ON us.seed_id = s.seed_id
                    WHERE us.user_id = %s
                ''', (user_id,))
                seeds = c.fetchall()
                if not seeds:
                    await update.message.reply_text("🌱 No seeds found.")
                    return
                response = "🌱 Your seeds:\n"
                for seed in seeds:
                    response += (f"ID: {seed[0]}, Seed: {seed[4]}, "
                                f"Last Planted: {seed[2] or 'Never'}, "
                                f"Last Harvested: {seed[3] or 'Never'}\n")
                await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Error checking seeds for user {user_id}: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")  

async def handle_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit amount input."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    seed_price = context.user_data.get("seed_price")
    input_text = update.message.text.strip()
    logger.info(f"User {user_id} entered deposit amount: '{input_text}'")

    if not seed_price:
        logger.error(f"No seed_price in user_data for user {user_id}")
        await update.message.reply_text(
            messages[lang]["invalid_data"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        return ConversationHandler.END

    try:
        amount = float(input_text)
        logger.info(f"Parsed amount for user {user_id}: {amount}")
        if amount != seed_price:
            logger.warning(f"Invalid amount entered by user {user_id}: {amount}, expected {seed_price}")
            await update.message.reply_text(
                messages[lang]["invalid_amount"].format(seed_price),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return DEPOSIT_AMOUNT
        context.user_data["amount"] = amount
        await update.message.reply_text(
            messages[lang]["choose_network"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("TRC20", callback_data="network_TRC20")],
                [InlineKeyboardButton("BEP20", callback_data="network_BEP20")],
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
            ])
        )
        logger.info(f"Sent network selection message to user {user_id}")
        return DEPOSIT_NETWORK
    except ValueError as e:
        logger.warning(f"Invalid amount format by user {user_id}: '{input_text}', error: {e}")
        await update.message.reply_text(
            messages[lang]["invalid_amount"].format(seed_price),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
            ])
        )
        return DEPOSIT_AMOUNT
    except Exception as e:
        logger.error(f"Error in handle_deposit_amount for user {user_id}: {e}", exc_info=True)
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
    logger.info(f"User {user_id} triggered deposit network callback: {query.data}")

    try:
        if query.data.startswith("network_"):
            network = query.data.split("_")[1]
            if network not in wallet_addresses:
                await query.message.reply_text(
                    messages[lang]["error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            context.user_data["network"] = network
            await query.message.reply_text(
                messages[lang]["wallet"](network, wallet_addresses[network]),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
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

async def handle_deposit_txid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit TXID or screenshot submission."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    amount = context.user_data.get("amount")
    network = context.user_data.get("network")
    seed_idx = context.user_data.get("seed_idx")
    logger.info(f"User {user_id} submitted TXID or screenshot")

    if not all([amount, network, seed_idx is not None]):
        await update.message.reply_text(
            messages[lang]["invalid_data"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

    try:
        seed = SEEDS[seed_idx]
        message_id = update.message.message_id
        
        # Insert transaction
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('SELECT seed_id FROM seeds WHERE name = %s', (seed["name"],))
                result = c.fetchone()
                if not result:
                    logger.error(f"No seed found with name {seed['name']} for user {user_id}")
                    await update.message.reply_text(
                        messages[lang]["db_error"],
                        parse_mode="Markdown",
                        reply_markup=get_main_menu(lang)
                    )
                    context.user_data.clear()
                    return ConversationHandler.END
                seed_id = result[0]
                transaction_id = insert_transaction(
                    user_id, amount, network, "pending", "deposit", message_id, seed_id=seed_id
                )

        # Forward to admin
        try:
            admin_message = await context.bot.forward_message(
                chat_id=DEFAULT_ADMIN_ID,
                from_chat_id=user_id,
                message_id=message_id
            )
            # Create inline buttons for approve and reject
            keyboard = [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve_{transaction_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_{transaction_id}")
                ]
            ]
            await context.bot.send_message(
                chat_id=DEFAULT_ADMIN_ID,
                text=(
                    f"📩 *New Deposit Request*\n"
                    f"User ID: `{user_id}`\n"
                    f"Amount: `{amount}` USDT\n"
                    f"Network: `{network}`\n"
                    f"Seed: `{seed['name_fa' if lang == 'fa' else 'name']}`\n"
                    f"Transaction ID: `{transaction_id}`\n"
                    f"──────────────"
                ),
                parse_mode="Markdown",
                reply_to_message_id=admin_message.message_id,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.TelegramError as e:
            logger.error(f"Error forwarding TXID to admin for user {user_id}: {e}")
            await update.message.reply_text(
                messages[lang]["admin_error"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang)
            )
            context.user_data.clear()
            return ConversationHandler.END

        await update.message.reply_text(
            messages[lang]["success"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END
    except psycopg2.Error as e:
        logger.error(f"Database error in handle_deposit_txid for user {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["db_error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_deposit_txid for user {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

async def handle_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal amount input."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    balance = user[1] if user else 0
    logger.info(f"User {user_id} entered withdrawal amount")

    try:
        amount = float(update.message.text)
        if amount < 15:
            await update.message.reply_text(
                "⚠️ *خطا*: مقدار واردشده کمتر از حداقل مقدار برداشت (15 تتر) است!\nلطفاً مقدار معتبر وارد کنید." if lang == "fa" else
                "⚠️ *Error*: The entered amount is less than the minimum withdrawal (15 USDT)!\nPlease enter a valid amount.",
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance, bool(get_user_seeds(user_id)))
            )
            return WITHDRAW_AMOUNT
        if amount > balance:
            await update.message.reply_text(
                f"⚠️ *خطا*: موجودی کافی نیست! موجودی شما `{balance}` تتر است.\nلطفاً مقدار کمتر یا برابر با موجودی وارد کنید." if lang == "fa" else
                f"⚠️ *Error*: Insufficient balance! Your balance is `{balance}` USDT.\nPlease enter an amount less than or equal to your balance.",
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance, bool(get_user_seeds(user_id)))
            )
            return WITHDRAW_AMOUNT
        context.user_data["withdraw_amount"] = amount
        await update.message.reply_text(
            messages[lang]["choose_network_withdraw"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("TRC20", callback_data="withdraw_network_TRC20")],
                [InlineKeyboardButton("BEP20", callback_data="withdraw_network_BEP20")],
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
            ])
        )
        return WITHDRAW_NETWORK
    except ValueError:
        await update.message.reply_text(
            messages[lang]["insufficient_balance"],
            parse_mode="Markdown",
            reply_markup=get_wallet_menu(lang, balance, bool(get_user_seeds(user_id)))
        )
        return WITHDRAW_AMOUNT
    except Exception as e:
        logger.error(f"Error in handle_withdraw_amount for user {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

async def handle_withdraw_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal network selection."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} triggered withdraw network callback: {query.data}")

    try:
        if query.data.startswith("withdraw_network_"):
            network = query.data.split("_")[2]
            if network not in wallet_addresses:
                await query.message.reply_text(
                    messages[lang]["error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            context.user_data["withdraw_network"] = network
            await query.message.reply_text(
                messages[lang]["ask_withdraw_address"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
                ])
            )
            return WITHDRAW_ADDRESS
        elif query.data == "wallet":
            balance = user[1] if user else 0
            try:
                with psycopg2.connect(DATABASE_URL) as conn:
                    with conn.cursor() as c:
                        c.execute('SELECT SUM(amount) FROM profits WHERE user_id = %s', (user_id,))
                        seed_profit = c.fetchone()[0] or 0.0
                        c.execute('SELECT SUM(profit_amount) FROM referral_profits WHERE referrer_id = %s', (user_id,))
                        referral_profit = c.fetchone()[0] or 0.0
                        total_profit = seed_profit + referral_profit
                        c.execute('SELECT COUNT(*) FROM transactions WHERE user_id = %s AND status = %s', (user_id, 'confirmed'))
                        transaction_count = c.fetchone()[0]
                        c.execute('SELECT created_at FROM transactions WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT 1', (user_id, 'confirmed'))
                        last_transaction = c.fetchone()[0] if c.rowcount > 0 else None
                        c.execute('''
                            SELECT s.name, s.name_fa
                            FROM user_seeds us
                            JOIN seeds s ON us.seed_id = s.seed_id
                            WHERE us.user_id = %s
                        ''', (user_id,))
                        seeds = [row[1] if lang == "fa" else row[0] for row in c.fetchall()]
                        seeds_text = ", ".join(seeds) if seeds else None
            except psycopg2.Error as e:
                logger.error(f"Database error retrieving wallet stats for user {user_id}: {e}")
                await query.message.reply_text(
                    messages[lang]["db_error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            await query.message.reply_text(
                messages[lang]["wallet_balance"](balance, seeds_text, total_profit, transaction_count, last_transaction),
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance, bool(seeds))
            )
            return ConversationHandler.END
        else:
            await query.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang)
            )
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_withdraw_network for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END        

async def handle_withdraw_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal address input."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    amount = context.user_data.get("withdraw_amount")
    network = context.user_data.get("withdraw_network")
    address = update.message.text
    logger.info(f"User {user_id} submitted withdrawal address")

    if not all([amount, network, address]):
        await update.message.reply_text(
            messages[lang]["invalid_data"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

    try:
        message_id = update.message.message_id
        transaction_id = insert_transaction(
            user_id, amount, network, "pending", "withdrawal", message_id, address=address
        )

        # Forward to admin
        try:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve_{transaction_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_{transaction_id}")
                ]
            ]
            await context.bot.send_message(
                chat_id=DEFAULT_ADMIN_ID,
                text=(
                    f"📤 *New Withdrawal Request*\n"
                    f"User ID: `{user_id}`\n"
                    f"Amount: `{amount}` USDT\n"
                    f"Network: `{network}`\n"
                    f"Address: `{address}`\n"
                    f"Transaction ID: `{transaction_id}`\n"
                    f"──────────────"
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except telegram.error.TelegramError as e:
            logger.error(f"Error sending withdrawal request to admin for user {user_id}: {e}")
            await update.message.reply_text(
                messages[lang]["admin_error"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang)
            )
            context.user_data.clear()
            return ConversationHandler.END

        await update.message.reply_text(
            messages[lang]["withdraw_success"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END
    except psycopg2.Error as e:
        logger.error(f"Database error in handle_withdraw_address for user {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["db_error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_withdraw_address for user {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin actions (approve/reject) from inline buttons."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id != DEFAULT_ADMIN_ID:
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        await query.message.reply_text(
            messages["en"]["unauthorized"],
            parse_mode="Markdown"
        )
        return

    logger.info(f"Admin {user_id} triggered action: {query.data}")
    try:
        action, transaction_id = query.data.split("_")
        transaction_id = int(transaction_id)
        logger.info(f"Admin {user_id} attempting to {action} transaction_id {transaction_id}")

        # Retrieve transaction
        transaction = get_transaction(transaction_id)
        if not transaction:
            logger.warning(f"No pending transaction found for transaction_id {transaction_id}")
            await query.message.reply_text(
                "❌ *Error*: Transaction not found or already processed.",
                parse_mode="Markdown"
            )
            return

        # Unpack transaction
        transaction_id, target_user_id, amount, network, status, type, address, seed_id = transaction
        logger.info(f"Found transaction: id {transaction_id}, type {type}, amount {amount}, seed_id {seed_id}")

        user = get_user(target_user_id)
        lang = user[0] if user else "en"

        if action == "approve":
            if not update_transaction_status(transaction_id, "confirmed"):
                await query.message.reply_text(
                    "❌ *Error*: Transaction already processed or not found.",
                    parse_mode="Markdown"
                )
                return
            
            if type == "deposit" and seed_id:
                logger.info(f"Adding seed {seed_id} to user {target_user_id}")
                add_user_seed(target_user_id, seed_id)
                if has_referrals(target_user_id):
                    chain = get_referral_chain(target_user_id)
                    logger.info(f"Referral chain for user {target_user_id}: {chain}")
                    profit_rates = {1: 0.05, 2: 0.03, 3: 0.01}
                    for referrer_id, level in chain:
                        if level in profit_rates:
                            profit_amount = round(amount * profit_rates[level], 2)
                            logger.info(f"Recording referral profit for referrer {referrer_id}, level {level}, amount {profit_amount}")
                            update_balance(referrer_id, profit_amount)
                            record_referral_profit(referrer_id, target_user_id, transaction_id, level, profit_amount)
                            # Send notification to referrer
                            try:
                                referrer_lang = get_user(referrer_id)[0] or "en"
                                await context.bot.send_message(
                                    chat_id=referrer_id,
                                    text=messages[referrer_lang]["referral_profit_notification"](profit_amount, target_user_id, level),
                                    parse_mode="Markdown"
                                )
                                logger.info(f"Sent referral profit notification to referrer {referrer_id}")
                            except telegram.error.TelegramError as e:
                                logger.error(f"Failed to send referral profit notification to referrer {referrer_id}: {e}")
                                await context.bot.send_message(
                                    chat_id=DEFAULT_ADMIN_ID,
                                    text=f"⚠️ *Warning*: Failed to notify referrer {referrer_id} about profit {profit_amount}: {e}",
                                    parse_mode="Markdown"
                                )
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=messages[lang]["confirmed"],
                        parse_mode="Markdown",
                        reply_markup=get_main_menu(lang)
                    )
                    logger.info(f"Sent confirmation message to user {target_user_id}")
                except telegram.error.TelegramError as e:
                    logger.error(f"Failed to send confirmation message to user {target_user_id}: {e}")
                    await context.bot.send_message(
                        chat_id=DEFAULT_ADMIN_ID,
                        text=f"⚠️ *Warning*: Transaction approved for user {target_user_id}, but failed to notify user: {e}",
                        parse_mode="Markdown"
                    )
            elif type == "withdrawal":
                logger.info(f"Deducting {amount} from user {target_user_id} balance")
                update_balance(target_user_id, -amount)
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=messages[lang]["withdraw_confirmed"],
                        parse_mode="Markdown",
                        reply_markup=get_main_menu(lang)
                    )
                    logger.info(f"Sent withdrawal confirmation message to user {target_user_id}")
                except telegram.error.TelegramError as e:
                    logger.error(f"Failed to send withdrawal confirmation to user {target_user_id}: {e}")
                    await context.bot.send_message(
                        chat_id=DEFAULT_ADMIN_ID,
                        text=f"⚠️ *Warning*: Withdrawal approved for user {target_user_id}, but failed to notify user: {e}",
                        parse_mode="Markdown"
                    )

            await query.message.reply_text(
                f"✅ *Transaction Approved* (ID: {transaction_id})",
                parse_mode="Markdown"
            )
            logger.info(f"Transaction {transaction_id} approved successfully")
        elif action == "reject":
            if not update_transaction_status(transaction_id, "rejected"):
                await query.message.reply_text(
                    "❌ *Error*: Transaction already processed or not found.",
                    parse_mode="Markdown"
                )
                return
            
            if type == "deposit":
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=messages[lang]["rejected"],
                        parse_mode="Markdown",
                        reply_markup=get_main_menu(lang)
                    )
                    logger.info(f"Sent rejection message to user {target_user_id} for deposit")
                except telegram.error.TelegramError as e:
                    logger.error(f"Failed to send rejection message to user {target_user_id}: {e}")
                    await context.bot.send_message(
                        chat_id=DEFAULT_ADMIN_ID,
                        text=f"⚠️ *Warning*: Deposit rejected for user {target_user_id}, but failed to notify user: {e}",
                        parse_mode="Markdown"
                    )
            elif type == "withdrawal":
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=messages[lang]["withdraw_rejected"],
                        parse_mode="Markdown",
                        reply_markup=get_main_menu(lang)
                    )
                    logger.info(f"Sent withdrawal rejection message to user {target_user_id}")
                except telegram.error.TelegramError as e:
                    logger.error(f"Failed to send withdrawal rejection to user {target_user_id}: {e}")
                    await context.bot.send_message(
                        chat_id=DEFAULT_ADMIN_ID,
                        text=f"⚠️ *Warning*: Withdrawal rejected for user {target_user_id}, but failed to notify user: {e}",
                        parse_mode="Markdown"
                    )

            await query.message.reply_text(
                f"❌ *Transaction Rejected* (ID: {transaction_id})",
                parse_mode="Markdown"
            )
            logger.info(f"Transaction {transaction_id} rejected successfully")
        else:
            logger.error(f"Invalid action for transaction_id {transaction_id}: {action}")
            await query.message.reply_text(
                "❌ *Error*: Invalid action.",
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Error in handle_admin_action for transaction_id {transaction_id}: {e}")
        await query.message.reply_text(
            f"❌ *Error*: {str(e)}",
            parse_mode="Markdown"
        )

async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back button callbacks."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} triggered back callback: {query.data}")

    try:
        if query.data == "back_to_menu":
            context.user_data.clear()
            await query.message.reply_text(
                messages[lang]["main_menu"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang)
            )
            return ConversationHandler.END
        elif query.data == "wallet":
            balance = user[1] if user else 0
            try:
                with psycopg2.connect(DATABASE_URL) as conn:
                    with conn.cursor() as c:
                        # جمع سود از جدول profits
                        c.execute('SELECT SUM(amount) FROM profits WHERE user_id = %s', (user_id,))
                        seed_profit = c.fetchone()[0] or 0.0
                        # جمع سود از جدول referral_profits
                        c.execute('SELECT SUM(profit_amount) FROM referral_profits WHERE referrer_id = %s', (user_id,))
                        referral_profit = c.fetchone()[0] or 0.0
                        total_profit = seed_profit + referral_profit
                        c.execute('SELECT COUNT(*) FROM transactions WHERE user_id = %s AND status = %s', (user_id, 'confirmed'))
                        transaction_count = c.fetchone()[0]
                        c.execute('SELECT created_at FROM transactions WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT 1', (user_id, 'confirmed'))
                        last_transaction = c.fetchone()[0] if c.rowcount > 0 else None
                        c.execute('''
                            SELECT s.name, s.name_fa
                            FROM user_seeds us
                            JOIN seeds s ON us.seed_id = s.seed_id
                            WHERE us.user_id = %s
                        ''', (user_id,))
                        seeds = [row[1] if lang == "fa" else row[0] for row in c.fetchall()]
                        seeds_text = ", ".join(seeds) if seeds else None
            except psycopg2.Error as e:
                logger.error(f"Database error retrieving wallet stats for user {user_id}: {e}")
                await query.message.reply_text(
                    messages[lang]["db_error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            await query.message.reply_text(
                messages[lang]["wallet_balance"](balance, seeds_text, total_profit, transaction_count, last_transaction),
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance, bool(seeds))
            )
            return ConversationHandler.END
        else:
            logger.warning(f"Unhandled back callback data for user {user_id}: {query.data}")
            await query.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang)
            )
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_back for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END        

async def approve_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle transaction approval by admin."""
    user_id = update.effective_user.id
    if user_id != DEFAULT_ADMIN_ID:
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        await update.message.reply_text(
            messages["en"]["unauthorized"],
            parse_mode="Markdown"
        )
        return

    command_text = update.message.text
    logger.info(f"Received /approve command from admin {user_id}: {command_text}")
    try:
        command = command_text.split("_")
        if len(command) != 2:
            logger.error(f"Invalid approve command format: {command_text}")
            await update.message.reply_text(
                "❌ *Error*: Invalid command format. Use /approve_{transaction_id}",
                parse_mode="Markdown"
            )
            return
        transaction_id = int(command[1])
        logger.info(f"Admin {user_id} attempting to approve transaction_id {transaction_id}")

        transaction = get_transaction(transaction_id)
        if not transaction:
            logger.warning(f"No pending transaction found for transaction_id {transaction_id}")
            await update.message.reply_text(
                "❌ *Error*: Transaction not found or already processed.",
                parse_mode="Markdown"
            )
            return

        transaction_id, target_user_id, amount, network, status, type, address, seed_id = transaction
        logger.info(f"Found transaction: id {transaction_id}, type {type}, amount {amount}, seed_id {seed_id}")

        if not update_transaction_status(transaction_id, "confirmed"):
            await update.message.reply_text(
                "❌ *Error*: Transaction already processed or not found.",
                parse_mode="Markdown"
            )
            return
        
        user = get_user(target_user_id)
        lang = user[0] if user else "en"
        if type == "deposit" and seed_id:
            logger.info(f"Adding seed {seed_id} to user {target_user_id}")
            add_user_seed(target_user_id, seed_id)
            if has_referrals(target_user_id):
                chain = get_referral_chain(target_user_id)
                logger.info(f"Referral chain for user {target_user_id}: {chain}")
                profit_rates = {1: 0.05, 2: 0.03, 3: 0.01}
                for referrer_id, level in chain:
                    if level in profit_rates:
                        profit_amount = round(amount * profit_rates[level], 2)
                        logger.info(f"Recording referral profit for referrer {referrer_id}, level {level}, amount {profit_amount}")
                        update_balance(referrer_id, profit_amount)
                        record_referral_profit(referrer_id, target_user_id, transaction_id, level, profit_amount)
                        # Send notification to referrer
                        try:
                            referrer_lang = get_user(referrer_id)[0] or "en"
                            await context.bot.send_message(
                                chat_id=referrer_id,
                                text=messages[referrer_lang]["referral_profit_notification"](profit_amount, target_user_id, level),
                                parse_mode="Markdown"
                            )
                            logger.info(f"Sent referral profit notification to referrer {referrer_id}")
                        except telegram.error.TelegramError as e:
                            logger.error(f"Failed to send referral profit notification to referrer {referrer_id}: {e}")
                            await context.bot.send_message(
                                chat_id=DEFAULT_ADMIN_ID,
                                text=f"⚠️ *Warning*: Failed to notify referrer {referrer_id} about profit {profit_amount}: {e}",
                                parse_mode="Markdown"
                            )
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=messages[lang]["confirmed"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                logger.info(f"Sent confirmation message to user {target_user_id}")
            except telegram.error.TelegramError as e:
                logger.error(f"Failed to send confirmation message to user {target_user_id}: {e}")
                await context.bot.send_message(
                    chat_id=DEFAULT_ADMIN_ID,
                    text=f"⚠️ *Warning*: Transaction approved for user {target_user_id}, but failed to notify user: {e}",
                    parse_mode="Markdown"
                )
        elif type == "withdrawal":
            logger.info(f"Deducting {amount} from user {target_user_id} balance")
            update_balance(target_user_id, -amount)
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=messages[lang]["withdraw_confirmed"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                logger.info(f"Sent withdrawal confirmation message to user {target_user_id}")
            except telegram.error.TelegramError as e:
                logger.error(f"Failed to send withdrawal confirmation to user {target_user_id}: {e}")
                await context.bot.send_message(
                    chat_id=DEFAULT_ADMIN_ID,
                    text=f"⚠️ *Warning*: Withdrawal approved for user {target_user_id}, but failed to notify user: {e}",
                    parse_mode="Markdown"
                )

        await update.message.reply_text(
            f"✅ *Transaction Approved* (ID: {transaction_id})",
            parse_mode="Markdown"
        )
        logger.info(f"Transaction {transaction_id} approved successfully")
    except Exception as e:
        logger.error(f"Error in approve_transaction for transaction_id {transaction_id}: {e}")
        await update.message.reply_text(
            f"❌ *Error*: {str(e)}",
            parse_mode="Markdown"
        )

async def reject_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle transaction rejection by admin."""
    user_id = update.effective_user.id
    if user_id != DEFAULT_ADMIN_ID:
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        await update.message.reply_text(
            messages["en"]["unauthorized"],
            parse_mode="Markdown"
        )
        return

    command_text = update.message.text
    logger.info(f"Received /reject command from admin {user_id}: {command_text}")
    try:
        command = command_text.split("_")
        if len(command) != 2:
            logger.error(f"Invalid reject command format: {command_text}")
            await update.message.reply_text(
                "❌ *Error*: Invalid command format. Use /reject_{transaction_id}",
                parse_mode="Markdown"
            )
            return
        transaction_id = int(command[1])
        logger.info(f"Admin {user_id} attempting to reject transaction_id {transaction_id}")

        # Retrieve transaction
        transaction = get_transaction(transaction_id)
        if not transaction:
            logger.warning(f"No pending transaction found for transaction_id {transaction_id}")
            await update.message.reply_text(
                "❌ *Error*: Transaction not found or already processed.",
                parse_mode="Markdown"
            )
            return

        # Unpack transaction
        transaction_id, target_user_id, amount, network, status, type, address, seed_id = transaction
        logger.info(f"Found transaction: id {transaction_id}, type {type}, amount {amount}, seed_id {seed_id}")

        # Update transaction status
        if not update_transaction_status(transaction_id, "rejected"):
            await update.message.reply_text(
                "❌ *Error*: Transaction already processed or not found.",
                parse_mode="Markdown"
            )
            return
        
        # Notify user
        user = get_user(target_user_id)
        lang = user[0] if user else "en"
        if type == "deposit":
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=messages[lang]["rejected"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                logger.info(f"Sent rejection message to user {target_user_id} for deposit")
            except telegram.error.TelegramError as e:
                logger.error(f"Failed to send rejection message to user {target_user_id}: {e}")
                await context.bot.send_message(
                    chat_id=DEFAULT_ADMIN_ID,
                    text=f"⚠️ *Warning*: Deposit rejected for user {target_user_id}, but failed to notify user: {e}",
                    parse_mode="Markdown"
                )
        elif type == "withdrawal":
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=messages[lang]["withdraw_rejected"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                logger.info(f"Sent withdrawal rejection message to user {target_user_id}")
            except telegram.error.TelegramError as e:
                logger.error(f"Failed to send withdrawal rejection to user {target_user_id}: {e}")
                await context.bot.send_message(
                    chat_id=DEFAULT_ADMIN_ID,
                    text=f"⚠️ *Warning*: Withdrawal rejected for user {target_user_id}, but failed to notify user: {e}",
                    parse_mode="Markdown"
                )

        await update.message.reply_text(
            f"❌ *Transaction Rejected* (ID: {transaction_id})",
            parse_mode="Markdown"
        )
        logger.info(f"Transaction {transaction_id} rejected successfully")
    except Exception as e:
        logger.error(f"Error in reject_transaction for transaction_id {transaction_id}: {e}")
        await update.message.reply_text(
            f"❌ *Error*: {str(e)}",
            parse_mode="Markdown"
        )

async def test_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test if admin can execute approve commands."""
    user_id = update.effective_user.id
    if user_id != DEFAULT_ADMIN_ID:
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        await update.message.reply_text(
            messages["en"]["unauthorized"],
            parse_mode="Markdown"
        )
        return

    logger.info(f"Admin {user_id} executed /test_approve")
    try:
        await update.message.reply_text(
            "✅ *Test Approve Command*\nThis command works! Please try an actual /approve_{user_id}_{message_id} command.",
            parse_mode="Markdown"
        )
        logger.info(f"Admin {user_id} successfully tested approve command")
    except Exception as e:
        logger.error(f"Error in test_approve for admin {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ *Error*: {str(e)}",
            parse_mode="Markdown"
        )


def update_transaction_status(transaction_id, status):
    """Update transaction status using transaction ID."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    UPDATE transactions
                    SET status = %s
                    WHERE id = %s AND status = 'pending'
                ''', (status, transaction_id))
                if c.rowcount == 0:
                    logger.warning(f"No pending transaction found for transaction_id {transaction_id} to update to {status}")
                    return False
                conn.commit()
                logger.info(f"Updated transaction status for transaction_id {transaction_id} to {status}")
                return True
    except Exception as e:
        logger.error(f"Error updating transaction status for transaction_id {transaction_id}: {e}")
        raise

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} cancelled operation")
    
    context.user_data.clear()
    await update.message.reply_text(
        messages[lang]["cancel"].replace(
            "برای بازگشت به منوی مزرعه، /start رو وارد کنید.",
            "به منوی اصلی مزرعه برگشتید. گزینه مورد نظر را انتخاب کنید:"
        ) if lang == "fa" else
        messages[lang]["cancel"].replace(
            "To return to the farm menu, use /start.",
            "Returned to the main farm menu. Choose an option:"
        ),
        parse_mode="Markdown",
        reply_markup=get_main_menu(lang)
    )
    return ConversationHandler.END

async def handle_unexpected_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unexpected messages during conversation."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} sent unexpected message")

    await update.message.reply_text(
        messages[lang]["unexpected_message"],
        parse_mode="Markdown",
        reply_markup=get_main_menu(lang)
    )
    return ConversationHandler.END

async def debug_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await update.message.reply_text("🚫 Unauthorized")
        return
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('SELECT referrer_id, referred_id, level FROM referrals WHERE referrer_id = %s', (user_id,))
                referrals = c.fetchall()
                if referrals:
                    response = "\n".join([f"Referrer: {r[0]}, Referred: {r[1]}, Level: {r[2]}" for r in referrals])
                else:
                    response = "No referrals found."
                await update.message.reply_text(f"Referrals:\n{response}")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def debug_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug balance and referral profits for a user."""
    user_id = update.effective_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await update.message.reply_text("🚫 Unauthorized")
        return
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # گرفتن بالانس
                c.execute('SELECT balance FROM users WHERE user_id = %s', (user_id,))
                balance = c.fetchone()[0] or 0.0
                # گرفتن سود بذرها
                c.execute('SELECT SUM(amount) FROM profits WHERE user_id = %s', (user_id,))
                seed_profit = c.fetchone()[0] or 0.0
                # گرفتن سود رفرال‌ها
                c.execute('SELECT SUM(profit_amount) FROM referral_profits WHERE referrer_id = %s', (user_id,))
                referral_profit = c.fetchone()[0] or 0.0
                # گرفتن جزئیات سود رفرال‌ها
                c.execute('''
                    SELECT referred_id, profit_amount, level, created_at
                    FROM referral_profits
                    WHERE referrer_id = %s
                    ORDER BY created_at DESC
                ''', (user_id,))
                referral_details = c.fetchall()
                referral_text = "\n".join(
                    f"Referred ID: {row[0]}, Profit: {row[1]} USDT, Level: {row[2]}, Date: {row[3]}"
                    for row in referral_details
                ) if referral_details else "No referral profits found."
                response = (
                    f"Debug Balance for User {user_id}:\n"
                    f"Balance: {balance} USDT\n"
                    f"Seed Profits: {seed_profit} USDT\n"
                    f"Referral Profits: {referral_profit} USDT\n"
                    f"Total Profits: {seed_profit + referral_profit} USDT\n"
                    f"Referral Profit Details:\n{referral_text}"
                )
                await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Error debugging balance for user {user_id}: {e}")
        await update.message.reply_text(f"Error: {str(e)}")        

def main():
    """Run the bot."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not found in environment variables")
        exit(1)

    # Initialize database and fix users table
    init_db()
    fix_users_table()
    logger.info("Database initialization and users table fix completed")

    app = ApplicationBuilder().token(token).build()

    # Run fix_database for user 5664533861 at startup
    fix_database(5664533861)
    logger.info("Ran fix_database for user 5664533861")

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(
                handle_menu_callback,
                pattern=r"^(buy_seed|wallet|referral|language|support|withdraw|history|plant_seed|harvest_seed|referral_\d+)$"
            ),
            CallbackQueryHandler(handle_language_callback, pattern=r"^lang_.*$"),
            CallbackQueryHandler(handle_seed_selection, pattern=r"^(seed_\d+|confirm_seed_purchase|balance_purchase)$"),
            CallbackQueryHandler(handle_deposit_network, pattern=r"^network_.*$"),
            CallbackQueryHandler(handle_plant_seed, pattern=r"^plant_\d+$"),
            CallbackQueryHandler(handle_harvest_seed, pattern=r"^harvest_\d+$"),
            CallbackQueryHandler(handle_admin_action, pattern=r"^(approve|reject)_\d+$"),
            CallbackQueryHandler(handle_balance_purchase, pattern=r"^confirm_balance_purchase$"),
            CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
        ],
        states={
            SELECT_SEED: [
                CallbackQueryHandler(
                    handle_seed_selection,
                    pattern=r"^(seed_\d+|confirm_seed_purchase|balance_purchase)$"
                ),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            DEPOSIT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deposit_amount),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            DEPOSIT_NETWORK: [
                CallbackQueryHandler(
                    handle_deposit_network,
                    pattern=r"^network_.*$"
                ),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            DEPOSIT_TXID: [
                MessageHandler(filters.TEXT | filters.PHOTO, handle_deposit_txid),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            WITHDRAW_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_withdraw_amount),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            WITHDRAW_NETWORK: [
                CallbackQueryHandler(
                    handle_withdraw_network,
                    pattern=r"^withdraw_network_.*$"
                ),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            WITHDRAW_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_withdraw_address),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            PLANT_SEED: [
                CallbackQueryHandler(
                    handle_plant_seed,
                    pattern=r"^plant_\d+$"
                ),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            HARVEST_SEED: [
                CallbackQueryHandler(
                    handle_harvest_seed,
                    pattern=r"^harvest_\d+$"
                ),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            CONFIRM_BALANCE_PURCHASE: [
                CallbackQueryHandler(
                    handle_balance_purchase,
                    pattern=r"^confirm_balance_purchase$"
                ),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", cancel),  # اضافه کردن هندلر برای /start
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message),
        ],
        per_message=False
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler(
        "approve",
        approve_transaction,
        filters=filters.Regex(r'^/approve_\d+$')
    ))
    app.add_handler(CommandHandler(
        "reject",
        reject_transaction,
        filters=filters.Regex(r'^/reject_\d+$')
    ))
    app.add_handler(CommandHandler("test_approve", test_approve))
    app.add_handler(CommandHandler("db_test", db_test))
    app.add_handler(CommandHandler("admintest", admin_test))
    app.add_handler(CommandHandler("checkseeds", check_seeds))
    app.add_handler(CommandHandler("test_referral_profit", test_referral_profit))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("debug_referrals", debug_referrals))
    app.add_handler(CommandHandler("debug_balance", debug_balance))

    logger.info("Starting bot")
    app.run_polling()

if __name__ == "__main__":
    main()
