#!/usr/bin/env python3
import os
import sys
import psycopg2
import argparse
from dotenv import load_dotenv

# --- CONFIGURATION ---
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")


def add_context(context_name, description, video_ids):
    """
    Adds a new, named experiment context to the database.
    """
    conn_string = f"host='{DB_HOST}' port='{DB_PORT}' dbname='{DB_NAME}' user='{DB_USER}' password='{DB_PASSWORD}'"

    try:
        with psycopg2.connect(conn_string) as conn:
            with conn.cursor() as cur:
                print(f"Adding context: '{context_name}'...")

                # Insert the new context with its list of video IDs
                cur.execute(
                    """INSERT INTO experiment_contexts (context_name, description, video_ids)
                       VALUES (%s, %s, %s) RETURNING context_id;""",
                    (context_name, description, video_ids)
                )
                context_id = cur.fetchone()[0]

                conn.commit()
                print(f"\n✅ Success! Context '{context_name}' created with ID: {context_id}")
                print(f"Added {len(video_ids)} videos to the context.")
                print("You can now reference this context by name in your config.yaml.")

    except psycopg2.errors.UniqueViolation:
        print(f"\n❌ Error: A context with the name '{context_name}' already exists. Please choose a unique name.")
        sys.exit(1)
    except psycopg2.OperationalError as e:
        print(f"\n❌ Database Connection Error: Could not connect to the PostgreSQL container.")
        print("Please ensure the database service is running ('docker-compose up -d db').")
        print(f"Details: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Add a new reusable context (a named list of video IDs) to the database.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--name",
        required=True,
        help="The unique name for this context (e.g., 'Initial Tech Exploration')."
    )
    parser.add_argument(
        "--desc",
        required=True,
        help="A brief description of what this context represents or is used for."
    )
    parser.add_argument(
        "--videos",
        nargs='+',
        required=True,
        metavar="VIDEO_ID",
        help="A space-separated list of YouTube video IDs (e.g., dQw4w9WgXcQ G_y2p1a2iXQ)."
    )

    args = parser.parse_args()

    add_context(args.name, args.desc, args.videos)


if __name__ == "__main__":
    main()
