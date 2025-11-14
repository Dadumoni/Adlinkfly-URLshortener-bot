import re
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from pymongo import MongoClient
import logging

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", ""))
SHORTENER_DOMAIN = ""
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", "")
DB_NAME = "telegram_bot"
COLLECTION_NAME = "users"
LINKS_COLLECTION_NAME = "shortened_links"

# MongoDB Client
try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    users_collection = db[COLLECTION_NAME]
    links_collection = db[LINKS_COLLECTION_NAME]
    logger.info("MongoDB connected successfully")
except Exception as e:
    logger.error(f"MongoDB connection error: {e}")

# Global app instance
app = None

# ---------------- DATABASE ----------------
def init_db():
    try:
        users_collection.create_index("user_id", unique=True)
        links_collection.create_index([("user_id", 1), ("slug", 1)])
        links_collection.create_index("slug")
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database init error: {e}")

def get_user(user_id):
    user = users_collection.find_one({"user_id": user_id})
    if user:
        return (
            user.get("api_token", ""),
            user.get("header", ""),
            user.get("footer", ""),
            user.get("channel", ""),
            user.get("mode", "keep")
        )
    return ("", "", "", "", "keep")

def update_user(user_id, **kwargs):
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": kwargs},
        upsert=True
    )

def reset_field(user_id, field):
    users_collection.update_one(
        {"user_id": user_id},
        {"$unset": {field: ""}}
    )

def save_shortened_link(user_id, slug, long_url):
    link_data = {"user_id": user_id, "slug": slug, "long_url": long_url}
    links_collection.insert_one(link_data)

def get_long_url_from_slug(slug):
    result = links_collection.find_one({"slug": slug})
    return result.get("long_url") if result else None

def get_shortened_link_by_user(user_id, long_url):
    result = links_collection.find_one({"user_id": user_id, "long_url": long_url})
    return f"https://{SHORTENER_DOMAIN}/{result.get('slug')}" if result else None

def extract_slug_from_url(short_url):
    parts = short_url.rstrip('/').split('/')
    return parts[-1] if len(parts) > 0 else ""

# ---------------- LINK SHORTENER ----------------
async def shorten_link(url: str, api_token: str) -> str:
    import aiohttp
    api_url = f"https://{SHORTENER_DOMAIN}/api?api={api_token}&url={url}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                data = await resp.json()
                return data.get("shortenedUrl", url)
    except Exception as e:
        logger.error(f"Shorten link error: {e}")
        return url

def extract_links(text):
    return re.findall(r'https?://[^\s]+', text)

# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    msg = f"""🖐️ Welcome {name} to {SHORTENER_DOMAIN} Bot!

I am Bulk Link Converter. I Can Convert Links Directly From Your {SHORTENER_DOMAIN} Account.

