import os
import sys
import time
import logging
import signal
import subprocess
import psutil
from datetime import datetime, timedelta

# Configure logging with more detail
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
CHECK_INTERVAL = 2  # Check every 2 seconds
STARTUP_TIMEOUT = 10  # Wait up to 10 seconds for process to start
MAX_RESTART_DELAY = 10  # Maximum delay between restarts is 10 seconds

def force_kill_process(pid):
    """Force kill a process and all its children."""
    try:
        logger.info(f"Force killing process tree for PID {pid}")
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
        logger.info(f"Successfully killed process tree for PID {pid}")
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logger.error(f"Error killing process: {str(e)}")

def cleanup_processes():
    """Aggressively clean up all related Python processes."""
    logger.info("Performing aggressive process cleanup...")

    # Find and kill all related Python processes
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and len(cmdline) >= 2 and 'python' in cmdline[0]:
                if any(script in cmdline[1] for script in ['bot.py', 'run_bot.py']):
                    logger.info(f"Killing process: {proc.pid} ({cmdline})")
                    force_kill_process(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    time.sleep(2)  # Wait for processes to fully terminate

def verify_token():
    """Verify Telegram token exists."""
    if not os.environ.get("TELEGRAM_TOKEN"):
        logger.critical("TELEGRAM_TOKEN not found!")
        return False
    return True

def monitor_process_health(proc):
    """Check if a process is healthy."""
    try:
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
            return False

        # Check resource usage
        memory_percent = proc.memory_percent()
        cpu_percent = proc.cpu_percent()
        logger.debug(f"Process {proc.pid} health - Memory: {memory_percent:.1f}%, CPU: {cpu_percent:.1f}%")

        if memory_percent > 90:  # High memory usage threshold
            logger.warning(f"High memory usage detected: {memory_percent:.1f}%")
            return False

        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

def wait_for_process_start(name, timeout=STARTUP_TIMEOUT):
    """Wait for process to start and verify it's running."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['cmdline'] and len(proc.info['cmdline']) >= 2:
                    if 'python' in proc.info['cmdline'][0] and name in proc.info['cmdline'][1]:
                        if monitor_process_health(proc):
                            return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(0.1)
    return None

def run_supervisor():
    """Enhanced supervisor with aggressive monitoring."""
    if not verify_token():
        sys.exit(1)

    cleanup_processes()
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

            # Start the monitor process
            logger.info("Starting monitor process...")
            subprocess.Popen(
                [sys.executable, 'run_bot.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                preexec_fn=os.setsid
            )

            # Wait for monitor to start
            monitor_proc = wait_for_process_start('run_bot.py')
            if not monitor_proc:
                raise Exception("Monitor process failed to start")

            last_start_time = datetime.now()
            logger.info(f"Monitor started successfully (PID: {monitor_proc.pid})")
            consecutive_failures = 0

            # Monitor the process
            while True:
                time.sleep(CHECK_INTERVAL)

                # Verify monitor process
                if not monitor_proc.is_running():
                    raise Exception("Monitor process died")

                if not monitor_process_health(monitor_proc):
                    raise Exception("Monitor process unhealthy")

                # Verify bot process
                bot_proc = None
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        if proc.info['cmdline'] and len(proc.info['cmdline']) >= 2:
                            if 'python' in proc.info['cmdline'][0] and 'bot.py' in proc.info['cmdline'][1]:
                                bot_proc = proc
                                break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                if not bot_proc:
                    raise Exception("Bot process not found")

                if not monitor_process_health(bot_proc):
                    raise Exception("Bot process unhealthy")

        except KeyboardInterrupt:
            logger.info("Received shutdown signal, cleaning up...")
            cleanup_processes()
            sys.exit(0)

        except Exception as e:
            logger.error(f"Supervisor error: {str(e)}")
            cleanup_processes()

            consecutive_failures += 1
            if consecutive_failures >= 3:
                logger.warning("Multiple failures detected, performing full cleanup...")
                consecutive_failures = 0
                time.sleep(5)

            delay = min(CHECK_INTERVAL * (2 ** consecutive_failures), MAX_RESTART_DELAY)
            time.sleep(delay)

def main():
    try:
        # Set up signal handlers
        signal.signal(signal.SIGTERM, lambda signo, frame: cleanup_processes())
        signal.signal(signal.SIGINT, lambda signo, frame: cleanup_processes())

        logger.info("Starting enhanced supervisor...")
        run_supervisor()
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}")
        cleanup_processes()
        sys.exit(1)

if __name__ == "__main__":
    main()