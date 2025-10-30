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


def add_profile(profile_name, persona_description):
    """
    Adds a new user persona profile to the database.
    """
    conn_string = f"host='{DB_HOST}' port='{DB_PORT}' dbname='{DB_NAME}' user='{DB_USER}' password='{DB_PASSWORD}'"

    try:
        with psycopg2.connect(conn_string) as conn:
            with conn.cursor() as cur:
                print(f"Adding profile: '{profile_name}'...")

                # Insert the new profile
                cur.execute(
                    "INSERT INTO profiles (profile_name, persona_description) VALUES (%s, %s) RETURNING profile_id;",
                    (profile_name, persona_description)
                )
                profile_id = cur.fetchone()[0]

                conn.commit()
                print(f"\n✅ Success! Profile '{profile_name}' created with ID: {profile_id}")
                print("You can now reference this profile_id in your config.yaml.")

    except psycopg2.errors.UniqueViolation:
        print(f"\n❌ Error: A profile with the name '{profile_name}' already exists. Please choose a unique name.")
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
        description="Add a new user persona to the YouTube Analysis database.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--name",
        required=True,
        help="The unique name for the new profile (e.g., 'News Junkie')."
    )
    parser.add_argument(
        "--desc",
        required=True,
        help="A detailed description of the user persona's interests and behaviors."
    )

    args = parser.parse_args()

    add_profile(args.name, args.desc)


if __name__ == "__main__":
    main()