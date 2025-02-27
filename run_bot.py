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

def get_process_info(name):
    """Get process info for the given script name."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and len(proc.info['cmdline']) >= 2:
                if 'python' in proc.info['cmdline'][0] and name in proc.info['cmdline'][1]:
                    return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def kill_process_tree(proc):
    """Kill a process and all its children."""
    if not proc:
        return

    logger.info(f"Terminating process tree for PID {proc.pid}")
    try:
        children = proc.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        proc.kill()
        proc.wait(5)
    except (psutil.NoSuchProcess, psutil.TimeoutExpired) as e:
        logger.error(f"Error killing process tree: {str(e)}")

def cleanup_bot():
    """Clean up any existing bot processes."""
    logger.info("Cleaning up existing bot processes...")
    proc = get_process_info('bot.py')
    if proc:
        kill_process_tree(proc)
        time.sleep(2)  # Wait for cleanup

def check_telegram_token():
    """Verify Telegram token is available."""
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.critical("TELEGRAM_TOKEN not found in environment!")
        return False
    return True

def monitor_bot():
    """Monitor and manage the bot process with enhanced error handling."""
    if not check_telegram_token():
        sys.exit(1)

    cleanup_bot()
    consecutive_failures = 0
    last_start_time = None

    while True:
        try:
            current_time = datetime.now()

            # Enforce minimum delay between restarts
            if last_start_time:
                elapsed = (current_time - last_start_time).total_seconds()
                if elapsed < CHECK_INTERVAL:
                    time.sleep(CHECK_INTERVAL - elapsed)

            logger.info("Starting bot process...")

            # Start the bot process
            process = subprocess.Popen(
                [sys.executable, 'bot.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                preexec_fn=os.setsid
            )

            last_start_time = datetime.now()
            logger.info(f"Bot process started with PID: {process.pid}")

            # Wait for bot to initialize
            start_wait = datetime.now()
            bot_ready = False

            while (datetime.now() - start_wait).total_seconds() < STARTUP_TIMEOUT:
                if process.poll() is not None:
                    raise Exception("Bot process terminated during startup")

                # Check process output for initialization
                output = process.stdout.readline() if process.stdout else None
                error = process.stderr.readline() if process.stderr else None

                if output and "Bot started successfully" in output:
                    bot_ready = True
                    break

                if error and error.strip():
                    logger.error(f"Bot error during startup: {error.strip()}")

                time.sleep(0.1)

            if not bot_ready:
                raise Exception("Bot failed to initialize within timeout")

            # Monitor the running bot
            while process.poll() is None:
                time.sleep(CHECK_INTERVAL)

                # Check process existence and health
                if not psutil.pid_exists(process.pid):
                    raise Exception("Bot process died unexpectedly")

                try:
                    proc = psutil.Process(process.pid)

                    # Check process state
                    if proc.status() == psutil.STATUS_ZOMBIE:
                        raise Exception("Bot process is in zombie state")

                    # Monitor resource usage
                    if int(time.time()) % 60 == 0:
                        memory_percent = proc.memory_percent()
                        cpu_percent = proc.cpu_percent()
                        logger.info(
                            f"Bot Status - "
                            f"Memory: {memory_percent:.1f}%, "
                            f"CPU: {cpu_percent:.1f}%, "
                            f"Status: {proc.status()}"
                        )

                except psutil.NoSuchProcess:
                    raise Exception("Bot process not found")

                # Check for process output
                while True:
                    output = process.stdout.readline() if process.stdout else None
                    error = process.stderr.readline() if process.stderr else None

                    if not output and not error:
                        break

                    if output and output.strip():
                        logger.info(f"Bot output: {output.strip()}")
                    if error and error.strip():
                        logger.error(f"Bot error: {error.strip()}")

            # If we get here, the process has ended
            exit_code = process.returncode
            logger.warning(f"Bot process ended with exit code: {exit_code}")

            if exit_code != 0:
                consecutive_failures += 1
                logger.warning(f"Consecutive failures: {consecutive_failures}")

                if consecutive_failures >= 3:
                    logger.warning("Multiple failures, performing full cleanup...")
                    cleanup_bot()
                    consecutive_failures = 0
                    time.sleep(5)
            else:
                consecutive_failures = 0

        except KeyboardInterrupt:
            logger.info("Received shutdown signal, cleaning up...")
            if 'process' in locals():
                kill_process_tree(psutil.Process(process.pid))
            sys.exit(0)

        except Exception as e:
            logger.error(f"Error in bot monitor: {str(e)}")
            consecutive_failures += 1

            if 'process' in locals():
                try:
                    output, error = process.communicate(timeout=5)
                    if output:
                        logger.error(f"Last output: {output}")
                    if error:
                        logger.error(f"Last error: {error}")
                except Exception:
                    pass
                kill_process_tree(psutil.Process(process.pid))

            time.sleep(min(CHECK_INTERVAL * (2 ** consecutive_failures), MAX_RESTART_DELAY))

def main():
    try:
        # Set up signal handlers
        signal.signal(signal.SIGTERM, lambda signo, frame: cleanup_bot())
        signal.signal(signal.SIGINT, lambda signo, frame: cleanup_bot())

        monitor_bot()
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}")
        cleanup_bot()
        sys.exit(1)

if __name__ == "__main__":
    main()