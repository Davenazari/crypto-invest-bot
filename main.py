import logging
import os
import psycopg2
import asyncio
from datetime import datetime, timedelta
import datetime as dt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
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
SELECT_LAND, DEPOSIT_AMOUNT, DEPOSIT_NETWORK, DEPOSIT_TXID, WITHDRAW_AMOUNT, WITHDRAW_NETWORK, WITHDRAW_ADDRESS, PLANT_LAND, HARVEST_LAND, CONFIRM_BALANCE_PURCHASE = range(10)

# Default admin ID
DEFAULT_ADMIN_ID = 536587863  # Changed to integer

# Supported languages
langs = {"فارسی": "fa", "English": "en"}

# 🌾 **لیست زمین‌های مزرعه** 🌱
LANDS = [
    {"name": "Tomato", "name_fa": "گوجه", "price": 15, "daily_profit_rate": 0.04, "seed_count": 50, "emoji": "🍅"},
    {"name": "Cucumber", "name_fa": "خیار", "price": 30, "daily_profit_rate": 0.043333, "seed_count": 50, "emoji": "🥒"},
    {"name": "Orange", "name_fa": "پرتغال", "price": 50, "daily_profit_rate": 0.042, "seed_count": 50, "emoji": "🍊"},
    {"name": "Apple", "name_fa": "سیب", "price": 120, "daily_profit_rate": 0.0375, "seed_count": 50, "emoji": "🍎"},
    {"name": "Banana", "name_fa": "موز", "price": 320, "daily_profit_rate": 0.034375, "seed_count": 50, "emoji": "🍌"},
    {"name": "Mango", "name_fa": "انبه", "price": 550, "daily_profit_rate": 0.036364, "seed_count": 50, "emoji": "🥭"},
]

