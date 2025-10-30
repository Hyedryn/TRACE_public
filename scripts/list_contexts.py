#!/usr/bin/env python3
import os
import sys
import psycopg2
from dotenv import load_dotenv

# --- CONFIGURATION ---
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")


def list_contexts():
    """
    Fetches and displays all experiment contexts from the database,
    including a sample of the video IDs.
    """
    conn_string = f"host='{DB_HOST}' port='{DB_PORT}' dbname='{DB_NAME}' user='{DB_USER}' password='{DB_PASSWORD}'"

    try:
        with psycopg2.connect(conn_string) as conn:
            with conn.cursor() as cur:
                # Updated query to also fetch the video_ids array itself
                query = """
                        SELECT context_id, \
                               context_name, \
                               description, \
                               cardinality(video_ids) as video_count, \
                               video_ids
                        FROM experiment_contexts
                        ORDER BY context_id; \
                        """
                cur.execute(query)
                contexts = cur.fetchall()

                if not contexts:
                    print("No contexts found in the database.")
                    print("You can add one using 'python scripts/add_context.py'")
                    return

                print("\n--- Available Experiment Contexts ---")
                # Define column widths, adding one for the video IDs
                id_width = 4
                name_width = 25
                count_width = 8
                desc_width = 45
                videos_width = 40  # Width for the new video IDs column

                # Print header
                header = (f"{'ID':<{id_width}} | {'Name':<{name_width}} | {'# Videos':<{count_width}} | "
                          f"{'Description':<{desc_width}} | {'Video IDs (Sample)'}")
                print(header)
                print("-" * len(header))

                # Print rows
                for context_id, name, description, video_count, video_ids in contexts:
                    # Truncate long descriptions
                    if len(description) > desc_width - 3:
                        description = description[:desc_width - 3] + "..."

                    # --- Format the video IDs list for display ---
                    video_sample_str = ""
                    if video_ids:
                        video_sample_str = str(video_ids)

                    # Truncate the final string if it's too long
                    if len(video_sample_str) > videos_width - 3:
                        video_sample_str = video_sample_str[:videos_width - 3] + "..."

                    print(f"{context_id:<{id_width}} | {name:<{name_width}} | {video_count:<{count_width}} | "
                          f"{description:<{desc_width}} | {video_sample_str}")

                print("-" * len(header))
                print(f"Found {len(contexts)} contexts.\n")


    except psycopg2.OperationalError as e:
        print(f"\n❌ Database Connection Error: Could not connect to the PostgreSQL container.", file=sys.stderr)
        print("Please ensure the database service is running ('docker-compose up -d db').", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    list_contexts()


if __name__ == "__main__":
    main()