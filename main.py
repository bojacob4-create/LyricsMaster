import os
import logging
import signal
import time
from telegram.ext import Updater

def main():
    """Entry point for the bot."""
    try:
        # Get token from environment
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            logging.error("TELEGRAM_TOKEN environment variable not set")
            return

        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Check if another bot process is already running
        lock_file = "/tmp/telegram_bot.lock"
        if os.path.exists(lock_file):
            try:
                with open(lock_file, 'r') as f:
                    pid = int(f.read().strip())
                # Try to kill the existing process
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(2)  # Give it time to terminate
                except OSError:
                    pass  # Process already gone
                # Remove stale lock file
                os.remove(lock_file)
            except (ValueError, OSError) as e:
                logging.error(f"Error handling existing lock file: {str(e)}")

        # Create lock file
        try:
            with open(lock_file, 'w') as f:
                f.write(str(os.getpid()))
        except OSError as e:
            logging.error(f"Error creating lock file: {str(e)}")
            return

        # Run the bot
        updater = Updater(
            token=token,
            use_context=True,
            request_kwargs={
                'read_timeout': 30,
                'connect_timeout': 30
            }
        )
        # ... rest of the bot logic (dispatcher, handlers etc.) ...

        updater.start_polling()
        updater.idle()

    except Exception as e:
        logging.exception(f"An error occurred: {str(e)}")
    finally:
        # Remove lock file on exit
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except OSError as e:
                logging.error(f"Error removing lock file: {str(e)}")


if __name__ == "__main__":
    main()