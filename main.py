import os
import logging
import requests
import datetime
import pytz
from io import BytesIO # Required for handling image data
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from keep_alive import keep_alive

# 1. CONFIGURATION
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
DEFAULT_TIME = os.getenv("POST_TIME", "09:00")
TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Kolkata")

# 2. AFFILIATE DATA
AD_TEXT = "📚 Read this book (40% Off)"
AD_LINK = "https://amzn.to/your-link"

# 3. SETUP LOGGING
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_errors.txt"),
        logging.StreamHandler()
    ]
)

# --- CORE FUNCTIONS ---

async def get_quote_and_image():
    """
    UPDATED: Downloads the image to memory first to prevent Telegram Timeouts.
    Returns: (image_bytes, caption)
    """
    try:
        # A. Get Quote
        q_response = requests.get("https://zenquotes.io/api/random", timeout=10)
        q_data = q_response.json()[0]
        quote = q_data['q']
        author = q_data['a']

        # B. Generate Image URL
        prompt = f"epic cinematic scenery, motivational, hyperrealistic, 8k, {quote[:20]}"
        image_url = f"https://image.pollinations.ai/prompt/{prompt}?nologo=true"

        # C. DOWNLOAD IMAGE (Fixes TimeOut Error)
        # We download the image to the Render server RAM first
        img_response = requests.get(image_url, timeout=30)
        img_bytes = BytesIO(img_response.content)
        img_bytes.name = 'motivation.jpg' # Give it a fake filename

        # D. Create Caption
        caption = (
            f"❝ {quote} ❞\n\n"
            f"~ *{author}*\n\n"
            f"👇 **Start Your Journey:**\n"
            f"[{AD_TEXT}]({AD_LINK})"
        )
        return img_bytes, caption

    except Exception as e:
        logging.error(f"Error generating content: {e}")
        return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 **Bot Active!**\n\n"
        "✅ `/post_now` - Preview a post\n"
        "✅ `/log` - Download error logs\n"
        "✅ `/set_time HH:MM` - Set schedule\n"
        "✅ `/stop` - Stop schedule"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def send_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        if os.path.exists("bot_errors.txt"):
            await context.bot.send_document(
                chat_id=chat_id,
                document=open("bot_errors.txt", "rb"),
                filename="bot_errors.txt",
                caption="📄 System Logs"
            )
        else:
            await context.bot.send_message(chat_id=chat_id, text="✅ No errors logged yet.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error sending logs: {e}")

# --- POSTING LOGIC ---

async def automated_post(context: ContextTypes.DEFAULT_TYPE):
    logging.info("⏰ Scheduler Triggered...")
    image_bytes, caption = await get_quote_and_image()
    
    if image_bytes:
        try:
            # Reset cursor to start of file
            image_bytes.seek(0)
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=image_bytes,
                caption=caption,
                parse_mode='Markdown',
                read_timeout=60,    # Give Telegram 60s to upload
                write_timeout=60,
                connect_timeout=60
            )
            logging.info("✅ Automated post sent.")
        except Exception as e:
            logging.error(f"Failed to send automated post: {e}")
    else:
        logging.error("Failed to generate content.")

async def manual_preview_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎨 Generating preview... (This takes ~10 seconds)")
    
    image_bytes, caption = await get_quote_and_image()
    
    if image_bytes:
        keyboard = [[InlineKeyboardButton("🚀 Share to Channel", callback_data="share_post")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        image_bytes.seek(0)
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=image_bytes,
            caption=caption,
            parse_mode='Markdown',
            reply_markup=reply_markup,
            read_timeout=60,
            write_timeout=60
        )
        await update.message.reply_text("👆 Review above. Click button to post.")
    else:
        await update.message.reply_text("❌ Generation failed. Check /log.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "share_post":
        try:
            message = query.message
            file_id = message.photo[-1].file_id
            caption = message.caption_markdown

            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=file_id,
                caption=caption,
                parse_mode='Markdown'
            )
            
            await query.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Posted to Channel!")

        except Exception as e:
            logging.error(f"Button share failed: {e}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Error sharing.")

# --- SCHEDULING ---

async def set_daily_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/set_time HH:MM`")
        return
    time_str = context.args[0]
    try:
        h, m = map(int, time_str.split(':'))
        tz = pytz.timezone(TIMEZONE_STR)
        schedule_time = datetime.time(hour=h, minute=m, tzinfo=tz)
        
        jobs = context.job_queue.get_jobs_by_name(str(CHANNEL_ID))
        for job in jobs: job.schedule_removal()

        context.job_queue.run_daily(automated_post, time=schedule_time, chat_id=CHANNEL_ID, name=str(CHANNEL_ID))
        await update.message.reply_text(f"✅ Schedule set for {time_str}")
    except Exception:
        await update.message.reply_text("❌ Invalid format.")

async def stop_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = context.job_queue.get_jobs_by_name(str(CHANNEL_ID))
    for job in jobs: job.schedule_removal()
    await update.message.reply_text("🛑 Schedule stopped.")

if __name__ == '__main__':
    if not TOKEN or not CHANNEL_ID:
        print("CRITICAL ERROR: Token or Channel ID missing!")
    else:
        keep_alive()
        
        # UPDATED: Increased connection timeouts for the bot itself
        builder = ApplicationBuilder().token(TOKEN)
        builder.read_timeout(60)
        builder.write_timeout(60)
        builder.connect_timeout(60)
        app = builder.build()

        app.add_handler(CommandHandler(['start', 'help'], start))
        app.add_handler(CommandHandler('post_now', manual_preview_post))
        app.add_handler(CommandHandler('log', send_logs))
        app.add_handler(CommandHandler('set_time', set_daily_time))
        app.add_handler(CommandHandler('stop', stop_schedule))
        app.add_handler(CallbackQueryHandler(button_handler))

        try:
            h, m = map(int, DEFAULT_TIME.split(':'))
            tz = pytz.timezone(TIMEZONE_STR)
            t_obj = datetime.time(hour=h, minute=m, tzinfo=tz)
            app.job_queue.run_daily(automated_post, time=t_obj, chat_id=CHANNEL_ID, name=str(CHANNEL_ID))
            print(f"✅ Bot Online. Schedule: {DEFAULT_TIME}")
        except:
            print("⚠️ Default schedule failed")

        app.run_polling()
