import os
import sys
import time
import subprocess
import logging
import signal
import psutil
from datetime import datetime, timedelta
from threading import Thread, Event

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

HEALTH_CHECK_INTERVAL = 1  # Check every second
MAX_CONSECUTIVE_FAILURES = 3
INITIAL_RETRY_DELAY = 2  # seconds
MAX_RETRY_DELAY = 30  # 30 seconds max delay
WATCHDOG_TIMEOUT = 60  # 1 minute watchdog timeout

class BotMonitor:
    def __init__(self):
        self.process = None
        self.watchdog_event = Event()
        self.should_stop = False
        self.consecutive_failures = 0
        self.retry_delay = INITIAL_RETRY_DELAY
        self.last_start_time = None

    def get_bot_process(self):
        """Get the bot process if it's running."""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and len(cmdline) >= 2 and 'python' in cmdline[0] and 'bot.py' in cmdline[1]:
                        return proc
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            logger.error(f"Error getting bot process: {str(e)}")
        return None

    def kill_existing_bot(self):
        """Kill any existing bot process."""
        try:
            proc = self.get_bot_process()
            if proc:
                logger.info(f"Found existing bot process (PID: {proc.pid}), terminating...")
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        logger.warning("Process didn't terminate, forcing kill...")
                        proc.kill()
                        proc.wait(timeout=5)
                except psutil.NoSuchProcess:
                    pass
                except Exception as e:
                    logger.error(f"Error killing process: {str(e)}")
                    if proc.is_running():
                        os.kill(proc.pid, signal.SIGKILL)
                logger.info("Existing bot process terminated")
                time.sleep(1)  # Wait for cleanup
        except Exception as e:
            logger.error(f"Error in kill_existing_bot: {str(e)}")

    def watchdog_timer(self):
        """Watchdog timer thread to monitor bot responsiveness."""
        while not self.should_stop:
            if not self.watchdog_event.wait(WATCHDOG_TIMEOUT):
                logger.error("Watchdog timeout - Bot appears to be unresponsive")
                self.restart_bot()
            self.watchdog_event.clear()

    def restart_bot(self):
        """Restart the bot process."""
        logger.info("Initiating bot restart...")
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                if self.process.poll() is None:
                    self.process.kill()
        self.start_bot()

    def monitor_process(self):
        """Monitor the bot process health."""
        while self.process.poll() is None and not self.should_stop:
            try:
                time.sleep(HEALTH_CHECK_INTERVAL)

                # Reset watchdog timer
                self.watchdog_event.set()

                if not psutil.pid_exists(self.process.pid):
                    raise Exception("Bot process died unexpectedly")

                try:
                    proc = psutil.Process(self.process.pid)
                    if proc.status() == psutil.STATUS_ZOMBIE:
                        raise Exception("Bot process is in zombie state")

                    # Monitor resource usage
                    if int(time.time()) % 60 == 0:  # Log every minute
                        memory_info = proc.memory_info()
                        cpu_percent = proc.cpu_percent()
                        logger.info(
                            f"Process Status - "
                            f"Memory: {memory_info.rss / 1024 / 1024:.2f}MB, "
                            f"CPU: {cpu_percent}%, "
                            f"Status: {proc.status()}"
                        )

                except psutil.NoSuchProcess:
                    raise Exception("Bot process not found")

                # Check for process output
                self.check_process_output()

            except Exception as e:
                logger.error(f"Process monitoring error: {str(e)}")
                return False

        return True

    def check_process_output(self):
        """Check and log process output."""
        if self.process.stdout:
            while True:
                line = self.process.stdout.readline()
                if not line:
                    break
                if line.strip():
                    logger.info(f"Bot output: {line.strip()}")

        if self.process.stderr:
            while True:
                line = self.process.stderr.readline()
                if not line:
                    break
                if line.strip():
                    logger.error(f"Bot error: {line.strip()}")

    def start_bot(self):
        """Start the bot process."""
        current_time = datetime.now()

        if self.last_start_time and (current_time - self.last_start_time) < timedelta(seconds=self.retry_delay):
            sleep_time = (self.last_start_time + timedelta(seconds=self.retry_delay) - current_time).total_seconds()
            if sleep_time > 0:
                logger.info(f"Waiting {sleep_time:.1f} seconds before next restart attempt...")
                time.sleep(sleep_time)

        logger.info("Starting bot process...")
        self.last_start_time = datetime.now()

        self.process = subprocess.Popen(
            [sys.executable, 'bot.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        logger.info(f"Bot process started with PID: {self.process.pid}")
        return self.monitor_process()

    def run(self):
        """Main monitoring loop."""
        # Start watchdog timer
        watchdog_thread = Thread(target=self.watchdog_timer, daemon=True)
        watchdog_thread.start()

        while not self.should_stop:
            try:
                self.kill_existing_bot()

                if not self.start_bot():
                    self.consecutive_failures += 1
                    self.retry_delay = min(INITIAL_RETRY_DELAY * (2 ** self.consecutive_failures), MAX_RETRY_DELAY)
                    logger.warning(f"Consecutive failures: {self.consecutive_failures}, next retry delay: {self.retry_delay}s")

                    if self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        logger.warning("Multiple failures detected, resetting retry counter...")
                        self.consecutive_failures = 0
                        self.retry_delay = INITIAL_RETRY_DELAY
                        time.sleep(5)  # Brief pause before clean restart
                else:
                    self.consecutive_failures = 0
                    self.retry_delay = INITIAL_RETRY_DELAY

            except KeyboardInterrupt:
                logger.info("Received shutdown signal, stopping monitor...")
                self.should_stop = True
                if self.process:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                self.kill_existing_bot()
                break

            except Exception as e:
                logger.error(f"Error in bot monitor: {str(e)}")
                if self.process:
                    try:
                        output, error = self.process.communicate(timeout=5)
                        if output:
                            logger.error(f"STDOUT: {output}")
                        if error:
                            logger.error(f"STDERR: {error}")
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                time.sleep(self.retry_delay)
                continue

def main():
    try:
        logger.info("Bot monitor starting...")
        monitor = BotMonitor()
        monitor.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal, stopping monitor...")
        monitor.should_stop = True
        monitor.kill_existing_bot()
        sys.exit(0)

if __name__ == "__main__":
    main()