"""Recommendation parsing using both LLM and BeautifulSoup methods."""
import re
import logging
from typing import List

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from llm_services import parse_recommendations_with_llm
from models import LLMError, VideoRecommendation, RecommendationsList
from config import get_config

logger = logging.getLogger(__name__)


def get_llm_config_for_task(task: str):
    """Gets the LLM configuration for a specific task."""
    config = get_config()
    return config.get_llm_provider_config(task)


def parse_recommendations_with_llm_structured(recommendations_html_list: List[str]) -> RecommendationsList:
    """Uses an LLM with structured output to parse the recommendations HTML."""
    llm_config = get_llm_config_for_task("parse_recommendations")
    logger.info("Parsing %d recommendations with LLM provider: %s", 
                len(recommendations_html_list), llm_config.provider)
    
    try:
        return parse_recommendations_with_llm(
            provider=llm_config.provider,
            model=llm_config.model,
            recommendations_html_list=recommendations_html_list
        )
    except Exception as e:
        logger.error("LLM parsing failed: %s", e)
        raise LLMError(f"Failed to parse recommendations with LLM: {e}") from e


def parse_recommendations_with_bs(recommendations_html_list: List[str]) -> RecommendationsList:
    """Uses BeautifulSoup to parse the recommendations HTML."""
    if BeautifulSoup is None:
        raise ImportError("BeautifulSoup not available. Install with: pip install beautifulsoup4 lxml")
    
    logger.info("Parsing recommendations with BeautifulSoup")
    recommendations = []

    def get_duration_from_aria_label(soup, selectors):
        for selector in selectors:
            element = soup.select_one(selector)
            if element and element.has_attr('aria-label'):
                aria_label = element['aria-label']
                # Regex to find patterns like "1 hour, 13 minutes", "26 minutes, 15 seconds", "14 minutes", etc.
                match = re.search(r"(?:(\d+)\s+hours?,?\s*)?(?:(\d+)\s+minutes?,?\s*)?(?:(\d+)\s+seconds?)?", aria_label)
                if match:
                    hours, minutes, seconds = match.groups()
                    duration_parts = []
                    if hours:
                        duration_parts.append(hours)
                    if minutes:
                        duration_parts.append(minutes.zfill(2))
                    if seconds:
                        duration_parts.append(seconds.zfill(2))
                    return ":".join(duration_parts)
        return None

    for html_content in recommendations_html_list:
        soup = BeautifulSoup(html_content, 'lxml')

        # --- Fallback Selectors ---
        title_selectors = ['h3.yt-lockup-metadata-view-model__heading-reset a span', 'h3.yt-lockup-metadata-view-model-wiz__heading-reset a span', 'span#video-title']
        publisher_selectors = ['span.yt-content-metadata-view-model__metadata-text', '.yt-content-metadata-view-model-wiz__metadata-text', '#text > a']
        views_selectors = ['span.yt-content-metadata-view-model__metadata-text', '.yt-content-metadata-view-model-wiz__metadata-text', 'span.ytd-video-meta-block']
        link_selectors = ['h3.yt-lockup-metadata-view-model__heading-reset a', 'h3.yt-lockup-metadata-view-model-wiz__heading-reset a', 'a#video-title-link']
        duration_selectors = ['div.yt-badge-shape__text', '.yt-lockup-thumbnail-view-model__time-text', 'span.ytd-thumbnail-overlay-time-status-renderer', '.badge-shape-wiz__text']

        def get_element_text(selectors):
            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    return element.text.strip()
            return None

        def get_link(selectors):
            for selector in selectors:
                element = soup.select_one(selector)
                if element and element.has_attr('href'):
                    return element['href']
            return None

        title = get_element_text(title_selectors)
        publisher = get_element_text(publisher_selectors)
        
        raw_link = get_link(link_selectors)
        video_id = None
        if raw_link:
            match = re.search(r"v=([a-zA-Z0-9_-]+)", raw_link)
            if match:
                video_id = match.group(1)
        
        link = f"https://www.youtube.com/watch?v={video_id}" if video_id else None

        duration = get_element_text(duration_selectors)
        if not duration:
            duration = get_duration_from_aria_label(soup, link_selectors)

        views_text = None
        for selector in views_selectors:
            elements = soup.select(selector)
            for element in elements:
                if 'views' in element.text or 'vues' in element.text:
                    views_text = element.text.strip()
                    break
            if views_text:
                break

        views = 0
        if views_text:
            original_views_text = views_text
            cleaned_views_text = re.sub(r'[^\d,.]', '', original_views_text)
            if cleaned_views_text:
                try:
                    if 'K' in original_views_text or 'k' in original_views_text:
                        views = int(float(cleaned_views_text.replace(',', '.')) * 1000)
                    elif 'M' in original_views_text or 'm' in original_views_text:
                        views = int(float(cleaned_views_text.replace(',', '.')) * 1000000)
                    else:
                        views = int(cleaned_views_text.replace(',', '').replace('.', ''))
                except ValueError:
                    views = 0

        if all([title, publisher, views, video_id, link, duration]):
            recommendations.append(VideoRecommendation(
                title=title,
                publisher=publisher,
                views=views,
                video_id=video_id,
                link=link,
                duration=duration
            ))
        else:
            logger.debug("Skipped incomplete recommendation block: "
                        "title=%s, publisher=%s, views=%s, video_id=%s, "
                        "link=%s, duration=%s", 
                        bool(title), bool(publisher), views, 
                        bool(video_id), bool(link), bool(duration))
            logger.debug("html_content: %s", html_content)
    
    logger.info("Successfully parsed %d recommendations with BeautifulSoup", len(recommendations))
    return RecommendationsList(recommendations=recommendations)


def parse_recommendations(recommendations_html_list: List[str]) -> RecommendationsList:
    """Parses recommendations using the configured method (LLM or BeautifulSoup)."""
    if not recommendations_html_list:
        logger.warning("No recommendation HTML blocks provided")
        return RecommendationsList(recommendations=[])
    
    config = get_config()
    
    try:
        if config.scraping.parser_method == 'bs':
            return parse_recommendations_with_bs(recommendations_html_list)
        
        # Default to LLM with structured output
        return parse_recommendations_with_llm_structured(recommendations_html_list)
        
    except Exception as e:
        logger.error("Failed to parse recommendations: %s", e)
        # Fallback to BeautifulSoup if LLM fails and BS is available
        if config.scraping.parser_method != 'bs' and BeautifulSoup is not None:
            logger.info("Falling back to BeautifulSoup parsing")
            try:
                return parse_recommendations_with_bs(recommendations_html_list)
            except Exception as bs_error:
                logger.error("BeautifulSoup fallback also failed: %s", bs_error)
        
        raise LLMError(f"All parsing methods failed: {e}") from e