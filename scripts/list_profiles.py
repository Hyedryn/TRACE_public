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


def list_profiles():
    """
    Fetches and displays all user persona profiles from the database.
    """
    conn_string = f"host='{DB_HOST}' port='{DB_PORT}' dbname='{DB_NAME}' user='{DB_USER}' password='{DB_PASSWORD}'"

    try:
        with psycopg2.connect(conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT profile_id, profile_name, persona_description FROM profiles ORDER BY profile_id;")
                profiles = cur.fetchall()

                if not profiles:
                    print("No profiles found in the database.")
                    print("You can add one using 'python scripts/add_profile.py'")
                    return

                print("\n--- Available User Personas ---")
                # Define column widths
                id_width = 1
                name_width = 28
                desc_width = 100

                # Print header
                print(f"{'ID':<{id_width}} | {'Name':<{name_width}} | {'Description'}")
                print("-" * (id_width + name_width + desc_width + 5))

                # Print rows
                for profile_id, name, description in profiles:
                    # Truncate long descriptions for cleaner display
                    if len(description) > desc_width - 3:
                        description = description[:desc_width - 3] + "..."

                    print(f"{profile_id:<{id_width}} | {name:<{name_width}} | {description}")
                print("-" * (id_width + name_width + desc_width + 5))
                print(f"Found {len(profiles)} profiles.\n")


    except psycopg2.OperationalError as e:
        print(f"\n❌ Database Connection Error: Could not connect to the PostgreSQL container.", file=sys.stderr)
        print("Please ensure the database service is running ('docker-compose up -d db').", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    list_profiles()


if __name__ == "__main__":
    main()
