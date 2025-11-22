import os
import logging
import requests
import asyncio
import datetime
import pytz
from telegram import Bot
from telegram.ext import ApplicationBuilder
from keep_alive import keep_alive

# 1. CONFIGURATION
# Get these from your Environment Variables
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID") # Example: -100123456789 (Must start with -100)
# Set your timezone (e.g., 'Asia/Kolkata', 'America/New_York', 'UTC')
TIMEZONE = pytz.timezone('Asia/Kolkata') 
POST_TIME = "09:00" # The time you want the post to go out (24-hour format)

# 2. AFFILIATE AD (Appears in every caption)
AD_TEXT = "📚 Read the book that changed my life"
AD_LINK = "https://amzn.to/your-affiliate-link"

logging.basicConfig(level=logging.INFO)

async def generate_and_post():
    bot = Bot(token=TOKEN)
    
    try:
        # A. Get a Random Quote
        print("Fetching quote...")
        q_response = requests.get("https://zenquotes.io/api/random")
        q_data = q_response.json()[0]
        quote = q_data['q']
        author = q_data['a']
        
        # B. Generate AI Image
        # We create a visual prompt based on the quote context + "cinematic", "epic"
        print("Dreaming up image...")
        prompt = f"epic cinematic scenery, motivational, hyperrealistic, 8k, {quote[:20]}"
        image_url = f"https://image.pollinations.ai/prompt/{prompt}?nologo=true"
        
        # C. Create the Caption
        caption = (
            f"❝ {quote} ❞\n\n"
            f"~ *{author}*\n\n"
            f"👇 **Start Your Journey:**\n"
            f"[{AD_TEXT}]({AD_LINK})"
        )

        # D. Post to Channel
        print(f"Posting to {CHANNEL_ID}...")
        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=image_url,
            caption=caption,
            parse_mode='Markdown'
        )
        print("✅ Posted successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")

async def scheduler():
    print(f"⏰ Scheduler started! Waiting for {POST_TIME} ({TIMEZONE})...")
    while True:
        # Get current time in your specific timezone
        now = datetime.datetime.now(TIMEZONE)
        current_time = now.strftime("%H:%M")
        
        # Check if it is time to post
        if current_time == POST_TIME:
            await generate_and_post()
            # Sleep for 61 seconds so we don't post twice in the same minute
            await asyncio.sleep(61)
        else:
            # Check again every minute
            await asyncio.sleep(60)

if __name__ == '__main__':
    if not TOKEN or not CHANNEL_ID:
        print("CRITICAL ERROR: Token or Channel ID missing!")
    else:
        keep_alive() # Start the fake server to keep bot running
        
        # Run the scheduler loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(scheduler())