# Localized messages
messages = {
    "fa": {
        "welcome": (
            "🌟 *خوش اومدید به مزرعه USDT!* 🌱\n"
            "اینجا می‌تونید زمین بخرید، بذر بکارید و سود تضمین‌شده برداشت کنید. "
            "برای شروع، یک زمین انتخاب کنید یا مزرعه خودتون رو بررسی کنید!\n"
            "👇 گزینه مورد نظرتون رو انتخاب کنید 👇"
        ),
        "main_menu": "🌾 *منوی مزرعه*\nلطفاً یک گزینه انتخاب کنید:",
        "select_land": (
            "🌾 **انتخاب زمین** 🏞️\n"
            "لطفاً **زمین** مورد نظر برای خرید را انتخاب کنید:\n"
            "👇 از **زمین‌های** زیر یکی را انتخاب کنید 👇"
        ),
        "land_info": lambda name, price, daily_profit, weekly_profit, monthly_profit, total_monthly, seed_count, emoji: (
            f"🌾 **زمین {name}** {emoji}\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"💰 **قیمت**: `{price}` تتر\n"
            f"🌱 **تعداد بذرها**: `{seed_count}` بذر\n"
            f"📆 **سود روزانه ({seed_count} بذر)**: `{daily_profit * seed_count:.2f}` تتر\n"
            f"📅 **سود هفتگی ({seed_count} بذر)**: `{weekly_profit * seed_count:.2f}` تتر\n"
            f"🗓️ **سود ماهانه ({seed_count} بذر)**: `{monthly_profit * seed_count:.2f}` تتر\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"🏞️ **آماده خرید این زمین هستید؟**"
        ),
        "ask_amount": (
            "💰 *واریز برای خرید زمین*\n"
            "لطفاً مقدار دقیق قیمت زمین ({}) تتر رو واریز کنید:\n"
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
        "invalid_amount": "⚠️ *خطا*: مقدار واردشده معتبر نیست!\nلطفاً قیمت دقیق زمین ({}) تتر رو وارد کنید.",
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
            "✅ *زمین خریداری شد!*\n"
            "زمین شما با موفقیت به مزرعه اضافه شد و `{}` بذر دریافت کردید.\n"
            "🌱 حالا می‌تونید هر روز بذرها رو بکارید و سود برداشت کنید!"
        ),
        "rejected": (
            "❌ *تراکنش رد شد!*\n"
            "واریز شما تأیید نشد.\n"
            "📩 لطفاً با پشتیبانی تماس بگیرید."
        ),
        "wallet_menu": "🌾 *مزرعه من*\nلطفاً یک گزینه انتخاب کنید:",
        "wallet_balance": lambda balance, lands, total_profit, transaction_count, last_transaction: (
            f"🌾 **مزرعه شما** 🌱\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"💰 **موجودی**: `{balance}` تتر\n"
            f"🎁 **بونوس**: `0.0` تتر\n"
            f"💎 **$FMX**: `0.0`\n"
            f"🏞️ **زمین‌های شما**: {lands or 'هیچ زمینی ندارید'}\n"
            f"📈 **کل سود کسب‌شده**: `{total_profit}` تتر\n"
            f"📝 **تراکنش‌های موفق**: `{transaction_count}`\n"
            f"⏰ **آخرین تراکنش**: {'ندارد' if not last_transaction else last_transaction}\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"📌 برای **کاشت**، **برداشت** یا **خرید زمین جدید**، گزینه‌های زیر را انتخاب کنید."
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
        "ask_withdraw_address": lambda network, example_address: (
            f"✅ *آدرس کیف پول {network}*\n"
            f"لطفاً آدرس کیف پول USDT خودتون رو برای برداشت وارد کنید:\n"
            f"📋 مثال: `{example_address}`\n"
            f"⚠️ *توجه*: فقط از شبکه *{network}* استفاده کنید!\n"
            f"📌 آدرس رو با دقت وارد کنید."
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
            f"📌 برای خرید زمین یا برداشت، به منوی مزرعه برید."
        ),
        "no_history": (
            "📜 *بدون تاریخچه*\n"
            "هنوز هیچ تراکنشی ثبت نشده.\n"
            "📌 برای خرید زمین، به منوی مزرعه برید."
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
        "referral_details": lambda username, join_date, lands, profit, transactions: (
            f"👤 *کارگر: @{username}*\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"📅 *تاریخ ورود*: {join_date}\n"
            f"🏞️ *زمین‌های خریداری‌شده*:\n{lands or 'هیچ زمینی خریداری نشده'}\n"
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
        "plant_land": (
            "🌱 **کاشت بذرها** 🌿\n"
            "لطفاً **زمینی** که می‌خواهید بذرهایش را امروز بکارید انتخاب کنید:\n"
            "👇 یکی از **زمین‌های** زیر را انتخاب کنید 👇"
        ),
        "plant_success": (
            "🌱 *بذرها کاشته شدند!*\n"
            "بذرهای زمین شما با موفقیت کاشته شدند. می‌تونید بعد از ساعت 00:00 سودش رو برداشت کنید."
        ),
        "plant_already_done": (
            "⚠️ *خطا*: بذرهای این زمین امروز کاشته شدند!\n"
            "هر زمین رو فقط یک‌بار در روز می‌تونید بکارید.\n"
            "📌 فردا دوباره تلاش کنید یا زمین‌های دیگه‌ای بکارید."
        ),
        "harvest_land": (
            "🚜 **برداشت سود** 💰\n"
            "لطفاً **زمینی** که می‌خواهید **سود بذرهایش** را برداشت کنید انتخاب کنید:\n"
            "👇 یکی از **زمین‌های** زیر را انتخاب کنید 👇"
        ),
        "harvest_success": lambda amount: (
            f"🎉 *سود برداشت شد!*\n"
            f"💰 *مقدار*: `{amount}` تتر\n"
            f"📌 سود به موجودی مزرعه‌تون اضافه شد."
        ),
        "harvest_not_ready": (
            "⚠️ *خطا*: هنوز نمی‌تونید سود بذرهای این زمین رو برداشت کنید!\n"
            "📌 لطفاً بعد از ساعت 00:00 یا پس از کاشت بذرها دوباره تلاش کنید."
        ),
        "no_lands": (
            "🏞️ *بدون زمین*\n"
            "شما هنوز هیچ زمینی ندارید.\n"
            "📌 برای خرید زمین، به منوی مزرعه برید."
        ),
        "db_test_success": (
            "✅ *تست دیتابیس موفق!*\n"
            "اتصال به دیتابیس برقرار است و جدول زمین‌ها پر شده است.\n"
            "تعداد زمین‌ها: {}"
        ),
        "db_test_failed": (
            "❌ *تست دیتابیس ناموفق!*\n"
            "مشکل در اتصال به دیتابیس یا جدول زمین‌ها خالی است.\n"
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
        "no_land": (
            "⚠️ *خطا*: این زمین متعلق به شما نیست!\n"
            "📌 لطفاً زمین دیگری انتخاب کنید یا به منوی مزرعه برگردید."
        ),
        "land_not_planted": (
            "⚠️ *خطا*: بذرهای این زمین هنوز کاشته نشده‌اند!\n"
            "📌 لطفاً ابتدا بذرها رو بکارید."
        ),
        "no_profit": (
            "⚠️ *خطا*: هیچ سودی برای برداشت وجود نداره!\n"
            "📌 لطفاً بعد از کاشت و زمان مناسب دوباره تلاش کنید."
        ),
        "manage_users_menu": "👤 *مدیریت کاربران*\nلطفاً یک گزینه انتخاب کنید:",
        "ban_user": "🚫 بن/حذف کاربر",
        "manage_lands": "🏞️ مدیریت زمین‌ها",
        "manage_balance": "💰 مدیریت بالانس",
        "ask_user_id": "📋 لطفاً ID کاربر را وارد کنید (فقط عدد):",
        "invalid_user_id": "⚠️ *خطا*: ID کاربر نامعتبر است یا کاربر وجود ندارد!",
        "confirm_ban_user": lambda user_id: f"🚫 آیا مطمئن هستید که می‌خواهید کاربر {user_id} را بن کنید؟",
        "user_banned": lambda user_id: f"✅ کاربر {user_id} با موفقیت بن شد.",
        "ask_land_action": "🏞️ *مدیریت زمین*\nلطفاً نوع عملیات را انتخاب کنید:",
        "add_land": "➕ اضافه کردن زمین",
        "remove_land": "➖ حذف زمین",
        "select_land_to_add": "🏞️ لطفاً زمین مورد نظر برای اضافه کردن را انتخاب کنید:",
        "select_land_to_remove": "🏞️ لطفاً زمین مورد نظر برای حذف را انتخاب کنید:",
        "land_added": lambda land_name, user_id: f"✅ زمین {land_name} به کاربر {user_id} اضافه شد.",
        "land_removed": lambda land_name, user_id: f"✅ زمین {land_name} از کاربر {user_id} حذف شد.",
        "no_lands_to_remove": "⚠️ *خطا*: این کاربر هیچ زمینی ندارد!",
        "ask_balance_action": "💰 *مدیریت بالانس*\nلطفاً نوع عملیات را انتخاب کنید:",
        "add_balance": "➕ افزایش بالانس",
        "subtract_balance": "➖ کاهش بالانس",
        "ask_balance_amount": "💰 لطفاً مقدار بالانس (تتر) را وارد کنید (عدد مثبت):",
        "invalid_balance_amount": "⚠️ *خطا*: مقدار واردشده معتبر نیست! لطفاً عدد مثبتی وارد کنید.",
        "balance_updated": lambda user_id, amount, action: (
            f"✅ بالانس کاربر {user_id} با موفقیت {action} شد.\nمقدار: {amount} تتر"
        ),
    },
    "en": {
        "welcome": (
            "🌟 *Welcome to the USDT Farm!* 🌱\n"
            "Buy lands, plant seeds, and harvest guaranteed profits. "
            "Start by choosing a land or checking your farm!\n"
            "👇 Choose an option below 👇"
        ),
        "main_menu": "🌾 *Farm Menu*\nPlease select an option:",
        "select_land": (
            "🌾 **Select Land** 🏞️\n"
            "Please choose a **land** to buy:\n"
            "👇 Pick one of the **lands** below 👇"
        ),
        "land_info": lambda name, price, daily_profit, weekly_profit, monthly_profit, total_monthly, seed_count, emoji: (
            f"🌾 **{name} Land** {emoji}\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"💰 **Price**: `{price}` USDT\n"
            f"🌱 **Number of Seeds**: `{seed_count}` seeds\n"
            f"📆 **Daily Profit ({seed_count} seeds)**: `{daily_profit * seed_count:.2f}` USDT\n"
            f"📅 **Weekly Profit ({seed_count} seeds)**: `{weekly_profit * seed_count:.2f}` USDT\n"
            f"🗓️ **Monthly Profit ({seed_count} seeds)**: `{monthly_profit * seed_count:.2f}` USDT\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"🏞️ **Ready to buy this land?**"
        ),
        "ask_amount": (
            "💰 *Deposit for Land Purchase*\n"
            "Please deposit the exact land price ({}) USDT:\n"
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
        "invalid_amount": "⚠️ *Error*: Invalid amount entered!\nPlease enter the exact land price ({}) USDT.",
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
            "✅ *Land Purchased!*\n"
            "Your land has been added to your farm, and you received `{}` seeds.\n"
            "🌱 You can now plant the seeds daily and harvest profits!"
        ),
        "rejected": (
            "❌ *Transaction Rejected!*\n"
            "Your deposit was not approved.\n"
            "📩 Please contact support."
        ),
        "wallet_menu": "🌾 *My Farm*\nPlease select an option:",
        "wallet_balance": lambda balance, lands, total_profit, transaction_count, last_transaction: (
            f"🌾 **Your Farm** 🌱\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"💰 **Balance**: `{balance}` USDT\n"
            f"🎁 **Bonus**: `0.0` USDT\n"
            f"💎 **$FMX**: `0.0`\n"
            f"🏞️ **Your Lands**: {lands or 'No lands yet'}\n"
            f"📈 **Total Profit Earned**: `{total_profit}` USDT\n"
            f"📝 **Successful Transactions**: `{transaction_count}`\n"
            f"⏰ **Last Transaction**: {'None' if not last_transaction else last_transaction}\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"📌 Choose an option to **plant**, **harvest**, or **buy new lands**."
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
        "ask_withdraw_address": lambda network, example_address: (
            f"✅ *{network} Wallet Address*\n"
            "Please enter your USDT wallet address for withdrawal:\n"
            f"📋 Example: `{example_address}`\n"
            f"⚠️ *Note*: Only use the *{network}* network!\n"
            f"📌 Enter the address carefully."
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
            f"📌 For new land purchases or withdrawals, go to the farm menu."
        ),
        "no_history": (
            "📜 *No History*\n"
            "No transactions have been recorded yet.\n"
            "📌 To buy a land, go to the farm menu."
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
        "referral_details": lambda username, join_date, lands, profit, transactions: (
            f"👤 *Worker: @{username}*\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"📅 *Join Date*: {join_date}\n"
            f"🏞️ *Purchased Lands*:\n{lands or 'No lands purchased'}\n"
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
        "plant_land": (
            "🌱 **Plant Seeds** 🌿\n"
            "Please choose a **land** to plant its seeds today:\n"
            "👇 Pick one of the **lands** below 👇"
        ),
        "plant_success": (
            "🌱 *Seeds Planted!*\n"
            "The seeds of your land have been successfully planted. You can harvest their profit after 00:00."
        ),
        "plant_already_done": (
            "⚠️ *Error*: The seeds of this land have already been planted today!\n"
            "You can only plant each land’s seeds once per day.\n"
            "📌 Try again tomorrow or plant other lands’ seeds."
        ),
        "harvest_land": (
            "🚜 **Harvest Profit** 💰\n"
            "Please choose a **land** to harvest its **seeds’ profit**:\n"
            "👇 Pick one of the **lands** below 👇"
        ),
        "harvest_success": lambda amount: (
            f"🎉 *Profit Harvested!*\n"
            f"💰 *Amount*: `{amount}` USDT\n"
            f"📌 The profit has been added to your farm balance."
        ),
        "harvest_not_ready": (
            "⚠️ *Error*: You can’t harvest the seeds of this land yet!\n"
            "📌 Please try after 00:00 or after planting the seeds."
        ),
        "no_lands": (
            "🏞️ *No Lands*\n"
            "You don’t have any lands yet.\n"
            "📌 Go to the farm menu to buy a land."
        ),
        "db_test_success": (
            "✅ *Database Test Successful!*\n"
            "Connection to the database is established, and the lands table is populated.\n"
            "Number of lands: {}"
        ),
        "db_test_failed": (
            "❌ *Database Test Failed!*\n"
            "Issue connecting to the database or lands table is empty.\n"
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
        "no_land": (
            "⚠️ *Error*: This land does not belong to you!\n"
            "📌 Please select another land or return to the farm menu."
        ),
        "land_not_planted": (
            "⚠️ *Error*: The seeds of this land have not been planted yet!\n"
            "📌 Please plant the seeds first."
        ),
        "no_profit": (
            "⚠️ *Error*: No profit available to harvest!\n"
            "📌 Please try again after planting and at the appropriate time."
        ),
        "manage_users_menu": "👤 *Manage Users*\nPlease select an option:",
        "ban_user": "🚫 Ban/Delete User",
        "manage_lands": "🏞️ Manage Lands",
        "manage_balance": "💰 Manage Balance",
        "ask_user_id": "📋 Please enter the user ID (numbers only):",
        "invalid_user_id": "⚠️ *Error*: Invalid user ID or user does not exist!",
        "confirm_ban_user": lambda user_id: f"🚫 Are you sure you want to ban user {user_id}?",
        "user_banned": lambda user_id: f"✅ User {user_id} has been banned successfully.",
        "ask_land_action": "🏞️ *Manage Lands*\nPlease select the action:",
        "add_land": "➕ Add Land",
        "remove_land": "➖ Remove Land",
        "select_land_to_add": "🏞️ Please select the land to add:",
        "select_land_to_remove": "🏞️ Please select the land to remove:",
        "land_added": lambda land_name, user_id: f"✅ Land {land_name} added to user {user_id}.",
        "land_removed": lambda land_name, user_id: f"✅ Land {land_name} removed from user {user_id}.",
        "no_lands_to_remove": "⚠️ *Error*: This user has no lands!",
        "ask_balance_action": "💰 *Manage Balance*\nPlease select the action:",
        "add_balance": "➕ Add Balance",
        "subtract_balance": "➖ Subtract Balance",
        "ask_balance_amount": "💰 Please enter the balance amount (USDT, positive number):",
        "invalid_balance_amount": "⚠️ *Error*: Invalid amount entered! Please enter a positive number.",
        "balance_updated": lambda user_id, amount, action: (
            f"✅ User {user_id}'s balance has been {action} successfully.\nAmount: {amount} USDT"
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
async def notify_admin_error(bot_token, error_message):
    """Send error notification to admin asynchronously."""
    try:
        # پاکسازی پیام خطا از کاراکترهای مشکل‌ساز
        safe_error_message = error_message.replace("`", "").replace("*", "").replace("_", "")
        bot = Bot(token=bot_token)
        await bot.send_message(
            chat_id=DEFAULT_ADMIN_ID,
            text=f"⚠️ *خطا*: {safe_error_message[:200]}",  # محدود کردن طول پیام
            parse_mode="Markdown"
        )
        logger.info("Successfully sent error notification to admin")
    except telegram.error.TelegramError as admin_e:
        logger.error(f"Failed to notify admin: {admin_e}")
        
def init_db():
    """Initialize database tables, update land profit rates, and migrate data from seeds to lands."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            conn.autocommit = False  # Start transaction
            try:
                with conn.cursor() as c:
                    # Add username and created_at columns to users table
                    logger.info("Adding username and created_at columns to users table")
                    c.execute('''
                        ALTER TABLE users
                        ADD COLUMN IF NOT EXISTS username TEXT,
                        ADD COLUMN IF NOT EXISTS created_at TEXT
                    ''')
                    logger.info("Successfully added username and created_at columns to users table")

                    # Add bonus and fmx_balance columns to users table
                    logger.info("Adding bonus and fmx_balance columns to users table")
                    c.execute('''
                        ALTER TABLE users
                        ADD COLUMN IF NOT EXISTS "bonus" REAL DEFAULT 0.0,
                        ADD COLUMN IF NOT EXISTS fmx_balance REAL DEFAULT 0.0
                    ''')
                    logger.info("Successfully added bonus and fmx_balance columns to users table")

                    # Create users table
                    logger.info("Creating users table if not exists")
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS users (
                            user_id BIGINT PRIMARY KEY,
                            language TEXT DEFAULT 'en',
                            balance REAL DEFAULT 0.0,
                            username TEXT,
                            created_at TEXT,
                            "bonus" REAL DEFAULT 0.0,
                            fmx_balance REAL DEFAULT 0.0
                        )
                    ''')
                    logger.info("Users table created or already exists")

                    # Add is_banned column
                    logger.info("Adding is_banned column to users table")
                    c.execute('''
                        ALTER TABLE users
                        ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE
                    ''')
                    logger.info("Successfully added is_banned column to users table")

                    # Create lands table with UNIQUE constraint on name
                    logger.info("Creating lands table if not exists")
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS lands (
                            land_id SERIAL PRIMARY KEY,
                            name TEXT NOT NULL UNIQUE,
                            name_fa TEXT NOT NULL,
                            price REAL NOT NULL,
                            daily_profit_rate REAL NOT NULL,
                            seed_count INTEGER NOT NULL DEFAULT 50
                        )
                    ''')
                    logger.info("Lands table created or already exists")

                    # Ensure UNIQUE constraint on name for existing lands table
                    logger.info("Ensuring UNIQUE constraint on lands.name")
                    c.execute('''
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.table_constraints
                                WHERE table_name = 'lands' AND constraint_type = 'UNIQUE' AND constraint_name = 'unique_land_name'
                            ) THEN
                                ALTER TABLE lands ADD CONSTRAINT unique_land_name UNIQUE (name);
                            END IF;
                        END $$;
                    ''')
                    logger.info("UNIQUE constraint ensured on lands.name")

                    # Create user_lands table
                    logger.info("Creating user_lands table if not exists")
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS user_lands (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT,
                            land_id INTEGER,
                            purchase_date TEXT,
                            last_planted TEXT,
                            last_harvested TEXT,
                            FOREIGN KEY (user_id) REFERENCES users (user_id),
                            FOREIGN KEY (land_id) REFERENCES lands (land_id)
                        )
                    ''')
                    logger.info("User_lands table created or already exists")

                    # Create transactions table
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
                            land_id INTEGER,
                            FOREIGN KEY (user_id) REFERENCES users (user_id),
                            FOREIGN KEY (land_id) REFERENCES lands (land_id)
                        )
                    ''')
                    logger.info("Transactions table created or already exists")

                    # Ensure land_id column in transactions
                    logger.info("Checking for land_id column in transactions table")
                    c.execute("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'transactions' AND column_name = 'land_id'
                    """)
                    if not c.fetchone():
                        logger.info("Adding land_id column to transactions table")
                        c.execute('''
                            ALTER TABLE transactions
                            ADD COLUMN land_id INTEGER
                        ''')
                        c.execute('''
                            ALTER TABLE transactions
                            ADD CONSTRAINT transactions_land_id_fkey
                            FOREIGN KEY (land_id) REFERENCES lands (land_id)
                        ''')
                        logger.info("Successfully added land_id column and foreign key to transactions table")

                    # Create profits table
                    logger.info("Creating profits table if not exists")
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS profits (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT,
                            land_id INTEGER,
                            amount REAL,
                            period TEXT,
                            created_at TEXT,
                            FOREIGN KEY (user_id) REFERENCES users (user_id),
                            FOREIGN KEY (land_id) REFERENCES lands (land_id)
                        )
                    ''')
                    logger.info("Profits table created or already exists")

                    # Ensure land_id column in profits
                    logger.info("Checking for land_id column in profits table")
                    c.execute("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'profits' AND column_name = 'land_id'
                    """)
                    if not c.fetchone():
                        logger.info("Adding land_id column to profits table")
                        c.execute('''
                            ALTER TABLE profits
                            ADD COLUMN land_id INTEGER
                        ''')
                        c.execute('''
                            ALTER TABLE profits
                            ADD CONSTRAINT profits_land_id_fkey
                            FOREIGN KEY (land_id) REFERENCES lands (land_id)
                        ''')
                        logger.info("Successfully added land_id column and foreign key to profits table")

                    # Create referrals table
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

                    # Create referral_profits table
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

                    # Migrate data from seeds and user_seeds
                    logger.info("Starting data migration from seeds to lands")
                    c.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'seeds'
                        )
                    """)
                    seeds_table_exists = c.fetchone()[0]
                    
                    if seeds_table_exists:
                        # Migrate seeds to lands
                        logger.info("Migrating data from seeds to lands")
                        c.execute('''
                            INSERT INTO lands (name, name_fa, price, daily_profit_rate, seed_count)
                            SELECT name, name_fa, price, daily_profit_rate, 50
                            FROM seeds
                            ON CONFLICT (name) DO NOTHING
                        ''')
                        logger.info("Successfully migrated seeds to lands")

                        # Migrate user_seeds to user_lands
                        logger.info("Migrating data from user_seeds to user_lands")
                        c.execute('''
                            INSERT INTO user_lands (user_id, land_id, purchase_date, last_planted, last_harvested)
                            SELECT us.user_id, l.land_id, us.purchase_date, us.last_planted, us.last_harvested
                            FROM user_seeds us
                            JOIN seeds s ON us.seed_id = s.seed_id
                            JOIN lands l ON s.name = l.name
                        ''')
                        logger.info("Successfully migrated user_seeds to user_lands")

                        # Check for seed_id column in transactions
                        c.execute("""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'transactions' AND column_name = 'seed_id'
                        """)
                        if c.fetchone():
                            # Update land_id in transactions
                            logger.info("Updating land_id in transactions table")
                            c.execute('''
                                UPDATE transactions t
                                SET land_id = l.land_id
                                FROM seeds s
                                JOIN lands l ON s.name = l.name
                                WHERE t.seed_id = s.seed_id
                            ''')
                            logger.info("Successfully updated land_id in transactions table")

                        # Check for seed_id column in profits
                        c.execute("""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'profits' AND column_name = 'seed_id'
                        """)
                        if c.fetchone():
                            # Update land_id in profits
                            logger.info("Updating land_id in profits table")
                            c.execute('''
                                UPDATE profits p
                                SET land_id = l.land_id
                                FROM seeds s
                                JOIN lands l ON s.name = l.name
                                WHERE p.seed_id = s.seed_id
                            ''')
                            logger.info("Successfully updated land_id in profits table")

                        # Drop seed_id column from transactions (if exists)
                        logger.info("Checking for seed_id column in transactions table")
                        c.execute("""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'transactions' AND column_name = 'seed_id'
                        """)
                        if c.fetchone():
                            logger.info("Dropping seed_id column from transactions table")
                            c.execute('''
                                ALTER TABLE transactions
                                DROP COLUMN IF EXISTS seed_id
                            ''')
                            logger.info("Successfully dropped seed_id column from transactions table")

                        # Drop seed_id column from profits (if exists)
                        logger.info("Checking for seed_id column in profits table")
                        c.execute("""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'profits' AND column_name = 'seed_id'
                        """)
                        if c.fetchone():
                            logger.info("Dropping seed_id column from profits table")
                            c.execute('''
                                ALTER TABLE profits
                                DROP COLUMN IF EXISTS seed_id
                            ''')
                            logger.info("Successfully dropped seed_id column from profits table")

                        # Drop old tables
                        logger.info("Dropping old seeds and user_seeds tables")
                        c.execute('DROP TABLE IF EXISTS user_seeds')
                        c.execute('DROP TABLE IF EXISTS seeds')
                        logger.info("Successfully dropped old seeds and user_seeds tables")

                    # Populate or update lands table
                    logger.info("Checking and updating lands table")
                    c.execute('SELECT COUNT(*) FROM lands')
                    land_count = c.fetchone()[0]
                    if land_count == 0:
                        logger.info("Populating lands table")
                        for land in LANDS:
                            c.execute('''
                                INSERT INTO lands (name, name_fa, price, daily_profit_rate, seed_count)
                                VALUES (%s, %s, %s, %s, %s)
                                ON CONFLICT (name) DO NOTHING
                            ''', (land["name"], land["name_fa"], land["price"], land["daily_profit_rate"], land["seed_count"]))
                        logger.info("Successfully populated lands table")
                    else:
                        logger.info("Updating lands table with new daily_profit_rate and seed_count")
                        for land in LANDS:
                            c.execute('''
                                UPDATE lands
                                SET daily_profit_rate = %s, seed_count = %s
                                WHERE name = %s
                            ''', (land["daily_profit_rate"], land["seed_count"], land["name"]))
                        logger.info("Successfully updated daily_profit_rate and seed_count in lands table")

                    conn.commit()
                    logger.info("Database initialized, data migrated, and lands updated successfully")
            except Exception as e:
                conn.rollback()
                logger.error(f"خطا در مقداردهی اولیه پایگاه داده: {str(e)}", exc_info=True)
                bot_token = os.getenv("BOT_TOKEN")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(notify_admin_error(bot_token, f"خطا در مقداردهی اولیه پایگاه داده: {str(e)}"))
                loop.close()
                raise
            finally:
                conn.autocommit = True
    except Exception as e:
        logger.error(f"خطا در اتصال به پایگاه داده: {str(e)}", exc_info=True)
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

def ban_user(user_id):
    """Ban a user by setting is_banned to True."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('UPDATE users SET is_banned = TRUE WHERE user_id = %s', (user_id,))
                if c.rowcount == 0:
                    return False
                conn.commit()
                logger.info(f"User {user_id} banned successfully")
                return True
    except Exception as e:
        logger.error(f"Error banning user {user_id}: {e}")
        raise

def add_user_land_admin(user_id, land_id):
    """Add a land to a user by admin."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                purchase_date = datetime.now(pytz.timezone('Asia/Tehran')).isoformat()
                c.execute('''
                    INSERT INTO user_lands (user_id, land_id, purchase_date)
                    VALUES (%s, %s, %s)
                ''', (user_id, land_id, purchase_date))
                conn.commit()
                logger.info(f"Land {land_id} added to user {user_id} by admin")
    except Exception as e:
        logger.error(f"Error adding land {land_id} to user {user_id}: {e}")
        raise

def remove_user_seed(user_id, user_seed_id):
    """Remove a specific seed from a user."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    DELETE FROM user_seeds
                    WHERE user_id = %s AND id = %s
                ''', (user_id, user_seed_id))
                if c.rowcount == 0:
                    return False
                conn.commit()
                logger.info(f"Seed {user_seed_id} removed from user {user_id}")
                return True
    except Exception as e:
        logger.error(f"Error removing seed {user_seed_id} from user {user_id}: {e}")
        raise    

# Database helper functions
def get_user(user_id):
    """Retrieve user data from database or create a new user."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('SELECT language, balance, is_banned FROM users WHERE user_id = %s', (user_id,))
                user = c.fetchone()
                if user:
                    if user[2]:  # اگر is_banned=True باشه
                        logger.warning(f"User {user_id} is banned")
                        return None
                    return user[:2]  # فقط language و balance رو برگردون
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
    """Retrieve referral details using lands instead of seeds."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # Get user info
                c.execute('''
                    SELECT username, created_at 
                    FROM users 
                    WHERE user_id = %s
                ''', (referred_id,))
                user_info = c.fetchone()
                if not user_info:
                    return None
                username, join_date = user_info

                # Get purchased lands
                c.execute('''
                    SELECT l.name, l.name_fa, t.created_at
                    FROM user_lands ul
                    JOIN lands l ON ul.land_id = l.land_id
                    JOIN transactions t ON t.land_id = l.land_id AND t.user_id = %s AND t.status = 'confirmed'
                    WHERE ul.user_id = %s
                    ORDER BY t.created_at DESC
                ''', (referred_id, referred_id))
                lands = c.fetchall()
                lands_text = "\n".join(
                    f"- {row[1] if lang == 'fa' else row[0]} (خرید: {row[2]})"
                    for row in lands
                ) if lands else None

                # Get referral profit
                c.execute('''
                    SELECT SUM(profit_amount) 
                    FROM referral_profits 
                    WHERE referrer_id = %s AND referred_id = %s
                ''', (referrer_id, referred_id))
                profit = c.fetchone()[0] or 0.0

                # Get transactions
                c.execute('''
                    SELECT t.amount, t.network, t.status, t.type, t.created_at, l.name, l.name_fa
                    FROM transactions t
                    LEFT JOIN lands l ON t.land_id = l.land_id
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
                    "seeds": lands_text,  # Renamed to maintain compatibility
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

def insert_transaction(user_id, amount, network, status, type, message_id, address=None, land_id=None):
    """Insert a transaction into the database using land_id."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                created_at = dt.datetime.now(dt.UTC).isoformat()
                c.execute('''
                    INSERT INTO transactions (user_id, amount, network, status, type, created_at, message_id, address, land_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (user_id, amount, network, status, type, created_at, message_id, address, land_id))
                transaction_id = c.fetchone()[0]
                conn.commit()
                logger.info(f"Inserted transaction for user {user_id}: amount {amount}, network {network}, status {status}, type {type}, land_id {land_id}, id {transaction_id}")
                return transaction_id
    except Exception as e:
        logger.error(f"Error inserting transaction for user {user_id}: {e}")
        raise

def insert_profit(user_id, land_id, amount, period):
    """Insert a profit record into the database using land_id."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # Check if profit already recorded for this land today
                today = datetime.now(pytz.timezone('Asia/Tehran')).date().isoformat()
                c.execute('''
                    SELECT COUNT(*) FROM profits
                    WHERE user_id = %s AND land_id = %s AND period = %s
                    AND DATE(created_at) = %s
                ''', (user_id, land_id, period, today))
                if c.fetchone()[0] > 0:
                    logger.warning(f"Profit already recorded for user {user_id}, land_id {land_id} today")
                    return
                created_at = dt.datetime.now(dt.UTC).isoformat()
                c.execute('''
                    INSERT INTO profits (user_id, land_id, amount, period, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (user_id, land_id, amount, period, created_at))
                conn.commit()
                logger.info(f"Inserted profit for user {user_id}: land_id {land_id}, amount {amount}, period {period}")
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
    """Retrieve transaction history for a user using lands."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    SELECT t.amount, t.network, t.status, t.type, t.created_at, l.name, l.name_fa
                    FROM transactions t
                    LEFT JOIN lands l ON t.land_id = l.land_id
                    WHERE t.user_id = %s
                    ORDER BY t.created_at DESC
                    LIMIT 10
                ''', (user_id,))
                transactions = c.fetchall()
                logger.info(f"Retrieved {len(transactions)} transactions for user {user_id}")
                return transactions
    except Exception as e:
        logger.error(f"Error getting transaction history for user {user_id}: {e}")
        raise

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

def get_user_lands(user_id):
    """Retrieve all lands owned by a user."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('''
                    SELECT l.land_id, l.name, l.name_fa, l.price, l.daily_profit_rate, 
                           l.seed_count, us.last_planted, us.last_harvested, us.id
                    FROM user_lands us
                    JOIN lands l ON us.land_id = l.land_id
                    WHERE us.user_id = %s
                ''', (user_id,))
                lands = c.fetchall()
                logger.info(f"Retrieved {len(lands)} lands for user {user_id}")
                return lands
    except Exception as e:
        logger.error(f"Error getting lands for user {user_id}: {e}")
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
def get_main_menu(lang, user_id=None):
    """🌾 Generate main menu keyboard with enhanced visuals."""
    keyboard = [
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
    ]
    # اضافه کردن دکمه مدیریت کاربران فقط برای ادمین
    if user_id == DEFAULT_ADMIN_ID:
        keyboard.append(
            [
                InlineKeyboardButton("👤 مدیریت کاربران" if lang == "fa" else "👤 Manage Users", callback_data="manage_users")
            ]
        )
    return InlineKeyboardMarkup(keyboard)

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
            reply_markup=get_main_menu(lang, update.effective_user.id)
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

async def handle_land_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle land selection for purchase."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    balance = user[1] if user else 0
    logger.info(f"User {user_id} triggered land selection callback: {query.data}")

    try:
        if query.data.startswith("land_"):
            land_idx = int(query.data.split("_")[1])
            if land_idx < 0 or land_idx >= len(LANDS):
                logger.warning(f"Invalid land index {land_idx} for user {user_id}")
                await query.message.reply_text(
                    messages[lang]["error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            land = LANDS[land_idx]
            daily_profit = round(land["price"] * land["daily_profit_rate"] * land["seed_count"], 3)
            weekly_profit = round(daily_profit * 7, 3)
            monthly_profit = round(daily_profit * 30, 3)
            total_monthly = round(land["price"] + monthly_profit, 3)
            context.user_data["land_idx"] = land_idx
            context.user_data["land_price"] = land["price"]
            buttons = [
                [InlineKeyboardButton("💸 پرداخت با واریز" if lang == "fa" else "💸 Pay with Deposit", callback_data="confirm_land_purchase")]
            ]
            if balance >= land["price"]:
                buttons.insert(0, [InlineKeyboardButton("💰 پرداخت با موجودی" if lang == "fa" else "💰 Pay with Balance", callback_data="balance_purchase")])
            buttons.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")])
            await query.message.reply_text(
                messages[lang]["land_info"](
                    land["name_fa" if lang == "fa" else "name"],
                    land["price"],
                    daily_profit,
                    weekly_profit,
                    monthly_profit,
                    total_monthly,
                    land["seed_count"],
                    land["emoji"]
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return SELECT_LAND
        elif query.data == "confirm_land_purchase":
            land_idx = context.user_data.get("land_idx")
            land_price = context.user_data.get("land_price")
            if land_idx is None or land_price is None:
                logger.warning(f"Missing land_idx or land_price for user {user_id}")
                await query.message.reply_text(
                    messages[lang]["invalid_data"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            await query.message.reply_text(
                messages[lang]["ask_amount"].format(land_price),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return DEPOSIT_AMOUNT
        elif query.data == "balance_purchase":
            land_idx = context.user_data.get("land_idx")
            land_price = context.user_data.get("land_price")
            if land_idx is None or land_price is None:
                logger.warning(f"Missing land_idx or land_price for user {user_id}")
                await query.message.reply_text(
                    messages[lang]["invalid_data"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            land = LANDS[land_idx]
            daily_profit = round(land["price"] * land["daily_profit_rate"] * land["seed_count"], 3)
            weekly_profit = round(daily_profit * 7, 3)
            monthly_profit = round(daily_profit * 30, 3)
            total_monthly = round(land["price"] + monthly_profit, 3)
            await query.message.reply_text(
                messages[lang]["land_info"](
                    land["name_fa" if lang == "fa" else "name"],
                    land["price"],
                    daily_profit,
                    weekly_profit,
                    monthly_profit,
                    total_monthly,
                    land["seed_count"],
                    land["emoji"]
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
        logger.error(f"Error in handle_land_selection for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        await context.bot.send_message(
            chat_id=DEFAULT_ADMIN_ID,
            text=f"⚠️ *Error in handle_land_selection for user {user_id}*: {str(e)}",
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

async def handle_plant_land(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle land planting."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"User {user_id} triggered plant land callback: {query.data}")

    try:
        if query.data.startswith("plant_"):
            user_land_id = int(query.data.split("_")[1])
            user_lands = get_user_lands(user_id)
            land = next((l for l in user_lands if l[6] == user_land_id), None)
            if not land or not can_plant_land(land[4]):
                await query.message.reply_text(
                    messages[lang]["plant_already_done"],
                    parse_mode="Markdown",
                    reply_markup=get_wallet_menu(lang, user[1], True)
                )
                return ConversationHandler.END
            update_land_plant(user_id, user_land_id)
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
                        land_profit = c.fetchone()[0] or 0.0
                        # جمع سود از جدول referral_profits
                        c.execute('SELECT SUM(profit_amount) FROM referral_profits WHERE referrer_id = %s', (user_id,))
                        referral_profit = c.fetchone()[0] or 0.0
                        total_profit = land_profit + referral_profit
                        c.execute('SELECT COUNT(*) FROM transactions WHERE user_id = %s AND status = %s', (user_id, 'confirmed'))
                        transaction_count = c.fetchone()[0]
                        c.execute('SELECT created_at FROM transactions WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT 1', (user_id, 'confirmed'))
                        last_transaction = c.fetchone()[0] if c.rowcount > 0 else None
                        c.execute('''
                            SELECT l.name, l.name_fa
                            FROM user_lands ul
                            JOIN lands l ON ul.land_id = l.land_id
                            WHERE ul.user_id = %s
                        ''', (user_id,))
                        lands = [row[1] if lang == "fa" else row[0] for row in c.fetchall()]
                        lands_text = ", ".join(lands) if lands else None
            except psycopg2.Error as e:
                logger.error(f"Database error retrieving wallet stats for user {user_id}: {e}")
                await query.message.reply_text(
                    messages[lang]["db_error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END

            await query.message.reply_text(
                messages[lang]["wallet_balance"](balance, lands_text, total_profit, transaction_count, last_transaction),
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, balance, bool(lands))
            )
            return ConversationHandler.END
        else:
            logger.warning(f"Unhandled plant land callback data for user {user_id}: {query.data}")
            await query.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_wallet_menu(lang, user[1], True)
            )
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_plant_land for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_wallet_menu(lang, user[1], True)
        )
        context.user_data.clear()
        return ConversationHandler.END
    
async def handle_harvest_land(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle harvesting profit from a specific land."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    if not user:
        await query.message.reply_text(
            messages["en"]["unauthorized"],
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    lang = user[0]
    user_land_id = int(query.data.split("_")[1])
    logger.info(f"User {user_id} attempting to harvest land {user_land_id}")

    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # Verify land ownership
                c.execute('''
                    SELECT ul.land_id, ul.last_planted, l.daily_profit_rate, l.seed_count
                    FROM user_lands ul
                    JOIN lands l ON ul.land_id = l.land_id
                    WHERE ul.id = %s AND ul.user_id = %s
                ''', (user_land_id, user_id))
                land_info = c.fetchone()
                if not land_info:
                    await query.message.reply_text(
                        messages[lang]["no_land"],
                        parse_mode="Markdown",
                        reply_markup=get_main_menu(lang)
                    )
                    return ConversationHandler.END

                land_id, last_planted, daily_profit_rate, seed_count = land_info

                # Check if land was planted
                if not last_planted:
                    await query.message.reply_text(
                        messages[lang]["land_not_planted"],
                        parse_mode="Markdown",
                        reply_markup=get_main_menu(lang)
                    )
                    return ConversationHandler.END

                # Check if it's time to harvest
                last_planted_dt = datetime.fromisoformat(last_planted)
                tehran_tz = pytz.timezone('Asia/Tehran')
                now = datetime.now(tehran_tz)
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                if last_planted_dt.date() >= midnight.date():
                    await query.message.reply_text(
                        messages[lang]["harvest_not_ready"],
                        parse_mode="Markdown",
                        reply_markup=get_main_menu(lang)
                    )
                    return ConversationHandler.END

                # Calculate profit
                profit = round(daily_profit_rate * seed_count, 2)
                if profit <= 0:
                    await query.message.reply_text(
                        messages[lang]["no_profit"],
                        parse_mode="Markdown",
                        reply_markup=get_main_menu(lang)
                    )
                    return ConversationHandler.END

                # Update balance and record profit
                update_balance(user_id, profit)
                c.execute('''
                    INSERT INTO profits (user_id, land_id, amount, period, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (user_id, land_id, profit, "daily", datetime.now(tehran_tz).isoformat()))
                c.execute('''
                    UPDATE user_lands
                    SET last_harvested = %s
                    WHERE id = %s AND ul.user_id = %s
                ''', (datetime.now(tehran_tz).isoformat(), user_land_id, user_id))
                conn.commit()

        await query.message.reply_text(
            messages[lang]["harvest_success"](profit),
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        logger.info(f"User {user_id} successfully harvested {profit} USDT from land {user_land_id}")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error harvesting land {user_land_id} for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        return ConversationHandler.END    

async def handle_land_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle land selection for purchase."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    lang = user[0] if user else "en"
    balance = user[1] if user else 0
    logger.info(f"User {user_id} triggered land selection callback: {query.data}")

    try:
        if query.data.startswith("land_"):
            land_idx = int(query.data.split("_")[1])
            if land_idx < 0 or land_idx >= len(LANDS):
                logger.warning(f"Invalid land index {land_idx} for user {user_id}")
                await query.message.reply_text(
                    messages[lang]["error"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            land = LANDS[land_idx]
            daily_profit = round(land["price"] * land["daily_profit_rate"] * land["seed_count"], 3)
            weekly_profit = round(daily_profit * 7, 3)
            monthly_profit = round(daily_profit * 30, 3)
            total_monthly = round(land["price"] + monthly_profit, 3)
            context.user_data["land_idx"] = land_idx
            context.user_data["land_price"] = land["price"]
            buttons = [
                [InlineKeyboardButton("💸 پرداخت با واریز" if lang == "fa" else "💸 Pay with Deposit", callback_data="confirm_land_purchase")]
            ]
            if balance >= land["price"]:
                buttons.insert(0, [InlineKeyboardButton("💰 پرداخت با موجودی" if lang == "fa" else "💰 Pay with Balance", callback_data="balance_purchase")])
            buttons.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")])
            await query.message.reply_text(
                messages[lang]["land_info"](
                    land["name_fa" if lang == "fa" else "name"],
                    land["price"],
                    daily_profit,
                    weekly_profit,
                    monthly_profit,
                    total_monthly,
                    land["seed_count"],
                    land["emoji"]
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return SELECT_LAND
        elif query.data == "confirm_land_purchase":
            land_idx = context.user_data.get("land_idx")
            land_price = context.user_data.get("land_price")
            if land_idx is None or land_price is None:
                logger.warning(f"Missing land_idx or land_price for user {user_id}")
                await query.message.reply_text(
                    messages[lang]["invalid_data"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            await query.message.reply_text(
                messages[lang]["ask_amount"].format(land_price),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return DEPOSIT_AMOUNT
        elif query.data == "balance_purchase":
            land_idx = context.user_data.get("land_idx")
            land_price = context.user_data.get("land_price")
            if land_idx is None or land_price is None:
                logger.warning(f"Missing land_idx or land_price for user {user_id}")
                await query.message.reply_text(
                    messages[lang]["invalid_data"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang)
                )
                return ConversationHandler.END
            land = LANDS[land_idx]
            daily_profit = round(land["price"] * land["daily_profit_rate"] * land["seed_count"], 3)
            weekly_profit = round(daily_profit * 7, 3)
            monthly_profit = round(daily_profit * 30, 3)
            total_monthly = round(land["price"] + monthly_profit, 3)
            await query.message.reply_text(
                messages[lang]["land_info"](
                    land["name_fa" if lang == "fa" else "name"],
                    land["price"],
                    daily_profit,
                    weekly_profit,
                    monthly_profit,
                    total_monthly,
                    land["seed_count"],
                    land["emoji"]
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
        logger.error(f"Error in handle_land_selection for user {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        await context.bot.send_message(
            chat_id=DEFAULT_ADMIN_ID,
            text=f"⚠️ *Error in handle_land_selection for user {user_id}*: {str(e)}",
            parse_mode="Markdown"
        )
        context.user_data.clear()
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
                messages[lang]["ask_withdraw_address"](network, wallet_addresses[network]),
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
     
# Conversation states for manage users
MANAGE_USERS, ENTER_USER_ID, BAN_USER, SEED_ACTION, SELECT_SEED_ADD, SELECT_SEED_REMOVE, BALANCE_ACTION, ENTER_BALANCE_AMOUNT, VIEW_USERS = range(10, 19)

async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manage users menu."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await query.message.reply_text(messages["en"]["unauthorized"], parse_mode="Markdown")
        return ConversationHandler.END
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"Admin {user_id} opened manage users menu")
    await query.message.reply_text(
        messages[lang]["manage_users_menu"],
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 مشاهده کاربران" if lang == "fa" else "👥 View Users", callback_data="view_users")],
            [InlineKeyboardButton(messages[lang]["ban_user"], callback_data="ban_user")],
            [InlineKeyboardButton(messages[lang]["manage_seeds"], callback_data="manage_seeds")],
            [InlineKeyboardButton(messages[lang]["manage_balance"], callback_data="manage_balance")],
            [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="back_to_menu")]
        ])
    )
    return MANAGE_USERS

async def handle_manage_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manage users callback."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await query.message.reply_text(messages["en"]["unauthorized"], parse_mode="Markdown")
        return ConversationHandler.END
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"Admin {user_id} selected manage users action: {query.data}")

    if query.data == "ban_user":
        context.user_data["manage_action"] = "ban_user"
        await query.message.reply_text(
            messages[lang]["ask_user_id"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
            ])
        )
        return ENTER_USER_ID
    elif query.data == "manage_seeds":
        context.user_data["manage_action"] = "manage_seeds"
        await query.message.reply_text(
            messages[lang]["ask_seed_action"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(messages[lang]["add_seed"], callback_data="add_seed")],
                [InlineKeyboardButton(messages[lang]["remove_seed"], callback_data="remove_seed")],
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
            ])
        )
        return SEED_ACTION
    elif query.data == "manage_balance":
        context.user_data["manage_action"] = "manage_balance"
        await query.message.reply_text(
            messages[lang]["ask_balance_action"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(messages[lang]["add_balance"], callback_data="add_balance")],
                [InlineKeyboardButton(messages[lang]["subtract_balance"], callback_data="subtract_balance")],
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
            ])
        )
        return BALANCE_ACTION
    elif query.data == "manage_users":
        await manage_users(update, context)
        return MANAGE_USERS
    else:
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang, user_id)
        )
        return ConversationHandler.END


async def handle_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user ban confirmation."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await query.message.reply_text(messages["en"]["unauthorized"], parse_mode="Markdown")
        return ConversationHandler.END
    user = get_user(user_id)
    lang = user[0] if user else "en"
    target_user_id = context.user_data.get("target_user_id")
    logger.info(f"Admin {user_id} confirming ban for user {target_user_id}")

    if query.data == "confirm_ban":
        if not target_user_id:
            await query.message.reply_text(
                messages[lang]["invalid_user_id"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang, user_id)
            )
            return ConversationHandler.END
        try:
            if ban_user(target_user_id):
                await query.message.reply_text(
                    messages[lang]["user_banned"](target_user_id),
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang, user_id)
                )
            else:
                await query.message.reply_text(
                    messages[lang]["invalid_user_id"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang, user_id)
                )
            context.user_data.clear()
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Error banning user {target_user_id} by admin {user_id}: {e}")
            await query.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang, user_id)
            )
            return ConversationHandler.END
    elif query.data == "manage_users":
        await manage_users(update, context)
        return MANAGE_USERS
    else:
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang, user_id)
        )
        return ConversationHandler.END

async def handle_land_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle land action selection (add/remove)."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await query.message.reply_text(messages["en"]["unauthorized"], parse_mode="Markdown")
        return ConversationHandler.END
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"Admin {user_id} selected land action: {query.data}")

    if query.data in ["add_land", "remove_land"]:
        context.user_data["land_action"] = query.data
        context.user_data["manage_action"] = "manage_lands"  # Context for land management
        await query.message.reply_text(
            messages[lang]["ask_user_id"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
            ])
        )
        return ENTER_USER_ID
    elif query.data == "manage_users":
        await manage_users(update, context)
        return MANAGE_USERS
    else:
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang, user_id)
        )
        return ConversationHandler.END


