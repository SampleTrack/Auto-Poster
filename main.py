import os
import logging
import requests
import datetime
import pytz
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

# 3. SETUP LOGGING (Save to file AND print to console)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_errors.txt"), # Saves errors to this file
        logging.StreamHandler() # Prints to Render Console
    ]
)

# --- CORE FUNCTIONS ---

async def get_quote_and_image():
    """Helper function to fetch data so we don't repeat code."""
    try:
        # Get Quote
        q_response = requests.get("https://zenquotes.io/api/random")
        q_data = q_response.json()[0]
        quote = q_data['q']
        author = q_data['a']

        # Generate Image
        prompt = f"epic cinematic scenery, motivational, hyperrealistic, 8k, {quote[:20]}"
        image_url = f"https://image.pollinations.ai/prompt/{prompt}?nologo=true"

        # Create Caption
        caption = (
            f"❝ {quote} ❞\n\n"
            f"~ *{author}*\n\n"
            f"👇 **Start Your Journey:**\n"
            f"[{AD_TEXT}]({AD_LINK})"
        )
        return image_url, caption
    except Exception as e:
        logging.error(f"Error generating content: {e}")
        return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 **Bot Active!**\n\n"
        "✅ `/post_now` - Preview a post (Review before sending)\n"
        "✅ `/log` - Download error log file\n"
        "✅ `/set_time HH:MM` - Set daily schedule\n"
        "✅ `/stop` - Stop schedule"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

# --- LOGGING COMMAND ---

async def send_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the bot_errors.txt file to the user."""
    chat_id = update.effective_chat.id
    try:
        if os.path.exists("bot_errors.txt"):
            await context.bot.send_document(
                chat_id=chat_id,
                document=open("bot_errors.txt", "rb"),
                filename="bot_errors.txt",
                caption="📄 Here are your system logs."
            )
        else:
            await context.bot.send_message(chat_id=chat_id, text="✅ Log file is empty or does not exist yet.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Could not send logs: {e}")

# --- POSTING LOGIC ---

async def automated_post(context: ContextTypes.DEFAULT_TYPE):
    """This runs automatically via the scheduler (Direct to Channel)."""
    logging.info("⏰ Scheduler Triggered. Generating content...")
    image_url, caption = await get_quote_and_image()
    
    if image_url:
        try:
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=image_url,
                caption=caption,
                parse_mode='Markdown'
            )
            logging.info("✅ Automated post sent to channel.")
        except Exception as e:
            logging.error(f"Failed to send automated post: {e}")
    else:
        logging.error("Failed to generate content for automated post.")

async def manual_preview_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered by /post_now. Sends to ADMIN first with a button."""
    await update.message.reply_text("🎨 Generating preview... please wait.")
    
    image_url, caption = await get_quote_and_image()
    
    if image_url:
        # Create the "Share" button
        keyboard = [[InlineKeyboardButton("🚀 Share to Channel", callback_data="share_post")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=image_url,
            caption=caption,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        await update.message.reply_text("👆 **Review this.** Click the button above to post it to the channel.")
    else:
        await update.message.reply_text("❌ Failed to generate content. Check /log.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Share to Channel' button click."""
    query = update.callback_query
    await query.answer() # Stop loading animation

    if query.data == "share_post":
        try:
            # We copy the message from the Admin Chat -> Public Channel
            # This is safer/faster than regenerating the image
            message = query.message
            
            # Get the highest quality photo file ID
            file_id = message.photo[-1].file_id
            caption = message.caption_markdown  # Use markdown caption

            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=file_id,
                caption=caption,
                parse_mode='Markdown'
            )
            
            await query.edit_message_reply_markup(reply_markup=None) # Remove button
            await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ **Posted to Channel!**")
            logging.info("Manual post shared to channel by admin.")

        except Exception as e:
            logging.error(f"Button share failed: {e}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Error sharing to channel. Check /log.")

# --- SCHEDULING COMMANDS ---

async def set_daily_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/set_time HH:MM`")
        return
    time_str = context.args[0]
    try:
        h, m = map(int, time_str.split(':'))
        tz = pytz.timezone(TIMEZONE_STR)
        schedule_time = datetime.time(hour=h, minute=m, tzinfo=tz)
        
        # Clear old jobs
        jobs = context.job_queue.get_jobs_by_name(str(CHANNEL_ID))
        for job in jobs: job.schedule_removal()

        context.job_queue.run_daily(automated_post, time=schedule_time, chat_id=CHANNEL_ID, name=str(CHANNEL_ID))
        await update.message.reply_text(f"✅ Schedule set for {time_str}")
    except Exception as e:
        await update.message.reply_text("❌ Invalid format.")

async def stop_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = context.job_queue.get_jobs_by_name(str(CHANNEL_ID))
    for job in jobs: job.schedule_removal()
    await update.message.reply_text("🛑 Schedule stopped.")

# --- MAIN RUNNER ---

if __name__ == '__main__':
    if not TOKEN or not CHANNEL_ID:
        print("CRITICAL ERROR: Token or Channel ID missing!")
    else:
        keep_alive()
        
        app = ApplicationBuilder().token(TOKEN).build()

        # Command Handlers
        app.add_handler(CommandHandler(['start', 'help'], start))
        app.add_handler(CommandHandler('post_now', manual_preview_post)) # UPDATED
        app.add_handler(CommandHandler('log', send_logs)) # NEW
        app.add_handler(CommandHandler('set_time', set_daily_time))
        app.add_handler(CommandHandler('stop', stop_schedule))
        
        # Button Handler
        app.add_handler(CallbackQueryHandler(button_handler))

        # Default Schedule
        try:
            h, m = map(int, DEFAULT_TIME.split(':'))
            tz = pytz.timezone(TIMEZONE_STR)
            t_obj = datetime.time(hour=h, minute=m, tzinfo=tz)
            app.job_queue.run_daily(automated_post, time=t_obj, chat_id=CHANNEL_ID, name=str(CHANNEL_ID))
            print(f"✅ Bot Online. Schedule: {DEFAULT_TIME}")
        except:
            print("⚠️ Default schedule failed (Check Environment Variables)")

        app.run_polling()
