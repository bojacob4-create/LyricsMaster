import os
import sys
import time
import logging
import signal
import subprocess
import psutil

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

# Globals
should_stop = False

def handle_signal(signum, frame):
    """Handle termination signals."""
    global should_stop
    sig_name = signal.Signals(signum).name
    logger.info(f"Received signal {sig_name}")
    should_stop = True

def get_monitor_process():
    """Get the run_bot.py monitor process if it's running."""
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and len(cmdline) >= 2 and 'python' in cmdline[0] and 'run_bot.py' in cmdline[1]:
                    logger.debug(f"Found monitor process: PID={proc.pid}")
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        logger.error(f"Error getting monitor process: {str(e)}")
    return None

def kill_process_tree(pid):
    """Kill a process and all its children."""
    try:
        logger.info(f"Killing process tree for PID {pid}")
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
        logger.info(f"Successfully killed process tree for PID {pid}")
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        logger.error(f"Error killing process tree: {str(e)}")

def run_supervisor():
    """Main supervisor loop to ensure monitor is running."""
    global should_stop

    # Set up signal handlers
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    while not should_stop:
        try:
            # Check if monitor is running
            monitor_proc = get_monitor_process()

            if not monitor_proc:
                logger.info("Monitor process not found, starting...")
                # Start the monitor
                subprocess.Popen(
                    [sys.executable, 'run_bot.py'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    bufsize=1,
                    preexec_fn=os.setsid  # Create new process group
                )
                logger.info("Started monitor process")
                time.sleep(2)  # Give process time to start
            else:
                # Check if monitor is responding
                try:
                    status = monitor_proc.status()
                    if status == psutil.STATUS_ZOMBIE:
                        logger.warning("Monitor process is zombie, restarting...")
                        kill_process_tree(monitor_proc.pid)
                        continue

                    # Log monitor status every minute
                    if int(time.time()) % 60 == 0:
                        memory_percent = monitor_proc.memory_percent()
                        cpu_percent = monitor_proc.cpu_percent()
                        logger.info(
                            f"Monitor Status - "
                            f"PID: {monitor_proc.pid}, "
                            f"Memory: {memory_percent:.1f}%, "
                            f"CPU: {cpu_percent:.1f}%, "
                            f"Status: {status}"
                        )

                except psutil.NoSuchProcess:
                    logger.warning("Monitor process died, will restart")
                    continue
                except Exception as e:
                    logger.error(f"Error checking monitor: {str(e)}")
                    # Kill the process if we can't check its status
                    kill_process_tree(monitor_proc.pid)
                    continue

            # Check every second
            time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Received shutdown signal, stopping supervisor...")
            if monitor_proc:
                kill_process_tree(monitor_proc.pid)
            sys.exit(0)

        except Exception as e:
            logger.error(f"Supervisor error: {str(e)}")
            time.sleep(5)  # Wait before retry
            continue

def main():
    try:
        logger.info("Starting supervisor...")
        run_supervisor()
    except KeyboardInterrupt:
        logger.info("Shutting down supervisor...")
        monitor_proc = get_monitor_process()
        if monitor_proc:
            kill_process_tree(monitor_proc.pid)
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()