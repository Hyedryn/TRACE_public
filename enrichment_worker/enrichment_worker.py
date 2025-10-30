import os
import time
import psycopg2
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
import re

# --- CONFIGURATION ---
DATABASE_URL = os.environ.get("DATABASE_URL")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
WEBSHARE_PROXY_USERNAME = os.environ.get("WEBSHARE_PROXY_USERNAME")
WEBSHARE_PROXY_PASSWORD = os.environ.get("WEBSHARE_PROXY_PASSWORD")

# --- ENRICHMENT WORKER LOGIC ---
def parse_iso8601_duration(duration_str):
    """
    Parses an ISO 8601 duration string (e.g., PT1M30S) into total seconds.
    """
    if not duration_str:
        return 0

    # Regex to extract hours, minutes, and seconds from the ISO 8601 string
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match:
        return 0

    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0
    seconds = int(match.group(3)) if match.group(3) else 0

    total_seconds = hours * 3600 + minutes * 60 + seconds
    return total_seconds


def connect_to_db(max_retries=5, delay=5):
    """Attempts to connect to the database with retries."""
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            print("Database connection established.")
            return conn
        except psycopg2.OperationalError as e:
            print(f"Database connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt + 1 == max_retries:
                print("Could not connect to the database. Exiting.")
                raise
            print(f"Retrying in {delay} seconds...")
            time.sleep(delay)

def main():
    print("Starting enrichment worker...")
    conn = connect_to_db()
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

    if WEBSHARE_PROXY_USERNAME and WEBSHARE_PROXY_PASSWORD:
        ytt_api = YouTubeTranscriptApi(proxy_config=WebshareProxyConfig(
            proxy_username=WEBSHARE_PROXY_USERNAME,
            proxy_password=WEBSHARE_PROXY_PASSWORD
        ))
    else:
        ytt_api = YouTubeTranscriptApi()

    while True:
        try:
            cur = conn.cursor()

            # Find videos that need enrichment
            cur.execute("SELECT video_youtube_id FROM videos WHERE last_enriched_at IS NULL LIMIT 50;")
            video_ids = [row[0] for row in cur.fetchall()]

            if video_ids:
                print(f"Found {len(video_ids)} videos to enrich.")
                try:
                    # --- YOUTUBE DATA API ---
                    request = youtube.videos().list(
                        part="snippet,contentDetails,statistics",
                        id=",".join(video_ids)
                    )
                    response = request.execute()

                    for item in response.get("items", []):
                        video_id = item["id"]
                        snippet = item.get("snippet", {})
                        content_details = item.get("contentDetails", {})
                        statistics = item.get("statistics", {})

                        iso_duration = content_details.get("duration")
                        duration_in_seconds = parse_iso8601_duration(iso_duration)

                        # --- TRANSCRIPT API ---
                        try:
                            transcript_list = ytt_api.fetch(video_id).to_raw_data()
                            transcript = " ".join([t["text"] for t in transcript_list])
                        except Exception as e:
                            transcript = None
                            print(f"Could not get transcript for {video_id}: {e}")

                        # --- UPDATE DATABASE ---
                        # --- UPDATE DATABASE ---
                        cur.execute(
                            """UPDATE videos
                               SET title            = %s,
                                   description      = %s,
                                   channel_id       = %s,
                                   channel_title    = %s,
                                   published_at     = %s,
                                   transcript       = %s,
                                   tags             = %s,
                                   category_id      = %s,
                                   duration_seconds = %s,
                                   last_enriched_at = NOW()
                               WHERE video_youtube_id = %s;""",
                            (
                                snippet.get("title"),
                                snippet.get("description"),
                                snippet.get("channelId"),
                                snippet.get("channelTitle"),
                                snippet.get("publishedAt"),
                                transcript,
                                snippet.get("tags"),
                                snippet.get("categoryId"),
                                duration_in_seconds,
                                video_id
                            )
                        )
                    conn.commit()
                    print(f"Successfully enriched {len(video_ids)} videos.")

                except Exception as e:
                    print(f"An error occurred during enrichment: {e}")
                    conn.rollback()
            
            else:
                print("No videos to enrich. Waiting...")

            cur.close()

        except (psycopg2.InterfaceError, psycopg2.OperationalError) as e:
            print(f"Database connection lost: {e}. Reconnecting...")
            conn.close()
            conn = connect_to_db()
        
        except Exception as e:
            print(f"An unexpected error occurred in the main loop: {e}")

        time.sleep(60) # Wait for a minute before checking for new tasks

if __name__ == "__main__":
    main()
