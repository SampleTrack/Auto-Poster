import os
import logging
import requests
import datetime
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from keep_alive import keep_alive

# 1. LOGGING
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 2. CONFIGURATION (Loaded from Cloud Dashboard)
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
# Default time if not set: 09:00 AM
DEFAULT_TIME = os.getenv("POST_TIME", "09:00") 
# Your Timezone (e.g., Asia/Kolkata, UTC, Europe/London)
TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Kolkata")

# 3. AFFILIATE DATA
AD_TEXT = "📚 Read this book (40% Off)"
AD_LINK = "https://amzn.to/your-link"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the welcome message and help menu."""
    help_text = (
        "🤖 **Auto-Motivation Bot Active!**\n\n"
        "**Commands:**\n"
        "✅ `/start` - Show this menu\n"
        "✅ `/help` - How to use the bot\n"
        "✅ `/post_now` - Force a post immediately\n"
        "✅ `/set_time HH:MM` - Change daily post time (e.g., /set_time 14:30)\n"
        "✅ `/set_freq X` - Post X times a day (e.g., /set_freq 3)\n"
        "✅ `/stop` - Stop all scheduled posts"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explains how the bot works."""
    await update.message.reply_text(
        "ℹ️ **How it works:**\n"
        "1. The bot wakes up at your scheduled time.\n"
        "2. It grabs a random motivational quote.\n"
        "3. It uses AI to generate a unique image.\n"
        "4. It posts to your channel with your affiliate link.\n\n"
        "⚠️ *Note: On Render Free tier, use the Dashboard Variables to set permanent times.*",
        parse_mode='Markdown'
    )

async def generate_content(context: ContextTypes.DEFAULT_TYPE):
    """The worker function that actually generates and posts."""
    chat_id = context.job.chat_id
    
    try:
        # A. Get Quote
        q_response = requests.get("https://zenquotes.io/api/random")
        q_data = q_response.json()[0]
        quote = q_data['q']
        author = q_data['a']

        # B. Generate Image
        prompt = f"epic cinematic scenery, motivational, hyperrealistic, 8k, {quote[:20]}"
        image_url = f"https://image.pollinations.ai/prompt/{prompt}?nologo=true"

        # C. Caption
        caption = (
            f"❝ {quote} ❞\n\n"
            f"~ *{author}*\n\n"
            f"👇 **Start Your Journey:**\n"
            f"[{AD_TEXT}]({AD_LINK})"
        )

        # D. Post
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=image_url,
            caption=caption,
            parse_mode='Markdown'
        )
        logging.info("✅ Post sent successfully.")

    except Exception as e:
        logging.error(f"❌ Error sending post: {e}")

async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual trigger to post immediately."""
    await update.message.reply_text("🚀 Generating post... please wait 10 seconds.")
    # We manually create a job object to reuse the logic
    context.job_queue.run_once(generate_content, when=0, chat_id=CHANNEL_ID)

async def set_daily_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets the daily post time (e.g., /set_time 18:30)."""
    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/set_time HH:MM` (24-hour format)")
        return

    time_str = context.args[0]
    try:
        # Parse time
        hour, minute = map(int, time_str.split(':'))
        tz = pytz.timezone(TIMEZONE_STR)
        schedule_time = datetime.time(hour=hour, minute=minute, tzinfo=tz)

        # Remove existing jobs to avoid duplicates
        current_jobs = context.job_queue.get_jobs_by_name(str(CHANNEL_ID))
        for job in current_jobs:
            job.schedule_removal()

        # Set new job
        context.job_queue.run_daily(
            generate_content, 
            time=schedule_time, 
            chat_id=CHANNEL_ID, 
            name=str(CHANNEL_ID)
        )
        
        await update.message.reply_text(f"✅ Schedule updated! Next post at **{time_str}** ({TIMEZONE_STR}).", parse_mode='Markdown')

    except ValueError:
        await update.message.reply_text("❌ Invalid format. Use HH:MM (e.g., 14:30).")

async def set_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calculates intervals for X posts a day (e.g., /set_freq 4)."""
    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/set_freq 3` (for 3 posts a day)")
        return

    try:
        count = int(context.args[0])
        if count < 1 or count > 24:
            await update.message.reply_text("⚠️ Please choose between 1 and 24 posts per day.")
            return

        # Calculate seconds between posts (86400 seconds in a day)
        interval = 86400 / count

        # Remove old jobs
        current_jobs = context.job_queue.get_jobs_by_name(str(CHANNEL_ID))
        for job in current_jobs:
            job.schedule_removal()

        # Set repeating job
        context.job_queue.run_repeating(
            generate_content,
            interval=interval,
            first=10, # Start first post in 10 seconds
            chat_id=CHANNEL_ID,
            name=str(CHANNEL_ID)
        )

        await update.message.reply_text(f"✅ Frequency set! Posting **{count} times** per day (every {round(interval/3600, 1)} hours).")

    except ValueError:
        await update.message.reply_text("❌ Please enter a number.")

async def stop_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stops the bot from posting."""
    current_jobs = context.job_queue.get_jobs_by_name(str(CHANNEL_ID))
    for job in current_jobs:
        job.schedule_removal()
    await update.message.reply_text("🛑 All scheduled posts stopped.")

if __name__ == '__main__':
    if not TOKEN or not CHANNEL_ID:
        print("CRITICAL ERROR: Token or Channel ID missing!")
    else:
        keep_alive()
        
        application = ApplicationBuilder().token(TOKEN).build()

        # Commands
        application.add_handler(CommandHandler(['start', 'help'], start))
        application.add_handler(CommandHandler('post_now', post_now))
        application.add_handler(CommandHandler('set_time', set_daily_time))
        application.add_handler(CommandHandler('set_freq', set_frequency))
        application.add_handler(CommandHandler('stop', stop_schedule))

        # Set Default Schedule on Startup
        job_queue = application.job_queue
        
        # Parse Default Time from Environment Variable
        try:
            h, m = map(int, DEFAULT_TIME.split(':'))
            tz = pytz.timezone(TIMEZONE_STR)
            default_time_obj = datetime.time(hour=h, minute=m, tzinfo=tz)
            
            job_queue.run_daily(
                generate_content,
                time=default_time_obj,
                chat_id=CHANNEL_ID,
                name=str(CHANNEL_ID)
            )
            print(f"✅ System Online: Scheduled daily post at {DEFAULT_TIME} {TIMEZONE_STR}")
        except Exception as e:
            print(f"⚠️ Could not set default schedule: {e}")

        application.run_polling()
