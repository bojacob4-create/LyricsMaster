import os
import sys
import time
import logging
import signal
import subprocess
import psutil
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

# Constants
CHECK_INTERVAL = 1  # Check every second
MAX_RESTART_DELAY = 15  # Maximum delay between restarts
STARTUP_TIMEOUT = 30  # Maximum time to wait for bot to start

class BotMonitor:
    def __init__(self):
        self.process = None
        self.should_stop = False
        self.consecutive_failures = 0
        self.retry_delay = 2  # Initial delay of 2 seconds

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

    def handle_signal(self, signum, frame):
        """Handle termination signals."""
        logger.info(f"Received signal {signal.Signals(signum).name}")
        self.cleanup()

    def cleanup(self):
        """Clean up processes before exit."""
        logger.info("Cleaning up processes...")
        self.should_stop = True
        if self.process:
            self.kill_process_tree(self.process.pid)
        sys.exit(0)

    def kill_process_tree(self, pid):
        """Kill a process and all its children."""
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            parent.kill()
            parent.wait(5)
            logger.info(f"Successfully terminated process tree for PID {pid}")
        except Exception as e:
            logger.error(f"Error killing process tree: {str(e)}")

    def verify_token(self):
        """Verify Telegram token exists."""
        if not os.environ.get("TELEGRAM_TOKEN"):
            logger.critical("TELEGRAM_TOKEN not found in environment!")
            return False
        return True

    def check_process_health(self, pid):
        """Check if process is healthy."""
        try:
            process = psutil.Process(pid)
            if process.status() == psutil.STATUS_ZOMBIE:
                return False

            # Log resource usage
            memory_percent = process.memory_percent()
            cpu_percent = process.cpu_percent()
            logger.debug(f"Process Health - Memory: {memory_percent:.1f}%, CPU: {cpu_percent:.1f}%")

            return True
        except Exception:
            return False

    def monitor_startup(self):
        """Monitor bot process during startup."""
        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < STARTUP_TIMEOUT:
            if self.process.poll() is not None:
                return False

            line = self.process.stdout.readline() if self.process.stdout else None
            if line:
                line = line.strip()
                if line:
                    logger.info(f"Bot output: {line}")
                    if "Bot started successfully" in line:
                        return True

            line = self.process.stderr.readline() if self.process.stderr else None
            if line and line.strip():
                logger.error(f"Bot error: {line.strip()}")

            time.sleep(0.1)

        logger.error("Bot startup timed out")
        return False

    def run(self):
        """Main monitoring loop."""
        if not self.verify_token():
            sys.exit(1)

        while not self.should_stop:
            try:
                # Start the bot process
                logger.info("Starting bot process...")
                self.process = subprocess.Popen(
                    [sys.executable, 'bot.py'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    bufsize=1,
                    preexec_fn=os.setsid
                )

                # Wait for successful startup
                if not self.monitor_startup():
                    raise Exception("Bot failed to start properly")

                logger.info("Bot is running, monitoring...")
                
                # Monitor the running process
                while self.process.poll() is None and not self.should_stop:
                    if not self.check_process_health(self.process.pid):
                        raise Exception("Process health check failed")

                    # Check for output
                    while True:
                        line = self.process.stdout.readline() if self.process.stdout else None
                        error = self.process.stderr.readline() if self.process.stderr else None

                        if not line and not error:
                            break

                        if line and line.strip():
                            logger.info(f"Bot output: {line.strip()}")
                        if error and error.strip():
                            logger.error(f"Bot error: {error.strip()}")

                    time.sleep(CHECK_INTERVAL)

                # Process ended, check exit code
                exit_code = self.process.poll()
                if exit_code != 0:
                    logger.error(f"Bot process exited with code: {exit_code}")
                    self.consecutive_failures += 1
                else:
                    self.consecutive_failures = 0

            except Exception as e:
                logger.error(f"Monitor error: {str(e)}")
                self.consecutive_failures += 1

            # Handle failures
            if self.consecutive_failures > 0:
                self.retry_delay = min(2 ** self.consecutive_failures, MAX_RESTART_DELAY)
                logger.warning(f"Waiting {self.retry_delay}s before restart (failures: {self.consecutive_failures})")
                time.sleep(self.retry_delay)

            # Cleanup before restart
            if self.process and self.process.poll() is None:
                self.kill_process_tree(self.process.pid)
                time.sleep(1)

def main():
    try:
        logger.info("Starting bot monitor...")
        monitor = BotMonitor()
        monitor.run()
    except KeyboardInterrupt:
        logger.info("Shutting down monitor...")
        if hasattr(monitor, 'cleanup'):
            monitor.cleanup()
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
