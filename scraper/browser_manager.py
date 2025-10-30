"""Browser management for the YouTube scraper."""
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.proxy import Proxy, ProxyType
from config import get_config

logger = logging.getLogger(__name__)

def setup_browser(proxy=None):
    """Sets up and returns a configured browser driver."""
    config = get_config()
    browser_type = config.scraping.browser_type
    
    logger.info(f"Initializing Selenium WebDriver for: {browser_type.upper()}")
    
    if browser_type == "firefox":
        browser_options = FirefoxOptions()
    elif browser_type == "chrome":
        browser_options = ChromeOptions()
    else:
        raise ValueError(f"Unsupported browser_type: {browser_type}. Choose 'chrome' or 'firefox'.")

    if proxy:
        logger.info(f"Using proxy: {proxy}")
        if browser_type == "firefox":
            # For Firefox, using the Proxy object is often more reliable
            my_proxy = Proxy()
            my_proxy.proxy_type = ProxyType.MANUAL
            my_proxy.http_proxy = f"http://{proxy}"
            my_proxy.ssl_proxy = f"http://{proxy}"
            browser_options.proxy = my_proxy
        else:  # Chrome
            browser_options.add_argument(f'--proxy-server={proxy}')

    selenium_hub_url = config.selenium.hub_url
    if selenium_hub_url:
        logger.info(f"Connecting to Selenium Hub at {selenium_hub_url}")
        driver = webdriver.Remote(
            command_executor=selenium_hub_url,
            options=browser_options
        )
    else:
        logger.info(f"Connecting to local {browser_type.capitalize()} driver")
        if browser_type == "firefox":
            driver = webdriver.Firefox(options=browser_options)
        else:  # Default to Chrome for local
            driver = webdriver.Chrome(options=browser_options)

    return driver


def accept_cookies(driver):
    """Accepts YouTube cookies if the consent dialog appears."""
    try:
        logger.info("Checking for and clicking the cookie consent button...")
        # This XPath targets the "Accept all" button in the consent dialog.
        cookie_button_xpath = "//*[@id='content']/div[2]/div[6]/div[1]/ytd-button-renderer[2]/yt-button-shape/button"

        # Wait up to 10 seconds for the button to be clickable, then click it.
        accept_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, cookie_button_xpath))
        )
        accept_button.click()
        logger.info("Cookie consent button clicked.")
        time.sleep(2)  # Brief pause to allow the UI to update after the click.
    except Exception:
        # This will catch TimeoutException if the button doesn't appear, which is fine.
        logger.warning("Cookie consent button not found or not clickable, continuing...")


def scroll_to_load_recommendations(driver):
    """Scrolls down the page to ensure lazy-loaded recommendation videos are loaded into the DOM."""
    try:
        logger.info("Scrolling to load recommendations...")
        # Wait for the main recommendations container to be present
        related_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "related"))
        )

        # Scroll the container into view to start
        driver.execute_script("arguments[0].scrollIntoView(true);", related_container)
        time.sleep(2)  # Wait for initial content to load after scrolling

        # Perform a few more incremental scrolls to be sure
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 200);")  # Scroll down 200 pixels
            time.sleep(2)  # Pause to allow content to render

        logger.info("Scrolling complete.")
    except Exception as e:
        logger.error(f"Could not scroll to find recommendations: {e}")


def get_recommendations_html(driver):
    """Gets the recommended videos from the related videos section and cleans them."""
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "related"))
    )

    js_cleaner_script = """
        const block = arguments[0];
        const selectorsToRemove = [
            '.yt-lockup-metadata-view-model-wiz__menu-button',
            'ytd-menu-renderer',
            'yt-interaction',
            'ytd-badge-supported-renderer',
            '#menu',
            '.yt-core-image' // Only remove the image, not the whole thumbnail
        ];

        // Remove all elements matching the selectors
        selectorsToRemove.forEach(selector => {
            block.querySelectorAll(selector).forEach(el => el.remove());
        });

        // Remove all HTML comment nodes
        const iterator = document.createNodeIterator(block, NodeFilter.SHOW_COMMENT);
        let node;
        while (node = iterator.nextNode()) {
            node.remove();
        }

        return block.innerHTML;
        """

    recommendation_blocks = driver.find_elements(By.CSS_SELECTOR, "yt-lockup-view-model, ytd-compact-video-renderer")
    
    cleaned_html_list = []
    for block in recommendation_blocks[:20]:
        cleaned_html = driver.execute_script(js_cleaner_script, block)
        cleaned_html_list.append(cleaned_html.strip())

    return cleaned_html_list