async def handle_seed_selection_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle seed selection for add/remove."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await query.message.reply_text(messages["en"]["unauthorized"], parse_mode="Markdown")
        return ConversationHandler.END
    user = get_user(user_id)
    lang = user[0] if user else "en"
    target_user_id = context.user_data.get("target_user_id")
    logger.info(f"Admin {user_id} selected seed action for user {target_user_id}: {query.data}")

    try:
        if query.data.startswith("add_seed_"):
            seed_idx = int(query.data.split("_")[2])
            seed = SEEDS[seed_idx]
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as c:
                    c.execute('SELECT seed_id FROM seeds WHERE name = %s', (seed["name"],))
                    seed_id = c.fetchone()[0]
            add_user_seed_admin(target_user_id, seed_id)
            await query.message.reply_text(
                messages[lang]["seed_added"](seed["name_fa" if lang == "fa" else "name"], target_user_id),
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang, user_id)
            )
            context.user_data.clear()
            return ConversationHandler.END
        elif query.data.startswith("remove_seed_"):
            user_seed_id = int(query.data.split("_")[2])
            seed_info = get_user_seed(target_user_id, user_seed_id)
            if not seed_info:
                await query.message.reply_text(
                    messages[lang]["invalid_data"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang, user_id)
                )
                return ConversationHandler.END
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as c:
                    c.execute('SELECT name, name_fa FROM seeds WHERE seed_id = %s', (seed_info[0],))
                    seed_name, seed_name_fa = c.fetchone()
            if remove_user_seed(target_user_id, user_seed_id):
                await query.message.reply_text(
                    messages[lang]["seed_removed"](seed_name_fa if lang == "fa" else seed_name, target_user_id),
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang, user_id)
                )
            else:
                await query.message.reply_text(
                    messages[lang]["invalid_data"],
                    parse_mode="Markdown",
                    reply_markup=get_main_menu(lang, user_id)
                )
            context.user_data.clear()
            return ConversationHandler.END
        elif query.data == "manage_users":
            await manage_users(update, context)
            return MANAGE_USERS
        else:
            await query.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang, user_id)
            )
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in handle_seed_selection_admin for admin {user_id}: {e}")
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang, user_id)
        )
        return ConversationHandler.END

