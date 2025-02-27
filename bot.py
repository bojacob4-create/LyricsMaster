import os
import logging
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
application = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    try:
        user = update.effective_user
        logger.info(f"Start command received from user {user.id}")
        await update.message.reply_text(f'👋 Hi {user.first_name}! I am your music bot!')
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}", exc_info=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    try:
        logger.info(f"Help command received from user {update.effective_user.id}")
        await update.message.reply_text('Send /start to test the bot!')
    except Exception as e:
        logger.error(f"Error in help command: {str(e)}", exc_info=True)

@app.route('/')
def index():
    return 'Bot is running!'

@app.route('/webhook', methods=['POST'])
async def webhook():
    """Handle incoming webhook updates."""
    try:
        if application:
            await application.update_queue.put(Update.de_json(request.get_json(), application.bot))
        return 'OK'
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return 'Error processing webhook', 500

async def setup():
    """Set up the application with handlers."""
    global application

    # Get token from environment
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN not found")
        return

    try:
        # Create application
        application = Application.builder().token(token).build()

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))

        # Set webhook
        domain = f"{os.environ.get('REPL_SLUG')}.{os.environ.get('REPL_OWNER')}.repl.co"
        webhook_url = f"https://{domain}/webhook"

        # Delete webhook before setting it
        await application.bot.delete_webhook()

        # Set new webhook
        await application.bot.set_webhook(webhook_url)
        logger.info(f"Webhook set to: {webhook_url}")

        # Start application
        await application.initialize()
        logger.info("Bot initialized successfully")

        return True
    except Exception as e:
        logger.error(f"Error in setup: {str(e)}", exc_info=True)
        return False

def main():
    """Start the bot."""
    try:
        # Run setup
        import asyncio
        asyncio.run(setup())

        # Start Flask app
        app.run(host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Critical error: {str(e)}", exc_info=True)

if __name__ == '__main__':
    main()