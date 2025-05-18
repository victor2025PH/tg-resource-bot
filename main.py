# ✅ Webhook + 智能应答 + Google Sheets + YAML应答 + 关键词标准化版本

import asyncio
from aiogram import Bot, Dispatcher, types
import openai
import logging
import yaml
import csv
import datetime
import os
import random
import json
import base64
import gspread
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ================== 核心配置 ==================
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456"))
GROUP_LINK = os.getenv("GROUP_LINK", "https://t.me/+abc")
VIP_GROUP_LINK = os.getenv("VIP_GROUP_LINK", GROUP_LINK)
GOOGLE_SHEET_NAME = os.getenv("GSHEET_NAME", "resources-data")
key_base64 = os.getenv("GSHEET_KEY_BASE64")

WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "secret-token"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-bot-url.onrender.com") + WEBHOOK_PATH

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
client = openai.OpenAI(api_key=OPENAI_API_KEY)
logging.basicConfig(level=logging.INFO)
user_history = {}

# ============ 加载 YAML 问答 ============
with open('qas_multi_lang.yaml', encoding='utf8') as f:
    qas = yaml.safe_load(f)

# ============ Google Sheet 授权 ============
with open("service_account.json", "wb") as f:
    f.write(base64.b64decode(key_base64))

gc = gspread.service_account(filename="service_account.json")
sheet_resources = gc.open(GOOGLE_SHEET_NAME).worksheet("resources")
sheet_reports = gc.open(GOOGLE_SHEET_NAME).worksheet("reports")
sheet_interactions = gc.open(GOOGLE_SHEET_NAME).worksheet("interactions")

# ============ 分类逻辑 ============
def classify_persona(text):
    text = text.lower()
    if any(word in text for word in ['老板', '担保', '收单', '大额']):
        return "大客户"
    elif any(word in text for word in ['推广', '广告', '引流', '运营']):
        return "推广号"
    elif any(word in text for word in ['招聘', '工人', '司机', '人事']):
        return "资源中介"
    return "普通用户"

def classify_tag(text):
    tags = {
        "担保": ["担保", "押金", "中介", "信用"],
        "换汇": ["换汇", "汇率", "转账", "USDT", "币"],
        "收款": ["收款", "码", "通道", "微信", "支付宝"]
    }
    for tag, keywords in tags.items():
        if any(k in text for k in keywords):
            return tag
    return "其它"

# ============ YAML 应答 ============


def log_unmatched_keywords(text):
    fname = 'unmatched_keywords.json'
    try:
        with open(fname, 'r', encoding='utf8') as f:
            data = json.load(f)
    except:
        data = {}
    data[text] = data.get(text, 0) + 1
    with open(fname, 'w', encoding='utf8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def smart_match_qas(text):
    for qa in qas:
        for sub in qa.get('subcategories', []):
            for k in sub['keywords']:
                if k.lower() in text.lower():
                    reply = sub['reply']
                    return random.choice(reply) if isinstance(reply, list) else reply
    log_unmatched_keywords(text)
    return None

# ============ 日志记录 ============
def save_log(uid, text, reply, tag):
    if not os.path.exists('logs'):
        os.makedirs('logs')
    fname = f'logs/log_{datetime.date.today()}.csv'
    with open(fname, 'a', newline='', encoding='utf8') as f:
        csv.writer(f).writerow([datetime.datetime.now(), uid, text, reply, tag])

def get_hook_content_by_persona(persona):
    if persona == "大客户":
        return f"尊敬的贵宾，欢迎加入VIP对接群，专属撮合、优先推荐！进群链接：{VIP_GROUP_LINK}"
    elif persona == "推广号":
        return f"推广人专属福利群，资源互换、广告合作，欢迎加入主群：{GROUP_LINK}"
    elif persona == "资源中介":
        return f"中介资源专属群，供需撮合、信息同步，欢迎加入主群：{GROUP_LINK}"
    return f"加入资源互助主群，免费对接供需，合作交流：{GROUP_LINK}"

# ============ 消息处理 ============
@dp.message()
async def handle(message: types.Message):
    text = message.text.strip()
    text_clean = text.replace("：", ":").replace(" ", "").lower()
    uid = str(message.from_user.id)
    username = message.from_user.username or uid
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if "我要资源" in text_clean:
        await message.reply("📦 请进入频道 @YourChannel，查看最新资源")
        sheet_interactions.append_row([username, text, "资源请求", now])
        return

    if "我要发布" in text_clean:
        await message.reply("📝 请按照格式发送资源内容：地区 + 类型 + 内容 + 联系方式")
        sheet_interactions.append_row([username, text, "资源发布意图", now])
        return

    if "举报" in text_clean:
        sheet_reports.append_row([username, text, classify_tag(text), now, "待审核"])
        await message.reply("📩 举报信息已记录，我们将尽快处理。")
        return

    if text_clean in ['加群', '进群', '入群']:
        await message.reply(f"🎯 主群地址：{GROUP_LINK}")
        return

    if text_clean in ['你是谁', '你叫啥', '你叫什么']:
        await message.reply("我是资源撮合客服助手，欢迎提问。")
        return

    if text_clean.startswith("发布:"):
        try:
            region, res_type, content, contact = map(str.strip, text.replace("发布：", "").replace("发布:", "").split("+"))
            tag = classify_tag(content + contact)
            sheet_resources.append_row([region, res_type, content, contact, tag, now])
            await message.reply("✅ 资源已提交，管理员审核后将上线。")
        except:
            await message.reply("格式错误，正确格式：发布：地区 + 类型 + 内容 + 联系方式")
        return

    ans = smart_match_qas(text)
    if ans:
        await message.reply(ans)
        return

    msgs = user_history.get(uid, [])
    msgs.append({"role": "user", "content": text})
    if len(msgs) > 10:
        msgs = msgs[-10:]
    try:
        reply = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=msgs,
            temperature=0.7
        ).choices[0].message.content
    except Exception as e:
        reply = f"AI错误：{e}"

    msgs.append({"role": "assistant", "content": reply})
    user_history[uid] = msgs
    await message.reply(reply)
    save_log(uid, text, reply, classify_persona(text))

# ============ Webhook 启动 ============
async def on_startup(dispatcher: Dispatcher):
    await bot.set_webhook(url=WEBHOOK_URL, secret_token=WEBHOOK_SECRET)

async def on_shutdown(dispatcher: Dispatcher):
    await bot.delete_webhook()

def create_app():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    return app

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