async def handle_balance_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle balance action selection (add/subtract)."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await query.message.reply_text(messages["en"]["unauthorized"], parse_mode="Markdown")
        return ConversationHandler.END
    user = get_user(user_id)
    lang = user[0] if user else "en"
    logger.info(f"Admin {user_id} selected balance action: {query.data}")

    if query.data in ["add_balance", "subtract_balance"]:
        context.user_data["balance_action"] = query.data
        context.user_data["manage_action"] = "manage_balance"  # اضافه کردن کنتکست
        await query.message.reply_text(
            messages[lang]["ask_user_id"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
            ])
        )
        return ENTER_USER_ID
    elif query.data == "manage_users":
        await manage_users(update, context)
        return MANAGE_USERS
    else:
        await query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang, user_id)
        )
        return ConversationHandler.END


async def handle_balance_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle balance amount input."""
    user_id = update.effective_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await update.message.reply_text(messages["en"]["unauthorized"], parse_mode="Markdown")
        return ConversationHandler.END
    user = get_user(user_id)
    lang = user[0] if user else "en"
    target_user_id = context.user_data.get("target_user_id")
    balance_action = context.user_data.get("balance_action")
    input_text = update.message.text.strip()
    logger.info(f"Admin {user_id} entered balance amount for user {target_user_id}: {input_text}")

    try:
        amount = float(input_text)
        if amount <= 0:
            await update.message.reply_text(
                messages[lang]["invalid_balance_amount"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
                ])
            )
            return ENTER_BALANCE_AMOUNT
        amount = amount if balance_action == "add_balance" else -amount
        update_balance(target_user_id, amount)
        action_text = "افزایش یافت" if balance_action == "add_balance" else "کاهش یافت" if lang == "fa" else \
                      "increased" if balance_action == "add_balance" else "decreased"
        await update.message.reply_text(
            messages[lang]["balance_updated"](target_user_id, abs(amount), action_text),
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang, user_id)
        )
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            messages[lang]["invalid_balance_amount"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
            ])
        )
        return ENTER_BALANCE_AMOUNT
    except Exception as e:
        logger.error(f"Error in handle_balance_amount for admin {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang, user_id)
        )
        return ConversationHandler.END

async def handle_user_id_common(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user ID input for ban, seed management, or balance management."""
    user_id = update.effective_user.id
    if user_id != DEFAULT_ADMIN_ID:
        await update.message.reply_text(messages["en"]["unauthorized"], parse_mode="Markdown")
        return ConversationHandler.END
    user = get_user(user_id)
    lang = user[0] if user else "en"
    input_text = update.message.text.strip()
    logger.info(f"Admin {user_id} entered user ID: {input_text}")

    try:
        target_user_id = int(input_text)
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                c.execute('SELECT user_id FROM users WHERE user_id = %s AND is_banned = FALSE', (target_user_id,))
                if not c.fetchone():
                    await update.message.reply_text(
                        messages[lang]["invalid_user_id"],
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
                        ])
                    )
                    return ENTER_USER_ID
        context.user_data["target_user_id"] = target_user_id

        # بررسی کنتکست برای تصمیم‌گیری
        if context.user_data.get("manage_action") == "ban_user":
            await update.message.reply_text(
                messages[lang]["confirm_ban_user"](target_user_id),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ تأیید" if lang == "fa" else "✅ Confirm", callback_data="confirm_ban")],
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
                ])
            )
            return BAN_USER
        elif context.user_data.get("manage_action") == "manage_seeds":
            seed_action = context.user_data.get("seed_action")
            if seed_action == "add_seed":
                keyboard = [
                    [InlineKeyboardButton(seed["name_fa" if lang == "fa" else "name"] + f" {seed['emoji']}", callback_data=f"add_seed_{idx}")]
                    for idx, seed in enumerate(SEEDS)
                ]
                keyboard.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")])
                await update.message.reply_text(
                    messages[lang]["select_seed_to_add"],
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return SELECT_SEED_ADD
            else:  # remove_seed
                user_seeds = get_user_seeds(target_user_id)
                if not user_seeds:
                    await update.message.reply_text(
                        messages[lang]["no_seeds_to_remove"],
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
                        ])
                    )
                    return MANAGE_USERS
                keyboard = [
                    [InlineKeyboardButton(f"{seed[1 if lang == 'fa' else 0]} (ID: {seed[6]})", callback_data=f"remove_seed_{seed[6]}")]
                    for seed in user_seeds
                ]
                keyboard.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")])
                await update.message.reply_text(
                    messages[lang]["select_seed_to_remove"],
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return SELECT_SEED_REMOVE
        elif context.user_data.get("manage_action") == "manage_balance":
            await update.message.reply_text(
                messages[lang]["ask_balance_amount"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
                ])
            )
            return ENTER_BALANCE_AMOUNT
        else:
            await update.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=get_main_menu(lang, user_id)
            )
            return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            messages[lang]["invalid_user_id"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
            ])
        )
        return ENTER_USER_ID
    except Exception as e:
        logger.error(f"Error in handle_user_id_common for admin {user_id}: {e}")
        await update.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang, user_id)
        )
        return ConversationHandler.END 

