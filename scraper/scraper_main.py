"""Main YouTube scraper orchestration."""
import time
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import random

# Import our modules
from config import get_config, ExperimentConfig
from database import *
from browser_manager import setup_browser, accept_cookies, scroll_to_load_recommendations, get_recommendations_html
from video_parser import watch_video, parse_duration
from recommendation_parser import parse_recommendations
from llm_services import choose_video_with_llm, check_video_relevance_with_llm, validate_provider


logger = logging.getLogger(__name__)


def get_llm_configs():
    """Gets the LLM configurations for all tasks."""
    config = get_config()
    
    # Validate providers first
    validate_provider(config.llm.parse_recommendations.provider)
    validate_provider(config.llm.choose_video.provider)
    validate_provider(config.llm.check_relevance.provider)
    
    return {
        'parse_recommendations': config.llm.parse_recommendations,
        'choose_video': config.llm.choose_video,
        'check_relevance': config.llm.check_relevance
    }


def check_video_relevance(driver, persona_description):
    """Checks if the video transcript is relevant to the persona."""

    def parse_timestamp_to_seconds(timestamp_str):
        """
        Converts a timestamp string in 'MM:SS' or 'H:MM:SS' format to total seconds.
        Returns -1 if parsing fails due to invalid format.
        """
        parts = timestamp_str.split(':')
        total_seconds = 0
        try:
            if len(parts) == 2:  # MM:SS format
                minutes = int(parts[0])
                seconds = int(parts[1])
                total_seconds = minutes * 60 + seconds
            elif len(parts) == 3:  # H:MM:SS format
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                total_seconds = hours * 3600 + minutes * 60 + seconds
            else:
                return -1 # Unrecognized format
        except ValueError:
            return -1 # Error converting parts to integers (e.g., non-digit characters)
        return total_seconds

    def trim_transcript(html_content, transcript_seconds):
        """
        Extracts the transcript text for the first <transcript_seconds> seconds from YouTube transcript HTML.

        Args:
            html_content (str): The HTML content of the YouTube transcript.

        Returns:
            str: The concatenated transcript text for the first <transcript_seconds> seconds,
                or an empty string if no segments are found or all are beyond <transcript_seconds> seconds.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        segments = soup.find_all('ytd-transcript-segment-renderer')

        extracted_text = []

        for segment in segments:
            timestamp_element = segment.find('div', class_='segment-timestamp')
            text_element = segment.find('yt-formatted-string', class_='segment-text')

            if timestamp_element and text_element:
                time_str = timestamp_element.text.strip()
                text = text_element.text.strip()

                current_seconds = parse_timestamp_to_seconds(time_str)

                if current_seconds != -1 and current_seconds < transcript_seconds:
                    extracted_text.append(f"[{time_str}] " + text)
                elif current_seconds >= transcript_seconds:
                    # Stop when we encounter a segment starting at or after <transcript_seconds> seconds
                    break
            # Segments without a valid timestamp or text element will be skipped.

        return f" \n".join(extracted_text)

    try:
        # Click the button to expand the description
        expand_description_button = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, "//ytd-text-inline-expander[@id='description-inline-expander']//tp-yt-paper-button[@id='expand']"))
        )
        if expand_description_button.get_attribute("hidden") is None:
            expand_description_button.click()

        # Click the button to show the transcript
        show_transcript_button = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, "//ytd-watch-metadata//ytd-video-description-transcript-section-renderer//div[@id='button-container']//div[@id='primary-button']//button"))
        )
        show_transcript_button.click()
        time.sleep(2)

        # Get the transcript text
        transcript_element = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//*[@id='content']/ytd-transcript-renderer"))
        )
        
        # Use LLM to check relevance
        config = get_config()
        relevance_config = config.llm.check_relevance

        # Trim transcript
        try:
            transcript_text_trimmed = trim_transcript(transcript_element.get_attribute('innerHTML'), config.scraping.persona_filter_transcript_seconds+10)
            logger.debug(f"transcript_text_trimmed: {transcript_text_trimmed}")
        except Exception as e:
            logger.error(f"Could not trim transcript, fallback to full transcript: {e}")
            transcript_text_trimmed = transcript_element.text

        transcript_text = transcript_element.text
        logger.debug(f"transcript_text: {transcript_text}")
        
        logger.info(f"Checking video relevance with transcript of char size {len(transcript_text_trimmed)}")
        result = check_video_relevance_with_llm(
            provider=relevance_config.provider,
            model=relevance_config.model,
            persona_description=persona_description,
            transcript_text=transcript_text_trimmed,
            transcript_seconds=config.scraping.persona_filter_transcript_seconds
        )
        logger.debug(f"[check_video_relevance] result: {result}")
        # Convert Pydantic model to dict for backward compatibility with existing code
        result_dict = result.model_dump()
        result_dict["video_transcript"] = transcript_text_trimmed
        return result_dict

    except Exception as e:
        logger.error(f"Could not check video relevance: {e}")
        return {"is_relevant": True, "justification": "Error during relevance check."}


def run_context_phase(driver, session_id, video_context_ids):
    """Runs the context-setting phase of the scraper."""
    logger.info("--- Starting Context-Setting Phase ---")
    source_video_id = None
    video_duration = 0
    
    for depth, context_video_id in enumerate(video_context_ids):
        logger.info(f"Context step {depth + 1}/{len(video_context_ids)}: Watching {context_video_id}")
        driver.get(f"https://www.youtube.com/watch?v={context_video_id}")

        # Get video duration from database
        video_duration = get_video_duration(context_video_id)
        watch_video(driver, duration_seconds=video_duration)

        scroll_to_load_recommendations(driver)
        recommendations_html_list = get_recommendations_html(driver)
        parsed_recs = parse_recommendations(recommendations_html_list)

        # Mark context recommendations
        for rec in parsed_recs.recommendations:
            rec.recommendation_source = "context"

        # The video just watched is the source for the recommendations
        source_video_id = context_video_id

        insert_video_and_recommendations(
            session_id, depth, source_video_id, 
            parsed_recs, None, None, is_context=True
        )
    
    return source_video_id, video_duration

def get_next_choice_context(experiment_config: ExperimentConfig, current_step: int) -> tuple[str, int | None]:
    """
    Determines the choice method and profile ID for the current step of the experiment.

    Args:
        experiment_config: The experiment configuration object.
        current_step: The current step number in the persona phase (starting from 0).

    Returns:
        A tuple containing the choice_method ('persona' or 'random') and the profile_id to use (or None).
    """
    mode = experiment_config.mode

    if mode == 'single_persona':
        return 'persona', experiment_config.profile_id

    if mode == 'random_choice':
        return 'random', None

    if mode == 'mixed_persona':
        # Ensure there's a mix defined
        if not experiment_config.persona_mix:
            logger.error("Mixed persona mode selected but no persona_mix is defined in config.")
            return 'random', None  # Fallback to random

        profiles = [p.profile_id for p in experiment_config.persona_mix]
        weights = [p.weight for p in experiment_config.persona_mix]
        chosen_profile = random.choices(profiles, weights=weights, k=1)[0]
        return 'persona', chosen_profile

    if mode == 'sequential_persona':
        # Ensure there's a sequence defined
        if not experiment_config.persona_sequence:
            logger.error("Sequential persona mode selected but no persona_sequence is defined in config.")
            return 'random', None  # Fallback to random

        steps_so_far = 0
        for seq in experiment_config.persona_sequence:
            steps_so_far += seq.steps
            if current_step < steps_so_far:
                return 'persona', seq.profile_id

        # If the sequence is finished, default to random choice for the remainder of the run
        logger.warning(f"Persona sequence finished at step {steps_so_far}. Defaulting to random choice.")
        return 'random', None

    # Fallback for any unknown mode
    return 'random', None


def run_persona_phase(driver, session_id, personas: dict,
                     start_video_id, start_duration, context_length):
    """Runs the persona-driven navigation phase of the scraper."""
    logger.info("--- Starting Persona-Driven Navigation Phase ---")
    config = get_config()
    next_video_id = start_video_id
    next_video_duration = start_duration

    max_depth = config.scraping.max_depth
    for depth in range(context_length, context_length + max_depth):
        logger.info(f"Persona step {depth - context_length + 1}/{max_depth}: Journeying from {next_video_id}")
        source_video_id = next_video_id

        # --- DYNAMIC CHOICE CONTEXT ---
        # Determine choice method and persona for this specific step
        current_step = depth - context_length
        choice_method, profile_id_for_choice = get_next_choice_context(config.experiment, current_step)
        persona_description = personas.get(profile_id_for_choice)
        logger.info(
            f"Step {current_step}: Using choice method '{choice_method}' with profile ID: {profile_id_for_choice}")

        # --- NAVIGATION AND VIDEO WATCHING ---
        driver.get(f"https://www.youtube.com/watch?v={next_video_id}")

        if config.scraping.persona_filter_enabled:
            relevance_result = check_video_relevance(driver, persona_description)
            is_relevant = relevance_result.get("is_relevant", True)
            justification = relevance_result.get("justification", "")
            video_transcript = relevance_result.get("video_transcript", "")

            log_persona_filter(session_id, next_video_id, not is_relevant, justification, video_transcript)

            if not is_relevant:
                logger.info(f"Video {next_video_id} is not relevant to the persona. Watching for a maximum of {config.scraping.persona_filter_seconds} seconds.")
                watch_video(driver, min(next_video_duration, config.scraping.persona_filter_seconds))
            else:
                watch_video(driver, next_video_duration)
        else:
            watch_video(driver, next_video_duration)

        # --- RECOMMENDATION PARSING ---
        scroll_to_load_recommendations(driver)
        recommendations_html_list = get_recommendations_html(driver)
        parsed_recs = parse_recommendations(recommendations_html_list)

        # Mark sidebar recommendations
        for rec in parsed_recs.recommendations:
            rec.recommendation_source = "sidebar"

        # --- VIDEO SELECTION LOGIC ---
        chosen_video_id = None
        justification = ""

        if choice_method == 'random':
            if parsed_recs.recommendations:
                chosen_video_rec = random.choice(parsed_recs.recommendations)
                chosen_video_id = chosen_video_rec.video_id
                justification = "Random choice for baseline."
            else:
                logger.warning("No recommendations found to make a random choice. Ending phase.")
                break
        elif choice_method == 'persona' and persona_description:
            choice_config = config.llm.choose_video
            chosen_video = choose_video_with_llm(
                provider=choice_config.provider,
                model=choice_config.model,
                persona_description=persona_description,
                recommendations=parsed_recs
            )
            chosen_video_id = chosen_video.video_id
            justification = chosen_video.justification
        else:
            logger.error(f"Invalid state: choice_method='{choice_method}' with no valid persona. Ending phase.")
            break

        # Handle case where LLM or logic decides no video is interesting
        if chosen_video_id == "no_interesting_video":
            logger.info("LLM choose \"no_interesting_video\" as video id, moving to Youtube home page.")
            driver.get("https://www.youtube.com/")
            time.sleep(5)
            homepage_html_list = get_recommendations_html(driver)
            parsed_recs_homepage = parse_recommendations(homepage_html_list)

            # Combine recommendations for logging and selection
            for rec in parsed_recs_homepage.recommendations:
                rec.recommendation_source = "homepage"

            parsed_recs.recommendations.extend(parsed_recs_homepage.recommendations)

            # --- CORRECTED LOGIC ---
            if choice_method == 'random':
                if parsed_recs_homepage.recommendations:
                    chosen_video_rec = random.choice(parsed_recs_homepage.recommendations)
                    chosen_video_id = chosen_video_rec.video_id
                    justification = "Random choice from homepage for baseline."
                else:
                    logger.warning("No recommendations on homepage either. Ending experiment.")
                    break
            else:  # 'persona'
                chosen_video = choose_video_with_llm(
                    provider=config.llm.choose_video.provider,
                    model=config.llm.choose_video.model,
                    persona_description=persona_description,
                    recommendations=parsed_recs_homepage  # Choose only from homepage recs
                )
                chosen_video_id = chosen_video.video_id
                justification = chosen_video.justification

                if chosen_video_id == "no_interesting_video":
                    logger.info("Ending experiment: no interesting video found on sidebar or homepage.")
                    break


        # --- UPDATE FOR NEXT LOOP ---
        next_video_found = False
        for rec in parsed_recs.recommendations:
            if rec.video_id == chosen_video_id:
                next_video_id = rec.video_id
                next_video_duration = parse_duration(rec.duration)
                next_video_found = True
                break
        
        # If not found in sidebar recommendations, it might be from homepage
        if not next_video_found and 'parsed_recs_homepage' in locals():
            for rec in parsed_recs_homepage.recommendations:
                if rec.video_id == chosen_video_id:
                    next_video_id = rec.video_id
                    next_video_duration = parse_duration(rec.duration)
                    break

        # --- LOGGING RESULTS ---
        insert_video_and_recommendations(
            session_id=session_id,
            depth=depth,
            source_video_id=source_video_id,
            parsed_recs=parsed_recs,
            chosen_video_id=chosen_video_id,
            justification=justification,
            is_context=False,
            profile_id_at_choice=profile_id_for_choice,
            choice_method=choice_method
        )


def main():
    """Main scraper function."""
    # A. Load configuration and set up logging
    config = get_config()
    logging.basicConfig(level=getattr(logging, config.logging.level),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    selenium_level = getattr(logging, config.logging.selenium_level, 'WARNING')
    for logger_name in ['selenium.webdriver.remote.remote_connection', 'urllib3.connectionpool']:
        logging.getLogger(logger_name).setLevel(selenium_level)

    logger.info("--- Starting Scraper Bot ---")
    driver, session_id = None, None

    try:
        # B. Set up the experiment based on the config file
        exp_config = config.experiment

        # C. Get context videos using the new hybrid logic
        video_context_ids = []
        if exp_config.context_name:
            logger.info(f"Fetching context videos for: '{exp_config.context_name}'")
            video_context_ids = get_context_videos_by_name(exp_config.context_name)
        elif exp_config.context_video_ids:
            logger.info("Using context videos directly from config.")
            video_context_ids = exp_config.context_video_ids
        else:
            logger.info("No context phase configured.")

        # D. Fetch all required persona descriptions for the experiment phase
        profile_ids_to_fetch = set()
        if exp_config.mode == 'single_persona':
            profile_ids_to_fetch.add(exp_config.profile_id)
        elif exp_config.mode == 'mixed_persona':
            profile_ids_to_fetch.update(p.profile_id for p in exp_config.persona_mix)
        elif exp_config.mode == 'sequential_persona':
            profile_ids_to_fetch.update(s.profile_id for s in exp_config.persona_sequence)

        persona_descriptions_map = {pid: get_profile_data(pid) for pid in profile_ids_to_fetch}
        if profile_ids_to_fetch:
            logger.info(f"Loaded {len(persona_descriptions_map)} personas for the experiment.")

        # E. Create the session in the database, storing the full experiment config
        session_id = create_session(experiment_config=config.model_dump())

        if video_context_ids:
            insert_context_videos(video_context_ids)

        # F. Set up the browser
        time.sleep(5)  # Pause for enrichment worker to potentially catch up
        driver = setup_browser()
        driver.get("https://www.youtube.com/")
        time.sleep(5)
        accept_cookies(driver)

        # G. Run the context and persona phases
        start_video_id, start_duration, context_length = None, 0, len(video_context_ids)
        if video_context_ids:
            start_video_id, start_duration = run_context_phase(driver, session_id, video_context_ids)

        if start_video_id:
            run_persona_phase(
                driver=driver, session_id=session_id, personas=persona_descriptions_map,
                start_video_id=start_video_id, start_duration=start_duration, context_length=context_length)
        else:
            logger.info("No starting video from context phase; scraper will finish.")

        update_session_status(session_id, 'completed')

    except ContextNotFoundError as e:
        logger.error(f"Configuration Error: {e}. Scraper cannot start.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        if session_id:
            update_session_status(session_id, 'failed')

    finally:
        if driver:
            driver.quit()
        close_connection_pool()
        logger.info("--- Scraper Bot Finished ---")



if __name__ == "__main__":
    main()