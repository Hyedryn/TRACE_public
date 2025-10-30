"""Database operations for the YouTube scraper."""
import time
import logging
from contextlib import contextmanager
from typing import Optional, Tuple, List, Any
from dataclasses import dataclass
import json

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2 import pool
except ImportError:
    raise ImportError("psycopg2 is required. Install with: pip install psycopg2-binary")

from config import get_config

# Configure logging
logger = logging.getLogger(__name__)

# Connection pool for better resource management
_connection_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass


class ProfileNotFoundError(DatabaseError):
    """Exception raised when a profile is not found."""
    pass

class ContextNotFoundError(DatabaseError):
    """Exception raised when a context is not found."""
    pass

def initialize_connection_pool(minconn: int = 1, maxconn: int = 10) -> None:
    """Initialize the database connection pool."""
    global _connection_pool
    if _connection_pool is None:
        try:
            config = get_config()
            _connection_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn, maxconn, config.database.url
            )
            logger.info("Database connection pool initialized")
        except psycopg2.Error as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise DatabaseError(f"Failed to initialize connection pool: {e}")


def close_connection_pool() -> None:
    """Close all connections in the pool."""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("Database connection pool closed")


@contextmanager
def get_db_connection():
    """Context manager for database connections with automatic cleanup."""
    if _connection_pool is None:
        initialize_connection_pool()
    
    conn = None
    try:
        conn = _connection_pool.getconn()
        conn.autocommit = False  # Explicit transaction control
        yield conn
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error: {e}")
        raise DatabaseError(f"Database operation failed: {e}")
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Unexpected error: {e}")
        raise
    finally:
        if conn:
            _connection_pool.putconn(conn)


def create_session(experiment_config: dict) -> int:
    """Creates a new session in the database and returns the session ID."""
    query = """
            INSERT INTO sessions (experiment_config)
            VALUES (%(experiment_config)s) RETURNING session_id; \
            """

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Convert the dict to a JSON string for PostgreSQL's JSONB type
            cur.execute(query, {'experiment_config': json.dumps(experiment_config)})
            result = cur.fetchone()
            if not result:
                raise DatabaseError("Failed to create session")
            session_id = result['session_id']
            conn.commit()
            logger.info(f"Created session {session_id} with experiment config.")
            return session_id


def get_profile_data(profile_id: int) -> str:
    """Gets persona description for a profile."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Get persona description
            cur.execute(
                "SELECT persona_description FROM profiles WHERE profile_id = %(profile_id)s;",
                {'profile_id': profile_id}
            )
            persona_row = cur.fetchone()
            if not persona_row:
                raise ProfileNotFoundError(f"Profile with ID {profile_id} not found")

            persona_description = persona_row['persona_description']

            logger.info(f"Retrieved persona description for profile {profile_id}")
            return persona_description


def get_context_videos_by_name(context_name: str) -> List[str]:
    """Gets the list of video IDs for a named context."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT video_ids FROM experiment_contexts WHERE context_name = %s;",
                (context_name,)
            )
            context_row = cur.fetchone()
            if not context_row:
                raise ContextNotFoundError(f"Context with name '{context_name}' not found in the database.")

            video_ids = context_row['video_ids']
            logger.info(f"Retrieved {len(video_ids)} videos for context '{context_name}'")
            return video_ids


def insert_context_videos(video_context_ids: List[str]) -> None:
    """Pre-inserts context videos to ensure they exist for foreign key constraints."""
    if not video_context_ids:
        return

    logger.info(f"Pre-loading {len(video_context_ids)} context videos into database")

    query = """
        INSERT INTO videos (video_youtube_id, title) 
        VALUES (%(video_id)s, %(title)s) 
        ON CONFLICT (video_youtube_id) DO NOTHING;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Use executemany for better performance
            data = [
                {'video_id': video_id, 'title': 'Context Video - Title Pending Enrichment'}
                for video_id in video_context_ids
            ]
            cur.executemany(query, data)
            conn.commit()
            logger.info(f"Successfully pre-loaded {len(video_context_ids)} context videos")


def get_video_duration(video_id: str) -> int:
    """Gets video duration from database."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT duration_seconds FROM videos WHERE video_youtube_id = %(video_id)s;",
                {'video_id': video_id}
            )
            result_row = cur.fetchone()
            
            if result_row and result_row['duration_seconds'] is not None:
                duration = result_row['duration_seconds']
                logger.info(f"Found pre-existing duration in DB: {duration} seconds for video {video_id}")
                return duration
            
            logger.info(f"Duration not found in DB for video {video_id}. Will determine from page.")
            return 0