def get_users_paginated(page=1, page_size=5):
    """Retrieve paginated list of users from the database."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                offset = (page - 1) * page_size
                c.execute('''
                    SELECT user_id, username, created_at, balance, is_banned
                    FROM users
                    WHERE is_banned = FALSE
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                ''', (page_size, offset))
                users = c.fetchall()
                c.execute('SELECT COUNT(*) FROM users WHERE is_banned = FALSE')
                total_users = c.fetchone()[0]
                logger.info(f"Fetched {len(users)} users for page {page}, total users: {total_users}")
                return users, total_users
    except Exception as e:
        logger.error(f"Error fetching paginated users: {e}")
        raise               

async def view_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle view users menu with pagination."""
    query = update.callback_query
    logger.info(f"View_users called with callback data: {query.data} by user {query.from_user.id}")
    try:
        await query.answer()
        user_id = query.from_user.id
        logger.info(f"Checking admin access for user {user_id}")
        if user_id != DEFAULT_ADMIN_ID:
            logger.warning(f"Unauthorized access attempt by user {user_id}")
            await query.message.reply_text(messages["en"]["unauthorized"], parse_mode="Markdown")
            return ConversationHandler.END
        user = get_user(user_id)
        lang = user[0] if user else "en"
        logger.info(f"Admin {user_id} opened view users menu with lang {lang}")

        # گرفتن شماره صفحه از callback_data یا user_data
        if query.data.startswith("page_"):
            page = int(query.data.split("_")[1])
            context.user_data["users_page"] = page
        else:
            page = int(context.user_data.get("users_page", 1))
        logger.info(f"Fetching users for page {page}")

        users, total_users = get_users_paginated(page=page)
        logger.info(f"Retrieved {len(users)} users, total users: {total_users}")
        total_pages = (total_users + 4) // 5  # محاسبه تعداد صفحات (هر صفحه ۵ کاربر)

        if not users:
            logger.info("No users found")
            await query.message.reply_text(
                "📋 *هیچ کاربری یافت نشد!*" if lang == "fa" else "📋 *No users found!*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
                ])
            )
            return MANAGE_USERS

        # ساخت دکمه‌های شیشه‌ای برای کاربران
        logger.info("Building user buttons")
        keyboard = [
            [InlineKeyboardButton(f"@{user[1] or 'No Username'} (ID: {user[0]})", callback_data=f"view_user_{user[0]}")]
            for user in users
        ]

        # اضافه کردن دکمه‌های صفحه‌بندی
        navigation_buttons = []
        if page > 1:
            navigation_buttons.append(InlineKeyboardButton("⬅️ قبلی" if lang == "fa" else "⬅️ Previous", callback_data=f"page_{page-1}"))
        if page < total_pages:
            navigation_buttons.append(InlineKeyboardButton("بعدی ➡️" if lang == "fa" else "Next ➡️", callback_data=f"page_{page+1}"))
        if navigation_buttons:
            keyboard.append(navigation_buttons)
        keyboard.append([InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")])
        logger.info(f"Keyboard built with {len(keyboard)} rows")

        # لاگ قبل از ارسال پیام
        logger.info(f"Sending user list for page {page} to admin {user_id}")
        await query.message.reply_text(
            f"📋 *لیست کاربران (صفحه {page} از {total_pages})*\n"
            f"تعداد کل کاربران: {total_users}" if lang == "fa" else
            f"📋 *User List (Page {page} of {total_pages})*\n"
            f"Total Users: {total_users}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"Successfully sent user list for page {page} to admin {user_id}")
        return VIEW_USERS
    except Exception as e:
        logger.error(f"Critical error in view_users for admin {user_id}: {str(e)}", exc_info=True)
        try:
            await query.message.reply_text(
                messages[lang]["error"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="manage_users")]
                ])
            )
            logger.info(f"Sent error message to admin {user_id}")
        except Exception as reply_error:
            logger.error(f"Failed to send error message to admin {user_id}: {str(reply_error)}")
        return MANAGE_USERS

