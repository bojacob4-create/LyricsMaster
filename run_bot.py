import os
import sys
import time
import subprocess
import logging
import signal
import psutil
from datetime import datetime, timedelta
from threading import Thread, Event

# Configure logging with more detail
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

# Constants for monitoring
HEALTH_CHECK_INTERVAL = 1  # Check every second
MAX_CONSECUTIVE_FAILURES = 3
INITIAL_RETRY_DELAY = 2  # seconds
MAX_RETRY_DELAY = 15  # 15 seconds max delay
WATCHDOG_TIMEOUT = 15  # 15 seconds watchdog timeout

class BotMonitor:
    def __init__(self):
        self.process = None
        self.watchdog_event = Event()
        self.should_stop = False
        self.consecutive_failures = 0
        self.retry_delay = INITIAL_RETRY_DELAY
        self.last_start_time = None
        self.last_activity_time = datetime.now()

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

    def handle_signal(self, signum, frame):
        """Handle termination signals."""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received signal {sig_name}")
        self.cleanup_and_exit()

    def cleanup_and_exit(self):
        """Clean up processes and exit."""
        logger.info("Cleaning up before exit...")
        self.should_stop = True
        if self.process:
            try:
                logger.info("Terminating bot process...")
                self.force_kill_process(psutil.Process(self.process.pid))
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}")
        sys.exit(0)

    def force_kill_process(self, proc):
        """Force kill a process and its children."""
        try:
            logger.info(f"Force killing process {proc.pid} and its children...")
            parent = psutil.Process(proc.pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            parent.kill()
            logger.info(f"Successfully killed process {proc.pid}")
        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            logger.error(f"Error in force kill: {str(e)}")

    def get_bot_process(self):
        """Get the bot process if it's running."""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and len(cmdline) >= 2 and 'python' in cmdline[0] and 'bot.py' in cmdline[1]:
                        logger.debug(f"Found bot process: PID={proc.pid}")
                        return proc
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            logger.error(f"Error getting bot process: {str(e)}")
        return None

    def kill_existing_bot(self):
        """Kill any existing bot process with force."""
        try:
            proc = self.get_bot_process()
            if proc:
                logger.info(f"Found existing bot process (PID: {proc.pid}), terminating...")
                try:
                    # Try graceful shutdown first
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        logger.warning("Process didn't terminate, forcing kill...")
                        self.force_kill_process(proc)
                except Exception as e:
                    logger.error(f"Error in process termination: {str(e)}")
                    self.force_kill_process(proc)
                logger.info("Existing bot process terminated")
                time.sleep(2)  # Wait for cleanup
        except Exception as e:
            logger.error(f"Error in kill_existing_bot: {str(e)}")

    def check_process_health(self, proc):
        """Check if process is healthy."""
        try:
            status = proc.status()
            if status == psutil.STATUS_ZOMBIE:
                logger.error("Process is in zombie state")
                return False

            memory_percent = proc.memory_percent()
            cpu_percent = proc.cpu_percent()
            logger.debug(f"Process Health - Memory: {memory_percent:.1f}%, CPU: {cpu_percent:.1f}%, Status: {status}")

            if memory_percent > 90:  # High memory usage
                logger.warning(f"High memory usage detected: {memory_percent:.1f}%")
                return False

            return True
        except Exception as e:
            logger.error(f"Health check error: {str(e)}")
            return False

    def check_process_output(self):
        """Non-blocking check of process output."""
        if not self.process:
            return

        try:
            if self.process.stdout:
                line = self.process.stdout.readline()
                if line and line.strip():
                    logger.info(f"Bot output: {line.strip()}")
                    self.last_activity_time = datetime.now()

            if self.process.stderr:
                line = self.process.stderr.readline()
                if line and line.strip():
                    logger.error(f"Bot error: {line.strip()}")
                    self.last_activity_time = datetime.now()
        except Exception as e:
            logger.error(f"Error checking process output: {str(e)}")

    def watchdog_timer(self):
        """Enhanced watchdog timer with health checks."""
        while not self.should_stop:
            try:
                if not self.watchdog_event.wait(WATCHDOG_TIMEOUT):
                    logger.error("Watchdog timeout - Bot appears to be unresponsive")
                    if self.process and self.process.poll() is None:
                        try:
                            proc = psutil.Process(self.process.pid)
                            if not self.check_process_health(proc):
                                logger.error("Process health check failed, forcing restart...")
                                self.force_kill_process(proc)
                        except Exception as e:
                            logger.error(f"Error in watchdog health check: {str(e)}")
                    self.restart_bot()
                self.watchdog_event.clear()
            except Exception as e:
                logger.error(f"Error in watchdog: {str(e)}")

    def restart_bot(self):
        """Force restart the bot process."""
        logger.info("Force restarting bot...")
        if self.process:
            try:
                self.force_kill_process(psutil.Process(self.process.pid))
            except Exception as e:
                logger.error(f"Error during force restart: {str(e)}")
        self.start_bot()

    def start_bot(self):
        """Start the bot process with enhanced monitoring."""
        try:
            # Enforce minimum delay between restarts
            current_time = datetime.now()
            if self.last_start_time:
                elapsed = (current_time - self.last_start_time).total_seconds()
                if elapsed < self.retry_delay:
                    wait_time = self.retry_delay - elapsed
                    logger.info(f"Waiting {wait_time:.1f} seconds before restart...")
                    time.sleep(wait_time)

            # Kill any existing process before starting
            self.kill_existing_bot()

            logger.info("Starting bot process...")
            self.process = subprocess.Popen(
                [sys.executable, 'bot.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                preexec_fn=os.setsid  # Create new process group
            )

            self.last_start_time = datetime.now()
            self.last_activity_time = datetime.now()
            logger.info(f"Bot process started with PID: {self.process.pid}")

            # Monitor the process
            while self.process.poll() is None and not self.should_stop:
                time.sleep(HEALTH_CHECK_INTERVAL)
                self.watchdog_event.set()

                if not psutil.pid_exists(self.process.pid):
                    raise Exception("Bot process died unexpectedly")

                try:
                    proc = psutil.Process(self.process.pid)
                    if not self.check_process_health(proc):
                        raise Exception("Process health check failed")
                except psutil.NoSuchProcess:
                    raise Exception("Bot process not found")

                self.check_process_output()

            return True

        except Exception as e:
            logger.error(f"Error in bot process: {str(e)}")
            return False

    def run(self):
        """Main monitoring loop with enhanced error handling."""
        logger.info("Starting enhanced bot monitor...")

        # Start watchdog timer
        watchdog_thread = Thread(target=self.watchdog_timer, daemon=True)
        watchdog_thread.start()

        while not self.should_stop:
            try:
                if not self.start_bot():
                    self.consecutive_failures += 1
                    self.retry_delay = min(INITIAL_RETRY_DELAY * (2 ** self.consecutive_failures), MAX_RETRY_DELAY)
                    logger.warning(f"Consecutive failures: {self.consecutive_failures}, next retry delay: {self.retry_delay}s")

                    if self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        logger.warning("Multiple failures detected, resetting retry counter...")
                        self.consecutive_failures = 0
                        self.retry_delay = INITIAL_RETRY_DELAY
                        time.sleep(3)  # Brief pause before clean restart
                else:
                    self.consecutive_failures = 0
                    self.retry_delay = INITIAL_RETRY_DELAY

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt...")
                self.cleanup_and_exit()
            except Exception as e:
                logger.error(f"Critical error in monitor: {str(e)}")
                time.sleep(self.retry_delay)

def main():
    try:
        monitor = BotMonitor()
        monitor.run()
    except KeyboardInterrupt:
        logger.info("Shutting down monitor...")
        monitor.cleanup_and_exit()
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()