def insert_video_and_recommendations(
        session_id: int,
        depth: int,
        source_video_id: str,
        parsed_recs,
        chosen_video_id: Optional[str] = None,
        justification: Optional[str] = None,
        is_context: bool = False,
        profile_id_at_choice: Optional[int] = None,
        choice_method: Optional[str] = None
) -> None:
    """
    Inserts video metadata and the full list of recommendations into the database.
    It specifically logs which video was chosen, why, and under which persona/method.
    """

    from models import RecommendationsList
    from video_parser import parse_duration

    # Handle both Pydantic models and legacy dict formats
    if isinstance(parsed_recs, RecommendationsList):
        recommendations = [rec.model_dump() for rec in parsed_recs.recommendations]
    elif isinstance(parsed_recs, list) and parsed_recs and hasattr(parsed_recs[0], 'model_dump'):
        recommendations = [rec.model_dump() for rec in parsed_recs]
    else:
        recommendations = parsed_recs

    if not recommendations:
        logger.warning("No recommendations provided to insert.")
        return

    # Query to insert or update video details. This ensures every seen video has an entry.
    video_query = """
                  INSERT INTO videos (video_youtube_id, title, duration_seconds)
                  VALUES (%(video_id)s, %(title)s, %(duration_seconds)s) ON CONFLICT (video_youtube_id) DO \
                  UPDATE SET
                      title = EXCLUDED.title, \
                      duration_seconds = CASE \
                      WHEN videos.last_enriched_at IS NULL THEN EXCLUDED.duration_seconds \
                      ELSE videos.duration_seconds
                  END; \
                  """

    # Query to log every single recommendation.
    recommendation_query = """
                           INSERT INTO recommendation_log (session_id, depth, source_video_id, recommended_video_id, \
                                                           recommendation_rank, recommendation_source, was_selected, \
                                                           justification, view_count_when_recommended, \
                                                           was_during_context, \
                                                           profile_id_at_choice, choice_method) \
                           VALUES (%(session_id)s, %(depth)s, %(source_video_id)s, %(recommended_video_id)s, \
                                   %(recommendation_rank)s, %(recommendation_source)s, %(was_selected)s, \
                                   %(justification)s, %(view_count_when_recommended)s, %(was_during_context)s, \
                                   %(profile_id_at_choice)s, %(choice_method)s); \
                           """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            video_data = []
            recommendation_data = []

            for i, rec in enumerate(recommendations):
                was_selected = (rec["video_id"] == chosen_video_id)

                # Prepare data for the 'videos' table
                video_data.append({
                    'video_id': rec["video_id"],
                    'title': rec["title"],
                    'duration_seconds': parse_duration(rec.get("duration"))
                })

                # Prepare data for the 'recommendation_log' table
                recommendation_data.append({
                    'session_id': session_id,
                    'depth': depth,
                    'source_video_id': source_video_id,
                    'recommended_video_id': rec["video_id"],
                    'recommendation_rank': i + 1,
                    'recommendation_source': rec.get("recommendation_source", "context" if is_context else "sidebar"),
                    'was_selected': was_selected,
                    'justification': justification if was_selected else None,
                    'view_count_when_recommended': rec.get("views"),
                    'was_during_context': is_context,
                    'profile_id_at_choice': profile_id_at_choice if was_selected else None,
                    'choice_method': choice_method if was_selected else None
                })

            video_data.sort(key=lambda x: x['video_id'])

            # Use executemany for efficient batch inserting
            if video_data:
                cur.executemany(video_query, video_data)

            if recommendation_data:
                cur.executemany(recommendation_query, recommendation_data)

            conn.commit()

            logger.info(
                f"Inserted {len(video_data)} videos and {len(recommendation_data)} recommendation logs for session {session_id}")

def log_persona_filter(
    session_id: int, 
    video_id: str, 
    was_filtered: bool, 
    justification: str, 
    transcript: str
) -> None:
    """Logs persona filter results."""
    query = """
        INSERT INTO persona_filter_logs (
            session_id, video_id, was_filtered, filter_justification, video_transcript
        ) VALUES (
            %(session_id)s, %(video_id)s, %(was_filtered)s, 
            %(filter_justification)s, %(video_transcript)s
        );
    """
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, {
                'session_id': session_id,
                'video_id': video_id,
                'was_filtered': was_filtered,
                'filter_justification': justification,
                'video_transcript': transcript
            })
            conn.commit()
            logger.info(f"Logged persona filter result for video {video_id} in session {session_id}")


def update_session_status(session_id: int, status: str) -> None:
    """Updates session status."""
    query = """
        UPDATE sessions 
        SET status = %(status)s, end_time = NOW() 
        WHERE session_id = %(session_id)s;
    """
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, {'status': status, 'session_id': session_id})
            if cur.rowcount == 0:
                logger.warning(f"No session found with ID {session_id}")
            else:
                conn.commit()
                logger.info(f"Updated session {session_id} status to {status}")

