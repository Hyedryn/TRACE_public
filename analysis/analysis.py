import os
import sys
import psycopg2
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from dotenv import load_dotenv

# --- CONFIGURATION ---
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")


def connect_to_db():
    """Establishes a connection to the PostgreSQL database."""
    conn_string = f"host='{DB_HOST}' port='{DB_PORT}' dbname='{DB_NAME}' user='{DB_USER}' password='{DB_PASSWORD}'"
    try:
        conn = psycopg2.connect(conn_string)
        print("Database connection established.")
        return conn
    except psycopg2.OperationalError as e:
        print(f"❌ Database Connection Error: {e}", file=sys.stderr)
        print("Ensure the database container is running ('docker-compose up -d db') and accessible.", file=sys.stderr)
        return None


def fetch_all_recommendation_data(conn):
    """
    Fetches all persona-phase recommendation data, joining with profiles for choices
    and videos for metadata. This is the main data retrieval function.
    """
    print("Fetching recommendation data from the database...")
    query = """
            SELECT r.log_id, \
                   r.session_id, \
                   r.depth, \
                   r.recommendation_rank, \
                   r.was_selected, \
                   r.choice_method, \
                   p.profile_name, -- The name of the profile that made the choice \
                   v.title         AS recommended_video_title, \
                   v.channel_title AS recommended_channel_title, \
                   v.category_id   AS recommended_category_id, \
                   source_v.title  AS source_video_title
            FROM recommendation_log r
                     JOIN videos v ON r.recommended_video_id = v.video_youtube_id
                -- LEFT JOIN is crucial because profile_id_at_choice can be NULL (for random choices or context phase)
                     LEFT JOIN profiles p ON r.profile_id_at_choice = p.profile_id
                     LEFT JOIN videos source_v ON r.source_video_id = source_v.video_youtube_id
            -- Only analyze the main persona/experiment phase, not the initial context-setting
            WHERE r.was_during_context = FALSE; \
            """
    df = pd.read_sql_query(query, conn)
    print(f"Successfully fetched {len(df)} recommendation log entries.")
    return df


def analyze_and_print_summary(df, title_prefix):
    """
    Analyzes and prints a summary for a given subset of the data (e.g., a specific persona).
    """
    if df.empty:
        print(f"\n--- No data for {title_prefix}. Skipping analysis. ---")
        return None

    print(f"\n--- Analysis for '{title_prefix}' ---")

    # Analyze the diversity of ALL videos that were recommended
    total_recommendations = len(df)
    unique_recommended_channels = df['recommended_channel_title'].nunique()
    print(f"\nOverall Recommendation Diversity:")
    print(f"  Total recommendations shown: {total_recommendations}")
    print(f"  Unique channels recommended: {unique_recommended_channels}")

    # Isolate only the videos that were actually selected
    df_selected = df[df['was_selected'] == True].copy()
    if df_selected.empty:
        print("\nNo videos were selected in this data subset.")
        return {'unique_recommended_channels': unique_recommended_channels, 'unique_selected_channels': 0}

    # Analyze the diversity of the SELECTED videos
    total_selections = len(df_selected)
    unique_selected_channels = df_selected['recommended_channel_title'].nunique()
    print(f"\nSelected Video Diversity:")
    print(f"  Total videos selected: {total_selections}")
    print(f"  Unique channels selected: {unique_selected_channels}")

    # Show the top 5 most frequently selected channels
    top_channels = df_selected['recommended_channel_title'].value_counts().head(5)
    print("\nTop 5 most selected channels:")
    print(top_channels.to_string())

    return {
        'unique_recommended_channels': unique_recommended_channels,
        'unique_selected_channels': unique_selected_channels
    }


def main():
    """Main function to run the analysis and generate visualizations."""
    conn = connect_to_db()
    if not conn:
        return

    # Fetch all relevant data in a single query
    df_all = fetch_all_recommendation_data(conn)
    if df_all.empty:
        print("No recommendation data found in the database. Exiting.")
        conn.close()
        return

    # --- DATA SUBSETTING ---
    # Create different dataframes for each experimental group you want to analyze
    df_palestine = df_all[df_all['profile_name'] == 'Pro-Palestine'].copy()
    df_israel = df_all[df_all['profile_name'] == 'Pro-Israel'].copy()
    df_random = df_all[df_all['choice_method'] == 'random'].copy()

    # --- ANALYSIS ---
    # Run the analysis for each group
    analysis_results = {}
    analysis_results['Pro-Palestine'] = analyze_and_print_summary(df_palestine, "Pro-Palestine Persona")
    analysis_results['Pro-Israel'] = analyze_and_print_summary(df_israel, "Pro-Israel Persona")
    analysis_results['Random Baseline'] = analyze_and_print_summary(df_random, "Random Choice Baseline")

    # --- VISUALIZATION ---
    print("\n--- Generating Visualizations ---")

    # Filter out any groups that had no data
    valid_results = {k: v for k, v in analysis_results.items() if v}

    if len(valid_results) < 2:
        print("Need at least two groups with data to generate comparison charts.")
        conn.close()
        return

    # 1. Compare diversity of SELECTED channels (Filter Bubble Analysis)
    labels = list(valid_results.keys())
    selected_diversity = [res['unique_selected_channels'] for res in valid_results.values()]

    plt.figure(figsize=(12, 7))
    sns.barplot(x=labels, y=selected_diversity)
    plt.title('Comparison of Selected Channel Diversity (Filter Bubble Effect)', fontsize=16)
    plt.ylabel('Number of Unique Channels Selected', fontsize=12)
    plt.xticks(rotation=10)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig('selected_channel_diversity.png')
    print("Saved selected channel diversity comparison to 'selected_channel_diversity.png'")
    plt.close()

    # 2. Compare diversity of ALL RECOMMENDED channels (Algorithmic Curation Analysis)
    recommended_diversity = [res['unique_recommended_channels'] for res in valid_results.values()]

    plt.figure(figsize=(12, 7))
    sns.barplot(x=labels, y=recommended_diversity)
    plt.title('Comparison of Overall Recommended Channel Diversity', fontsize=16)
    plt.ylabel('Total Unique Channels Recommended', fontsize=12)
    plt.xticks(rotation=10)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig('recommended_channel_diversity.png')
    print("Saved recommended channel diversity comparison to 'recommended_channel_diversity.png'")
    plt.close()

    conn.close()
    print("\nAnalysis complete.")


if __name__ == "__main__":
    main()
