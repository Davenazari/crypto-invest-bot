import logging
import os
import psycopg2
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
SELECT_SEED, DEPOSIT_AMOUNT, DEPOSIT_NETWORK, DEPOSIT_TXID, WITHDRAW_AMOUNT, WITHDRAW_ADDRESS, PLANT_SEED, HARVEST_SEED = range(8)

# Default admin ID
DEFAULT_ADMIN_ID = 536587863  # Changed to integer

# Supported languages
langs = {"فارسی": "fa", "English": "en"}

# Seed data
SEEDS = [
    {"name": "Tomato", "name_fa": "گوجه", "price": 15, "daily_profit_rate": 0.001},
    {"name": "Cucumber", "name_fa": "خیار", "price": 30, "daily_profit_rate": 0.0015},
    {"name": "Orange", "name_fa": "پرتغال", "price": 50, "daily_profit_rate": 0.002},
    {"name": "Apple", "name_fa": "سیب", "price": 120, "daily_profit_rate": 0.0028},
    {"name": "Banana", "name_fa": "موز", "price": 320, "daily_profit_rate": 0.004},
    {"name": "Mango", "name_fa": "انبه", "price": 550, "daily_profit_rate": 0.005},
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
            "🌱 *انتخاب بذر*\n"
            "لطفاً بذری که می‌خواهید بخرید رو انتخاب کنید:\n"
            "👇 یکی از بذرهای زیر رو انتخاب کنید 👇"
        ),
        "seed_info": lambda name, price, daily_profit, weekly_profit, monthly_profit, total_monthly: (
            f"🌾 *بذر {name}*\n"
            f"────────────────────\n"
            f"💰 *قیمت*: `{price}` تتر\n"
            f"📆 *سود روزانه*: `{daily_profit}` تتر\n"
            f"📅 *سود هفتگی*: `{weekly_profit}` تتر\n"
            f"🗓️ *سود ماهانه*: `{monthly_profit}` تتر\n"
            f"💸 *مجموع (اصل + سود ماهانه)*: `{total_monthly}` تتر\n"
            f"────────────────────\n"
            f"🌱 آماده خرید این بذر هستید؟"
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
            f"🌾 *مزرعه شما*\n"
            f"────────────────────\n"
            f"💰 *موجودی*: `{balance}` تتر\n"
            f"🌱 *بذرهای شما*: {seeds or 'هیچ بذری ندارید'}\n"
            f"📈 *کل سود کسب‌شده*: `{total_profit}` تتر\n"
            f"📝 *تراکنش‌های موفق*: `{transaction_count}`\n"
            f"⏰ *آخرین تراکنش*: {'ندارد' if not last_transaction else last_transaction}\n"
            f"────────────────────\n"
            f"📌 برای کاشت، برداشت یا خرید بذر جدید، گزینه‌های زیر رو انتخاب کنید."
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
            "🤝 *دعوت کارگر به مزرعه*\n"
            "لطفاً یک گزینه انتخاب کنید:"
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
        "plant_seed": (
            "🌱 *کاشت بذر*\n"
            "لطفاً بذری که می‌خواهید امروز بکارید رو انتخاب کنید:\n"
            "👇 یکی از بذرهای زیر رو انتخاب کنید 👇"
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
            "🚜 *برداشت سود*\n"
            "لطفاً بذری که می‌خواهید سودش رو برداشت کنید انتخاب کنید:\n"
            "👇 یکی از بذرهای زیر رو انتخاب کنید 👇"
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
            "🌱 *Select Seed*\n"
            "Please choose the seed you want to buy:\n"
            "👇 Choose one of the seeds below 👇"
        ),
        "seed_info": lambda name, price, daily_profit, weekly_profit, monthly_profit, total_monthly: (
            f"🌾 *{name} Seed*\n"
            f"────────────────────\n"
            f"💰 *Price*: `{price}` USDT\n"
            f"📆 *Daily Profit*: `{daily_profit}` USDT\n"
            f"📅 *Weekly Profit*: `{weekly_profit}` USDT\n"
            f"🗓️ *Monthly Profit*: `{monthly_profit}` USDT\n"
            f"💸 *Total (Principal + Monthly Profit)*: `{total_monthly}` USDT\n"
            f"────────────────────\n"
            f"🌱 Ready to buy this seed?"
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
            f"🌾 *Your Farm*\n"
            f"────────────────────\n"
            f"💰 *Balance*: `{balance}` USDT\n"
            f"🌱 *Your Seeds*: {seeds or 'No seeds yet'}\n"
            f"📈 *Total Profit Earned*: `{total_profit}` USDT\n"
            f"📝 *Successful Transactions*: `{transaction_count}`\n"
            f"⏰ *Last Transaction*: {'None' if not last_transaction else last_transaction}\n"
            f"────────────────────\n"
            f"📌 Choose an option to plant, harvest, or buy new seeds."
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
            "🤝 *Invite Farm Workers*\n"
            "Please select an option:"
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
        "plant_seed": (
            "🌱 *Plant Seed*\n"
            "Please choose the seed you want to plant today:\n"
            "👇 Choose one of the seeds below 👇"
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
            "🚜 *Harvest Profit*\n"
            "Please choose the seed you want to harvest profit from:\n"
            "👇 Choose one of the seeds below 👇"
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
    """Initialize database tables."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # Users table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        language TEXT DEFAULT 'en',
                        balance REAL DEFAULT 0.0
                    )
                ''')
                # Seeds table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS seeds (
                        seed_id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        name_fa TEXT NOT NULL,
                        price REAL NOT NULL,
                        daily_profit_rate REAL NOT NULL
                    )
                ''')
                # User seeds table
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
                # Transactions table
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
                # Referrals table
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
                # Referral profits table
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
                # Profits table
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
                # Populate seeds table if empty
                c.execute('SELECT COUNT(*) FROM seeds')
                if c.fetchone()[0] == 0:
                    for seed in SEEDS:
                        c.execute('''
                            INSERT INTO seeds (name, name_fa, price, daily_profit_rate)
                            VALUES (%s, %s, %s, %s)
                        ''', (seed["name"], seed["name_fa"], seed["price"], seed["daily_profit_rate"]))
                # Check if seeds table is populated
                c.execute('SELECT COUNT(*) FROM seeds')
                seed_count = c.fetchone()[0]
                if seed_count == 0:
                    logger.error("Seeds table is empty after initialization")
                    # Optionally notify admin
                    try:
                        bot = telegram.Bot(token=os.getenv("BOT_TOKEN"))
                        bot.send_message(
                            chat_id=DEFAULT_ADMIN_ID,
                            text="⚠️ *Error*: Seeds table is empty after database initialization. Please check the database.",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify admin about empty seeds table: {e}")
                # Check if seed_id column exists in transactions table
                c.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'transactions' AND column_name = 'seed_id'
                """)
                if not c.fetchone():
                    c.execute('''
                        ALTER TABLE transactions
                        ADD COLUMN seed_id INTEGER
                    ''')
                    c.execute('''
                        ALTER TABLE transactions
                        ADD CONSTRAINT transactions_seed_id_fkey
                        FOREIGN KEY (seed_id) REFERENCES seeds (seed_id)
                    ''')
                    logger.info("Added seed_id column and foreign key to transactions table")
                conn.commit()
                logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
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
                    SELECT t.amount, t.network, t.status, t.type, t.created_at, r.level, s.name, s.name_fa
                    FROM transactions t
                    JOIN referrals r ON t.user_id = r.referred_id
                    LEFT JOIN seeds s ON t.seed_id = s.seed_id
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
                return c.fetchone()
    except Exception as e:
        logger.error(f"Error getting user seed {user_seed_id} for user {user_id}: {e}")
        return None

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

def can_harvest_seed(last_planted, last_harvested):
    """Check if a seed can be harvested (temporary test mode)."""
    # برای تست، بذر گوجه (ID: 2) همیشه قابل برداشت است
    return True  # این خط برای تست موقت اضافه شده
    # کد اصلی (برای بعد از تست برگردون به این)
    if not last_planted:
        return False
    last_planted_dt = datetime.fromisoformat(last_planted).astimezone(pytz.timezone('Asia/Tehran'))
    now = datetime.now(pytz.timezone('Asia/Tehran'))
    
    if last_harvested:
        last_harvested_dt = datetime.fromisoformat(last_harvested).astimezone(pytz.timezone('Asia/Tehran'))
        if last_harvested_dt.date() >= last_planted_dt.date():
            return False
    
    return now.date() > last_planted_dt.date()

# Menu generation
def get_main_menu(lang):
    """Generate main menu keyboard."""
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

def get_seed_selection_menu(lang):
    """Generate seed selection keyboard."""
    buttons = [
        [InlineKeyboardButton(seed["name_fa" if lang == "fa" else "name"], callback_data=f"seed_{idx}")]
        for idx, seed in enumerate(SEEDS)
    ]
    buttons.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)

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
        ]
    ]
    if balance >= 15:
        buttons.append([InlineKeyboardButton("💸 برداشت" if lang == "fa" else "💸 Withdraw", callback_data="withdraw")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)

def get_referral_menu(lang):
    """Generate referral menu keyboard."""
    return InlineKeyboardMarkup([
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
    """Handle /start command."""
    user_id = update.effective_user.id
    args = context.args
    logger.info(f"User {user_id} called /start with args: {args}")
    
    try:
        context.user_data.clear()
        logger.info(f"Cleared user_data for user {user_id}")
        
        referred_by = None
        if args and args[0].startswith("ref_"):
            try:
                referred_by = int(args[0].split("_")[1])
                if referred_by == user_id:
                    referred_by = None
                logger.info(f"Referral detected for user {user_id}: referred_by {referred_by}")
            except (IndexError, ValueError):
                logger.warning(f"Invalid referral code for user {user_id}: {args[0]}")
        
        user = get_user(user_id)
        lang = user[0] if user else "en"
        logger.info(f"User {user_id} language: {lang}, user_data: {user}")
        if not user:
            logger.info(f"Creating new user {user_id} with referred_by {referred_by}")
            upsert_user(user_id, language="en", referred_by=referred_by)
            if referred_by:
                add_referral(referred_by, user_id, 1)
                chain = get_referral_chain(referred_by)
                for referrer_id, level in chain:
                    if level < 3:
                        add_referral(referrer_id, user_id, level + 1)
        
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
                for seed in user_seeds if can_harvest_seed(seed[4], seed[5])
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
            context.user_data.clear()
            if balance < 15:
                await query.message.reply_text(
                    messages[lang]["insufficient_balance"],
                    parse_mode="Markdown",
                    reply_markup=get_wallet_menu(lang, balance, bool(get_user_seeds(user_id)))
                )
                return ConversationHandler.END
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


async def handle_seed_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle seed selection for purchase."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} triggered seed selection callback: {query.data}")

    try:
        if query.data.startswith("seed_"):
            seed_idx = int(query.data.split("_")[1])
            seed = SEEDS[seed_idx]
            daily_profit = round(seed["price"] * seed["daily_profit_rate"], 2)
            weekly_profit = round(daily_profit * 7, 2)
            monthly_profit = round(daily_profit * 30, 2)
            total_monthly = round(seed["price"] + monthly_profit, 2)
            context.user_data["seed_idx"] = seed_idx
            context.user_data["seed_price"] = seed["price"]
            await query.message.reply_text(
                messages[lang]["seed_info"](
                    seed["name_fa" if lang == "fa" else "name"],
                    seed["price"],
                    daily_profit,
                    weekly_profit,
                    monthly_profit,
                    total_monthly
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ خرید" if lang == "fa" else "✅ Buy", callback_data="confirm_seed_purchase")],
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return SELECT_SEED
        elif query.data == "confirm_seed_purchase":
            seed_idx = context.user_data.get("seed_idx")
            seed_price = context.user_data.get("seed_price")
            if seed_idx is None or seed_price is None:
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
        logger.error(f"Error in handle_seed_selection for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
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
        elif query.data == "back_to_menu":
            context.user_data.clear()
            await query.message.reply_text(
                messages[lang]["main_menu"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang)
            )
            return ConversationHandler.END
        else:
            logger.warning(f"Unhandled plant seed callback data for user {user_id}: {query.data}")
            await query.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang)
            )
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_plant_seed for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        context.user_data.clear()
        return ConversationHandler.END

async def handle_harvest_seed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle seed harvesting by user."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_seed_id = int(query.data.split("_")[1])  # Use user_seed_id (id from user_seeds)
    logger.info(f"User {user_id} triggered harvest seed callback: harvest_{user_seed_id}")

    try:
        # Get user seed
        user_seed = get_user_seed(user_id, user_seed_id)
        if not user_seed:
            logger.warning(f"User {user_id} does not own seed with user_seed_id {user_seed_id}")
            user = get_user(user_id)
            lang = user[0] if user else "en"
            await query.message.reply_text(
                messages[lang]["no_seeds"],
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, user[1] if user else 0, True)
            )
            return ConversationHandler.END

        # Unpack seed data
        seed_id, last_planted, last_harvested, price, daily_profit_rate = user_seed

        # Check if seed can be harvested
        if not can_harvest_seed(last_planted, last_harvested):
            logger.info(f"Seed {seed_id} not ready for harvest by user {user_id}")
            user = get_user(user_id)
            lang = user[0] if user else "en"
            await query.message.reply_text(
                messages[lang]["harvest_not_ready"],
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, user[1] if user else 0, True)
            )
            return ConversationHandler.END

        # Calculate daily profit
        profit_amount = round(price * daily_profit_rate, 3)  # Daily profit
        current_time = dt.datetime.now(dt.UTC).isoformat()

        # Update last harvested time
        update_seed_harvest(user_id, user_seed_id)
        logger.info(f"Updated last harvested for user {user_id}, seed {seed_id}")

        # Update user balance
        update_balance(user_id, profit_amount)
        logger.info(f"Updated balance for user {user_id}: added {profit_amount}")

        # Record profit in profits table
        insert_profit(user_id, seed_id, profit_amount, "daily")
        logger.info(f"Inserted profit for user {user_id}: seed_id {seed_id}, amount {profit_amount}")

        # Notify user
        user = get_user(user_id)
        lang = user[0] if user else "en"
        await query.message.reply_text(
            messages[lang]["harvest_success"](profit_amount),
            parse_mode="Markdown",
            reply_markup=get_wallet_menu(lang, user[1] if user else 0, True)
        )
        logger.info(f"Sent harvest success message to user {user_id}")
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in handle_harvest_seed for user {user_id}: {e}")
        user = get_user(user_id)
        lang = user[0] if user else "en"
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_wallet_menu(lang, user[1] if user else 0, True)
        )
        return ConversationHandler.END
    