async def view_user_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display detailed information about a selected user using lands."""
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    if user_id != DEFAULT_ADMIN_ID:
        query.message.reply_text(messages["en"]["unauthorized"], parse_mode="Markdown")
        return ConversationHandler.END
    user = get_user(user_id)
    lang = user[0] if user else "en"
    target_user_id = int(query.data.split("_")[2])
    logger.info(f"Admin {user_id} viewing details for user {target_user_id}")

    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as c:
                # Get user info
                c.execute('''
                    SELECT user_id, username, balance, created_at
                    FROM users
                    WHERE user_id = %s AND is_banned = FALSE
                ''', (target_user_id,))
                user_info = c.fetchone()
                if not user_info:
                    query.message.reply_text(
                        messages[lang]["invalid_user_id"],
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="view_users")]
                        ])
                    )
                    return VIEW_USERS

                user_id, username, balance, created_at = user_info

                # Get lands
                c.execute('''
                    SELECT l.name, l.name_fa
                    FROM user_lands ul
                    JOIN lands l ON ul.land_id = l.land_id
                    WHERE ul.user_id = %s
                ''', (target_user_id,))
                lands = [row[1] if lang == "fa" else row[0] for row in c.fetchall()]
                lands_text = ", ".join(lands) if lands else "هیچ زمینی ندارد" if lang == "fa" else "No lands yet"

                # Get total profit
                c.execute('SELECT SUM(amount) FROM profits WHERE user_id = %s', (target_user_id,))
                land_profit = c.fetchone()[0] or 0.0
                c.execute('SELECT SUM(profit_amount) FROM referral_profits WHERE referrer_id = %s', (target_user_id,))
                referral_profit = c.fetchone()[0] or 0.0
                total_profit = land_profit + referral_profit

                # Get transaction count
                c.execute('SELECT COUNT(*) FROM transactions WHERE user_id = %s AND status = %s', (target_user_id, 'confirmed'))
                transaction_count = c.fetchone()[0]

                # Get last transaction
                c.execute('SELECT created_at FROM transactions WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT 1', (target_user_id, 'confirmed'))
                last_transaction = c.fetchone()[0] if c.rowcount > 0 else None

                # Get referral counts
                c.execute('''
                    SELECT level, COUNT(*)
                    FROM referrals
                    WHERE referrer_id = %s
                    GROUP BY level
                ''', (target_user_id,))
                level_counts = {1: 0, 2: 0, 3: 0}
                for level, count in c.fetchall():
                    level_counts[level] = count

        response = (
            f"👤 *جزئیات کاربر*\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"🆔 *آیدی عددی*: `{user_id}`\n"
            f"📛 *یوزرنیم*: @{username or 'بدون یوزرنیم'}\n"
            f"📅 *تاریخ ثبت‌نام*: {created_at}\n"
            f"💰 *موجودی*: `{balance}` تتر\n"
            f"🌱 *زمین‌ها*: {lands_text}\n"
            f"📈 *کل سود کسب‌شده*: `{total_profit}` تتر\n"
            f"📝 *تراکنش‌های موفق*: `{transaction_count}`\n"
            f"⏰ *آخرین تراکنش*: {'ندارد' if not last_transaction else last_transaction}\n"
            f"🤝 *رفرال‌ها*:\n"
            f"  📌 سطح ۱: `{level_counts[1]}` نفر\n"
            f"  📌 سطح ۲: `{level_counts[2]}` نفر\n"
            f"  📌 سطح ۳: `{level_counts[3]}` نفر\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌"
        ) if lang == "fa" else (
            f"👤 *User Details*\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            f"🆔 *User ID*: `{user_id}`\n"
            f"📛 *Username*: @{username or 'No Username'}\n"
            f"📅 *Join Date*: {created_at}\n"
            f"💰 *Balance*: `{balance}` USDT\n"
            f"🌱 *Lands*: {lands_text}\n"
            f"📈 *Total Profit Earned*: `{total_profit}` USDT\n"
            f"📝 *Successful Transactions*: `{transaction_count}`\n"
            f"⏰ *Last Transaction*: {'None' if not last_transaction else last_transaction}\n"
            f"🤝 *Referrals*:\n"
            f"  📌 Level 1: `{level_counts[1]}` workers\n"
            f"  📌 Level 2: `{level_counts[2]}` workers\n"
            f"  📌 Level 3: `{level_counts[3]}` workers\n"
            f"╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌"
        )

        query.message.reply_text(
            response,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="view_users")]
            ])
        )
        return VIEW_USERS
    except Exception as e:
        logger.error(f"Error in view_user_details for admin {user_id}, user {target_user_id}: {e}")
        query.message.reply_text(
            messages[lang]["error"],
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت" if lang == "fa" else "🔙 Back", callback_data="view_users")]
            ])
        )
        return VIEW_USERS

async def debug_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log all callback queries for debugging."""
    query = update.callback_query
    logger.info(f"Debug: Received callback query with data: {query.data} from user {query.from_user.id}")
    await query.answer()     

