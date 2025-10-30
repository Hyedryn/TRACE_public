"""Video parsing and watching functionality."""
import time
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import get_config

logger = logging.getLogger(__name__)

def parse_duration(duration_str):
    """
    Parses a duration string (e.g., "1:10:25" or "10:25") into total seconds.
    It correctly handles formats from H:M:S down to just S.
    """
    if not duration_str or not isinstance(duration_str, str):
        logger.error("Invalid duration string.")
        return 0

    parts = duration_str.split(':')
    duration = 0

    try:
        # Iterate over the parts in reverse (from seconds, to minutes, to hours).
        # The index 'i' will be 0 for seconds, 1 for minutes, 2 for hours, etc.
        # This correctly handles "10:25" (i=0 for '25', i=1 for '10') and
        # "1:10:25" (i=0 for '25', i=1 for '10', i=2 for '1').
        for i, part in enumerate(reversed(parts)):
            # The multiplier is 60^0 for seconds, 60^1 for minutes, 60^2 for hours.
            duration += int(part) * (60 ** i)
        return duration
    except ValueError:
        # This handles cases where a part is not a valid number, e.g., "LIVE".
        logger.warning(f"Warning: Could not parse malformed duration string: '{duration_str}'. Defaulting to 0.")
        return 0


def skip_ad(driver):
    """
    A non-blocking function to check for and click a skippable ad button.
    Returns True if an ad was skipped, False otherwise.
    """
    try:
        # Using a more specific selector for the modern button format
        skip_button = driver.find_element(By.CSS_SELECTOR, "button.ytp-skip-ad-button")
        if skip_button.is_displayed() and skip_button.is_enabled():
            skip_button.click()
            logger.info("Ad skipped.")
            return True
    except:
        # No skip button found, which is the normal case.
        pass
    return False


def watch_video(driver, duration_seconds=0, max_duration=None):
    """
    Actively "watches" a video for a specified duration, while periodically
    checking for and skipping mid-roll ads.
    """
    if max_duration is None:
        config = get_config()
        max_duration = config.scraping.max_duration
    
    logger.info(f"Attempting to watch video for up to {max_duration} seconds.")
    
    # Try to ensure the video is playing first
    try:
        player_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "movie_player"))
        )
        if 'paused-mode' in player_container.get_attribute('class'):
            logger.info("Video is paused. Clicking play button.")
            player_container.find_element(By.CSS_SELECTOR, ".ytp-play-button").click()
            time.sleep(1)
    except Exception as e:
        logger.error(f"Could not ensure video is playing: {e}")

    start_time = time.time()

    time.sleep(5) # Sleep to let the potential ad load

    skip_ad(driver)

    # Determine the actual duration to watch
    watch_duration = max_duration
    if duration_seconds > 0:
        watch_duration = min(duration_seconds, max_duration)
    else:
        try:
            video_player = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".html5-main-video"))
            )
            duration_str = video_player.get_attribute("duration")
            if duration_str:
                logger.info(f"Scrapped video duration: {duration_str}")
                watch_duration = min(float(duration_str), max_duration)
        except Exception as e:
            logger.error(f"Could not get video duration: {e}. Waiting for a fixed time.")

    
    elapsed_time = 0
    while elapsed_time < watch_duration:
        # Periodically check for and skip ads
        skip_ad(driver)
            
        # Wait for a short interval
        time.sleep(2)
        elapsed_time = time.time() - start_time

    logger.info(f"Finished watching video. Total time: {elapsed_time} seconds.")