async def check_seeds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check seeds for user 5664533861 (temporary for debugging)."""
    user_id = update.effective_user.id
    if user_id != 5664533861:  # فقط برای کاربر خاص
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
        if amount < 15 or amount > balance:
            await update.message.reply_text(
                messages[lang]["insufficient_balance"],
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance, bool(get_user_seeds(user_id)))
            )
            return WITHDRAW_AMOUNT
        context.user_data["withdraw_amount"] = amount
        await update.message.reply_text(
            messages[lang]["ask_withdraw_address"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="wallet")]
            ])
        )
        return WITHDRAW_ADDRESS
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

async def handle_withdraw_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal address input."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    amount = context.user_data.get("withdraw_amount")
    address = update.message.text
    logger.info(f"User {user_id} submitted withdrawal address")

    if not amount:
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
            user_id, amount, None, "pending", "withdrawal", message_id, address=address
        )

        # Forward to admin
        try:
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
                    f"📤 *New Withdrawal Request*\n"
                    f"User ID: `{user_id}`\n"
                    f"Amount: `{amount}` USDT\n"
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
            # Update transaction status
            if not update_transaction_status(transaction_id, "confirmed"):
                await query.message.reply_text(
                    "❌ *Error*: Transaction already processed or not found.",
                    parse_mode="Markdown"
                )
                return
            
            # Handle deposit or withdrawal
            if type == "deposit" and seed_id:
                logger.info(f"Adding seed {seed_id} to user {target_user_id}")
                add_user_seed(target_user_id, seed_id)
                # Update referral profits
                chain = get_referral_chain(target_user_id)
                profit_rates = {1: 0.05, 2: 0.03, 3: 0.01}
                for referrer_id, level in chain:
                    if level in profit_rates:
                        profit_amount = round(amount * profit_rates[level], 2)
                        logger.info(f"Recording referral profit for referrer {referrer_id}, level {level}, amount {profit_amount}")
                        update_balance(referrer_id, profit_amount)
                        record_referral_profit(referrer_id, target_user_id, transaction_id, level, profit_amount)
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
            # Update transaction status
            if not update_transaction_status(transaction_id, "rejected"):
                await query.message.reply_text(
                    "❌ *Error*: Transaction already processed or not found.",
                    parse_mode="Markdown"
                )
                return
            
            # Notify user
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
        if not update_transaction_status(transaction_id, "confirmed"):
            await update.message.reply_text(
                "❌ *Error*: Transaction already processed or not found.",
                parse_mode="Markdown"
            )
            return
        
        # Handle deposit or withdrawal
        user = get_user(target_user_id)
        lang = user[0] if user else "en"
        if type == "deposit" and seed_id:
            logger.info(f"Adding seed {seed_id} to user {target_user_id}")
            add_user_seed(target_user_id, seed_id)
            # Update referral profits
            chain = get_referral_chain(target_user_id)
            profit_rates = {1: 0.05, 2: 0.03, 3: 0.01}
            for referrer_id, level in chain:
                if level in profit_rates:
                    profit_amount = round(amount * profit_rates[level], 2)
                    logger.info(f"Recording referral profit for referrer {referrer_id}, level {level}, amount {profit_amount}")
                    update_balance(referrer_id, profit_amount)
                    record_referral_profit(referrer_id, target_user_id, transaction_id, level, profit_amount)
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
    """Cancel the current operation."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} cancelled operation")
    
    context.user_data.clear()
    await update.message.reply_text(
        messages[lang]["cancel"],
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

def main():
    """Run the bot."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not found in environment variables")
        exit(1)

    app = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(
                handle_menu_callback,
                pattern=r"^(buy_seed|wallet|referral|language|support|back_to_menu|withdraw|history|plant_seed|harvest_seed)$"
            ),
            CallbackQueryHandler(handle_language_callback, pattern=r"^lang_.*$"),
            CallbackQueryHandler(handle_seed_selection, pattern=r"^(seed_\d+|confirm_seed_purchase)$"),
            CallbackQueryHandler(handle_deposit_network, pattern=r"^network_.*$"),
            CallbackQueryHandler(handle_plant_seed, pattern=r"^plant_\d+$"),
            CallbackQueryHandler(handle_harvest_seed, pattern=r"^harvest_\d+$"),
            CallbackQueryHandler(handle_admin_action, pattern=r"^(approve|reject)_\d+$"),
        ],
        states={
            SELECT_SEED: [
                CallbackQueryHandler(
                    handle_seed_selection,
                    pattern=r"^(seed_\d+|confirm_seed_purchase|back_to_menu)$"
                ),
            ],
            DEPOSIT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deposit_amount),
                CallbackQueryHandler(handle_menu_callback, pattern=r"^back_to_menu$"),
            ],
            DEPOSIT_NETWORK: [
                CallbackQueryHandler(
                    handle_deposit_network,
                    pattern=r"^(network_.*|back_to_menu)$"
                ),
            ],
            DEPOSIT_TXID: [
                MessageHandler(filters.TEXT | filters.PHOTO, handle_deposit_txid),
                CallbackQueryHandler(handle_menu_callback, pattern=r"^back_to_menu$"),
            ],
            WITHDRAW_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_withdraw_amount),
                CallbackQueryHandler(handle_menu_callback, pattern=r"^wallet$"),
            ],
            WITHDRAW_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_withdraw_address),
                CallbackQueryHandler(handle_menu_callback, pattern=r"^wallet$"),
            ],
            PLANT_SEED: [
                CallbackQueryHandler(
                    handle_plant_seed,
                    pattern=r"^(plant_\d+|wallet|back_to_menu)$"
                ),
            ],
            HARVEST_SEED: [
                CallbackQueryHandler(
                    handle_harvest_seed,
                    pattern=r"^(harvest_\d+|wallet|back_to_menu)$"
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
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
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("checkseeds", check_seeds))

    logger.info("Starting bot")
    app.run_polling()

if __name__ == '__main__':
    main()