async def temp_view_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Temporary handler to debug view_users callback."""
    query = update.callback_query
    logger.info(f"Temp view_users called with callback data: {query.data} by user {query.from_user.id}")
    await query.answer()
    await view_users(update, context)  # فراخوانی تابع اصلی view_users

async def debug_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log current conversation state for debugging."""
    current_state = context.user_data.get('__conversation_state', 'Unknown')
    logger.info(f"Debug: Current conversation state for user {update.effective_user.id}: {current_state}")
    if update.callback_query:
        logger.info(f"Debug: Handling callback query with data: {update.callback_query.data} in state {current_state}")
    return current_state              

def main():
    """Run the bot."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not found in environment variables")
        exit(1)

    # Initialize database and fix users table
    logger.info("Starting database initialization")
    init_db()
    fix_users_table()
    logger.info("Database initialization and users table fix completed")

    # Build the application
    logger.info("Building Telegram application")
    app = ApplicationBuilder().token(token).build()


    # Define conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(
                handle_menu_callback,
                pattern=r"^(buy_land|wallet|referral|language|support|withdraw|history|plant_land|harvest_land|referral_\d+)$"
            ),
            CallbackQueryHandler(handle_language_callback, pattern=r"^lang_.*$"),
            CallbackQueryHandler(handle_land_selection, pattern=r"^(land_\d+|confirm_land_purchase|balance_purchase)$"),
            CallbackQueryHandler(handle_deposit_network, pattern=r"^network_.*$"),
            CallbackQueryHandler(handle_plant_land, pattern=r"^plant_\d+$"),
            CallbackQueryHandler(handle_harvest_land, pattern=r"^harvest_\d+$"),
            CallbackQueryHandler(handle_admin_action, pattern=r"^(approve|reject)_\d+$"),
            CallbackQueryHandler(handle_balance_purchase, pattern=r"^confirm_balance_purchase$"),
            CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            CallbackQueryHandler(manage_users, pattern=r"^manage_users$"),
            CallbackQueryHandler(handle_manage_users_callback, pattern=r"^(ban_user|manage_lands|manage_balance)$"),
            CallbackQueryHandler(handle_ban_user, pattern=r"^confirm_ban$"),
            CallbackQueryHandler(handle_land_action, pattern=r"^(add_land|remove_land)$"),
            CallbackQueryHandler(handle_land_selection_admin, pattern=r"^(add_land_\d+|remove_land_\d+)$"),
            CallbackQueryHandler(handle_balance_action, pattern=r"^(add_balance|subtract_balance)$"),
            CallbackQueryHandler(view_users, pattern=r"^view_users$"),
            CallbackQueryHandler(view_users, pattern=r"^page_\d+$"),
            CallbackQueryHandler(view_user_details, pattern=r"^view_user_\d+$"),
        ],
        states={
            SELECT_LAND: [
                CallbackQueryHandler(
                    handle_land_selection,
                    pattern=r"^(land_\d+|confirm_land_purchase|balance_purchase)$"
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
            PLANT_LAND: [
                CallbackQueryHandler(
                    handle_plant_land,
                    pattern=r"^plant_\d+$"
                ),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            HARVEST_LAND: [
                CallbackQueryHandler(
                    handle_harvest_land,
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
            MANAGE_USERS: [
                CallbackQueryHandler(handle_manage_users_callback, pattern=r"^(ban_user|manage_lands|manage_balance)$"),
                CallbackQueryHandler(manage_users, pattern=r"^manage_users$"),
                CallbackQueryHandler(view_users, pattern=r"^view_users$"),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            VIEW_USERS: [
                CallbackQueryHandler(view_users, pattern=r"^page_\d+$"),
                CallbackQueryHandler(view_user_details, pattern=r"^view_user_\d+$"),
                CallbackQueryHandler(manage_users, pattern=r"^manage_users$"),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            ENTER_USER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_id_common),
                CallbackQueryHandler(manage_users, pattern=r"^manage_users$"),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            BAN_USER: [
                CallbackQueryHandler(handle_ban_user, pattern=r"^confirm_ban$"),
                CallbackQueryHandler(manage_users, pattern=r"^manage_users$"),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            LAND_ACTION: [
                CallbackQueryHandler(handle_land_action, pattern=r"^(add_land|remove_land)$"),
                CallbackQueryHandler(manage_users, pattern=r"^manage_users$"),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            SELECT_LAND_ADD: [
                CallbackQueryHandler(handle_land_selection_admin, pattern=r"^add_land_\d+$"),
                CallbackQueryHandler(manage_users, pattern=r"^manage_users$"),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            SELECT_LAND_REMOVE: [
                CallbackQueryHandler(handle_land_selection_admin, pattern=r"^remove_land_\d+$"),
                CallbackQueryHandler(manage_users, pattern=r"^manage_users$"),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            BALANCE_ACTION: [
                CallbackQueryHandler(handle_balance_action, pattern=r"^(add_balance|subtract_balance)$"),
                CallbackQueryHandler(manage_users, pattern=r"^manage_users$"),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
            ENTER_BALANCE_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_balance_amount),
                CallbackQueryHandler(manage_users, pattern=r"^manage_users$"),
                CallbackQueryHandler(handle_back, pattern=r"^(back_to_menu|wallet)$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", cancel),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message),
            CallbackQueryHandler(debug_conversation),
        ],
        per_message=False
    )

    # Add handlers to the application
    logger.info("Adding handlers to the application")
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
    app.add_handler(CommandHandler("checklands", check_lands))
    app.add_handler(CommandHandler("test_referral_profit", test_referral_profit))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("debug_referrals", debug_referrals))
    app.add_handler(CommandHandler("debug_balance", debug_balance))
    app.add_handler(CallbackQueryHandler(debug_callback))
    app.add_handler(conv_handler)

    # Start the bot
    logger.info("Starting bot")
    app.run_polling()

if __name__ == "__main__":
    main()
