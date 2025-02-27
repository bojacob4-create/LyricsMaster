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
        logging.FileHandler('supervisor.log')
    ]
)
logger = logging.getLogger(__name__)

# Constants
CHECK_INTERVAL = 5  # Check every 5 seconds
MAX_RESTART_DELAY = 30  # Maximum delay between restarts

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

def cleanup_processes():
    """Clean up any existing bot and monitor processes."""
    logger.info("Cleaning up existing processes...")

    # Clean up bot.py processes
    bot_proc = get_process_info('bot.py')
    if bot_proc:
        kill_process_tree(bot_proc)

    # Clean up run_bot.py processes
    monitor_proc = get_process_info('run_bot.py')
    if monitor_proc:
        kill_process_tree(monitor_proc)

    # Wait for processes to fully terminate
    time.sleep(2)

def check_telegram_token():
    """Verify Telegram token is available."""
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.critical("TELEGRAM_TOKEN not found in environment!")
        return False
    return True

def run_supervisor():
    """Main supervisor loop with enhanced process management."""
    if not check_telegram_token():
        sys.exit(1)

    cleanup_processes()

    logger.info("Starting supervisor with enhanced monitoring...")
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

            # Check monitor process
            monitor_proc = get_process_info('run_bot.py')

            if not monitor_proc:
                logger.info("Monitor process not found, starting...")

                # Start fresh - ensure no lingering processes
                cleanup_processes()

                # Start the monitor process
                subprocess.Popen(
                    [sys.executable, 'run_bot.py'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    bufsize=1,
                    preexec_fn=os.setsid
                )

                last_start_time = datetime.now()
                logger.info("Started monitor process")
                time.sleep(2)  # Give process time to start

                # Verify monitor started successfully
                if not get_process_info('run_bot.py'):
                    raise Exception("Failed to start monitor process")

                consecutive_failures = 0
            else:
                # Check monitor health
                try:
                    monitor_status = monitor_proc.status()
                    if monitor_status == psutil.STATUS_ZOMBIE:
                        logger.error("Monitor process is zombie, restarting...")
                        kill_process_tree(monitor_proc)
                        continue

                    # Log status periodically
                    if int(time.time()) % 60 == 0:
                        memory_percent = monitor_proc.memory_percent()
                        cpu_percent = monitor_proc.cpu_percent()
                        logger.info(
                            f"Monitor Status - "
                            f"PID: {monitor_proc.pid}, "
                            f"Memory: {memory_percent:.1f}%, "
                            f"CPU: {cpu_percent:.1f}%, "
                            f"Status: {monitor_status}"
                        )

                    # Verify bot process is running
                    bot_proc = get_process_info('bot.py')
                    if not bot_proc:
                        logger.error("Bot process not found, restarting monitor...")
                        kill_process_tree(monitor_proc)
                        continue

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    logger.error("Lost access to monitor process, restarting...")
                    continue

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Received shutdown signal, cleaning up...")
            cleanup_processes()
            sys.exit(0)

        except Exception as e:
            logger.error(f"Supervisor error: {str(e)}")
            consecutive_failures += 1

            if consecutive_failures >= 3:
                logger.warning("Multiple failures, performing full cleanup...")
                cleanup_processes()
                consecutive_failures = 0
                time.sleep(5)

            time.sleep(min(CHECK_INTERVAL * (2 ** consecutive_failures), MAX_RESTART_DELAY))

def main():
    try:
        # Set up signal handlers
        signal.signal(signal.SIGTERM, lambda signo, frame: cleanup_processes())
        signal.signal(signal.SIGINT, lambda signo, frame: cleanup_processes())

        run_supervisor()
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}")
        cleanup_processes()
        sys.exit(1)

if __name__ == "__main__":
    main()