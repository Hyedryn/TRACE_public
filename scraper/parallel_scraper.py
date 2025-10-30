"""Parallel scraper wrapper for running multiple concurrent sessions."""
import os
import sys
import logging
import multiprocessing
from pathlib import Path

# Import the main scraper
from scraper_main import main as scraper_main
from config import get_config, reload_config

logger = logging.getLogger(__name__)


def run_single_scraper(worker_id, config_path):
    """
    Run a single scraper instance in a separate process.

    Args:
        worker_id: Unique identifier for this worker (0-indexed)
        config_path: Path to the configuration file
    """
    # Set up logging for this worker
    log_format = f'%(asctime)s - Worker-{worker_id} - %(name)s - %(levelname)s - %(message)s'

    # Reload config in this process (each process gets its own config instance)
    os.environ['CONFIG_FILE'] = config_path
    config = reload_config()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.logging.level),
        format=log_format,
        force=True  # Force reconfiguration in this subprocess
    )

    logger.info(f"Starting scraper worker {worker_id}")

    try:
        # Run the main scraper function
        scraper_main()
        logger.info(f"Worker {worker_id} completed successfully")
    except Exception as e:
        logger.error(f"Worker {worker_id} failed with error: {e}", exc_info=True)
        sys.exit(1)


def main():
    """Main entry point for parallel scraper."""
    # Load configuration
    config = get_config()

    # Get concurrent_users from experiment config
    concurrent_users = getattr(config.experiment, 'concurrent_users', 1)

    if concurrent_users <= 0:
        concurrent_users = 1

    config_path = os.getenv('CONFIG_FILE')
    if not config_path:
        logger.error("CONFIG_FILE environment variable not set")
        sys.exit(1)

    # Set up logging for the main process
    logging.basicConfig(
        level=getattr(logging, config.logging.level),
        format='%(asctime)s - Main - %(name)s - %(levelname)s - %(message)s'
    )

    logger.info(f"Starting parallel scraper with {concurrent_users} concurrent user(s)")

    if concurrent_users == 1:
        # Single user mode - just run directly without multiprocessing overhead
        logger.info("Running in single-user mode")
        scraper_main()
    else:
        # Multi-user mode - spawn multiple processes
        logger.info(f"Spawning {concurrent_users} worker processes")

        # Create a list to hold process objects
        processes = []

        # Spawn worker processes
        for worker_id in range(concurrent_users):
            process = multiprocessing.Process(
                target=run_single_scraper,
                args=(worker_id, config_path),
                name=f"ScraperWorker-{worker_id}"
            )
            process.start()
            processes.append(process)
            logger.info(f"Started worker {worker_id} (PID: {process.pid})")

        # Wait for all processes to complete
        logger.info("Waiting for all workers to complete...")
        for worker_id, process in enumerate(processes):
            process.join()
            if process.exitcode == 0:
                logger.info(f"Worker {worker_id} completed successfully")
            else:
                logger.error(f"Worker {worker_id} failed with exit code {process.exitcode}")

        # Check if all processes completed successfully
        failed_workers = [i for i, p in enumerate(processes) if p.exitcode != 0]
        if failed_workers:
            logger.error(f"Some workers failed: {failed_workers}")
            sys.exit(1)
        else:
            logger.info("All workers completed successfully")


if __name__ == "__main__":
    main()
