messages = {
    "fa": {
        "start": "سلام! زبان مورد نظر را انتخاب کن:",
        "ask_amount": "لطفا مقدار سرمایه‌گذاری را وارد کن (مثلا 100 تتر):",
        "result": lambda amount: f"""💵 با سرمایه‌گذاری {amount} تتر:
📆 سود روزانه: {round(amount * 0.5 / 30, 2)} تتر
📅 سود هفتگی: {round(amount * 0.5 / 4, 2)} تتر
🗓️ سود ماهانه: {round(amount * 0.5, 2)} تتر"""
    },
    "en": {
        "start": "Hello! Please choose your language:",
        "ask_amount": "Please enter the investment amount (e.g. 100 USDT):",
        "result": lambda amount: f"""💵 If you invest {amount} USDT:
📆 Daily profit: {round(amount * 0.5 / 30, 2)} USDT
📅 Weekly profit: {round(amount * 0.5 / 4, 2)} USDT
🗓️ Monthly profit: {round(amount * 0.5, 2)} USDT"""
    }
}
