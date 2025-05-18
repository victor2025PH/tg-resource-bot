import os
import logging
import openai
import gspread
import base64
from datetime import datetime
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ===== 基础配置 =====
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://yourdomain.com")
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "secret-token"
GOOGLE_SHEET_NAME = os.getenv("GSHEET_NAME", "resources-data")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your-openai-key")

openai.api_key = OPENAI_API_KEY
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ===== Google Sheets 授权配置 =====
key_base64 = os.getenv("GSHEET_KEY_BASE64")
with open("service_account.json", "wb") as f:
    f.write(base64.b64decode(key_base64))

gc = gspread.service_account(filename="service_account.json")
sheet_resources = gc.open(GOOGLE_SHEET_NAME).worksheet("resources")
sheet_reports = gc.open(GOOGLE_SHEET_NAME).worksheet("reports")
sheet_interactions = gc.open(GOOGLE_SHEET_NAME).worksheet("interactions")

# ===== ChatGPT 调用 =====
async def ask_gpt(prompt: str):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message["content"]
    except Exception as e:
        logging.error(f"[GPT错误] {e}")
        return "抱歉，我暂时无法回答你的问题。"

# ===== 处理用户消息 =====
@dp.message()
async def handle_message(message: Message):
    text = message.text.strip()
    username = message.from_user.username or f"id_{message.from_user.id}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        if "我要资源" in text:
            await message.answer("📦 请进入频道 @YourChannel，查看最新资源")
            sheet_interactions.append_row([username, text, "资源请求", now])
        elif "我要发布" in text:
            await message.answer("📝 请按照格式发送资源内容：地区 + 类型 + 内容 + 联系方式")
            sheet_interactions.append_row([username, text, "资源发布意图", now])
        elif "举报" in text:
            await message.answer("⚠️ 请发送举报对象、理由、截图等内容")
            sheet_interactions.append_row([username, text, "举报意图", now])
        else:
            reply = await ask_gpt(text)
            await message.answer(reply)
            sheet_interactions.append_row([username, text, "AI回复", now])
    except Exception as e:
        logging.error(f"[消息处理错误] {e}")
        await message.answer("处理过程中出现错误，请稍后再试。")

# ===== Webhook 启动关闭配置 =====
async def on_startup(dispatcher: Dispatcher):
    await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}", secret_token=WEBHOOK_SECRET)

async def on_shutdown(dispatcher: Dispatcher):
    await bot.delete_webhook()

# ===== 启动入口 =====
def create_app():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    return app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