1️⃣ Create an Account on {SHORTENER_DOMAIN}
2️⃣ Go To 👉 https://{SHORTENER_DOMAIN}/member/tools/api
3️⃣ Copy your API Key
4️⃣ Send /set_api <API_KEY>
5️⃣ Now send me any link or media – I'll shorten it instantly!"""
    await update.message.reply_text(msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"""🛠️ *How To Use Bot?*
/set_api - connect with {SHORTENER_DOMAIN}
/add_header - add your header text
/delete_header - delete your header
/add_footer - add your footer text
/delete_footer - delete your footer
/add_channel - add your channel link/username
/delete_channel - delete your channel
/keep_text - keep original caption
/delete_text - remove caption and keep only links"""
    await update.message.reply_text(msg)

async def set_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("⚠️ Usage: /set_api <Your API Token>")
        return
    api_token = context.args[0]
    update_user(update.effective_user.id, api_token=api_token)
    await update.message.reply_text("✅ API Token saved successfully!")

async def add_header(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏️ Send Your Header Text!")
    context.user_data["awaiting"] = "header"

async def add_footer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏️ Send Your Footer Text!")
    context.user_data["awaiting"] = "footer"

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("⚠️ Usage: /add_channel <link or @username>")
        return
    channel = context.args[0]
    update_user(update.effective_user.id, channel=channel)
    await update.message.reply_text("✅ Channel saved successfully!")

async def delete_header(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_field(update.effective_user.id, "header")
    await update.message.reply_text("🧹 Header deleted successfully!")

async def delete_footer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_field(update.effective_user.id, "footer")
    await update.message.reply_text("🧹 Footer deleted successfully!")

async def delete_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_field(update.effective_user.id, "channel")
    await update.message.reply_text("🧹 Channel deleted successfully!")

async def keep_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user(update.effective_user.id, mode="keep")
    await update.message.reply_text("✅ Bot will keep original caption text.")

async def delete_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user(update.effective_user.id, mode="delete")
    await update.message.reply_text("🧹 Done 💯")

# ---------------- MESSAGE HANDLER ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id
    text = msg.caption or msg.text or ""
    api_token, header, footer, channel, mode = get_user(user_id)

    if "awaiting" in context.user_data:
        target = context.user_data.pop("awaiting")
        update_user(user_id, **{target: text})
        await msg.reply_text(f"✅ {target.capitalize()} saved successfully!")
        return

    try:
        await msg.copy(chat_id=CHANNEL_ID)
    except Exception as e:
        logger.error(f"Copy failed: {e}")

    links = extract_links(text)
    if not links:
        await msg.reply_text("❌ No valid link found.")
        return

    if not api_token:
        await msg.reply_text("⚠️ Please set your API token using /set_api first.")
        return

    telegram_links = []
    other_links = []
    for link in links:
        if "t.me" in link or link.startswith("@"):
            telegram_links.append(link)
        else:
            other_links.append(link)

    processed_links = []
    for link in other_links:
        if SHORTENER_DOMAIN in link:
            slug = extract_slug_from_url(link)
            long_url = get_long_url_from_slug(slug)
            if long_url:
                shortened = await shorten_link(long_url, api_token)
                processed_links.append((long_url, shortened))
            else:
                processed_links.append((link, link))
        else:
            existing_short = get_shortened_link_by_user(user_id, link)
            if existing_short:
                processed_links.append((link, existing_short))
            else:
                shortened = await shorten_link(link, api_token)
                processed_links.append((link, shortened))

    short_links = []
    for long_url, shortened in processed_links:
        short_links.append(shortened)
        if shortened != long_url and SHORTENER_DOMAIN in shortened:
            slug = extract_slug_from_url(shortened)
            if slug:
                existing = links_collection.find_one({"user_id": user_id, "slug": slug})
                if not existing:
                    save_shortened_link(user_id, slug, long_url)

    if mode == "keep":
        if channel:
            text = re.sub(r'(https?://t\.me/[^\s]+|@[\w_]+)', channel, text)
        else:
            text = re.sub(r'(https?://t\.me/[^\s]+|@[\w_]+)', '', text)
        
        for i, link in enumerate(other_links):
            text = text.replace(link, short_links[i])
        
        caption = f"{header}\n{text}\n{footer}".strip()
    else:
        caption = f"{header}\n" + "\n".join(short_links) + f"\n{footer}".strip()

    if msg.photo:
        await msg.reply_photo(photo=msg.photo[-1].file_id, caption=caption)
    elif msg.video:
        await msg.reply_video(video=msg.video.file_id, caption=caption)
    else:
        await msg.reply_text(caption)

# ---------------- WEBHOOK SETUP ----------------
async def initialize_app():
    global app
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("set_api", set_api))
    app.add_handler(CommandHandler("add_header", add_header))
    app.add_handler(CommandHandler("delete_header", delete_header))
    app.add_handler(CommandHandler("add_footer", add_footer))
    app.add_handler(CommandHandler("delete_footer", delete_footer))
    app.add_handler(CommandHandler("add_channel", add_channel))
    app.add_handler(CommandHandler("delete_channel", delete_channel))
    app.add_handler(CommandHandler("keep_text", keep_text))
    app.add_handler(CommandHandler("delete_text", delete_text))
    
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    
    init_db()
    await app.initialize()

# For Vercel deployment
async def handler(request):
    try:
        if app is None:
            await initialize_app()
        
        update = Update.de_json(await request.json(), app.bot)
        await app.process_update(update)
        return {"statusCode": 200}
    except Exception as e:
        logger.error(f"Handler error: {e}")
        return {"statusCode": 500, "body": str(e)}
