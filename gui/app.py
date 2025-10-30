import os
import uuid
import subprocess
import yaml
import json
import docker
import psycopg2
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

SETTINGS_FILE = '/app/settings.json'

# Default settings
DEFAULT_SETTINGS = {
    'max_duration': 300,
    'parser_method': 'bs',
    'persona_filter_enabled': True,
    'persona_filter_seconds': 60,
    'persona_filter_transcript_seconds': 120
}

# Cache for auto-detected Docker configuration
_docker_network = None
_scraper_image = None
_vnc_host = None

def get_vnc_host():
    """Get the hostname to use for VNC URLs."""
    global _vnc_host
    if _vnc_host is None:
        # Try environment variable first
        _vnc_host = os.environ.get('VNC_HOST')
        if not _vnc_host:
            # Try to detect from request context, fallback to localhost
            try:
                from flask import request
                _vnc_host = request.host.split(':')[0]
            except:
                _vnc_host = 'localhost'
    return _vnc_host

def get_docker_network():
    """Auto-detect the Docker network this container is on."""
    global _docker_network
    if _docker_network is None:
        try:
            client = docker.from_env()
            # Get the gui container itself
            gui_container = client.containers.get('gui')
            # Get the first network it's connected to
            networks = list(gui_container.attrs['NetworkSettings']['Networks'].keys())
            if networks:
                _docker_network = networks[0]
                app.logger.info(f"Auto-detected Docker network: {_docker_network}")
            else:
                _docker_network = "youtubestats_default"  # Fallback
                app.logger.warning(f"Could not detect network, using fallback: {_docker_network}")
        except Exception as e:
            app.logger.error(f"Error detecting Docker network: {e}")
            _docker_network = "youtubestats_default"  # Fallback
    return _docker_network

def get_scraper_image():
    """Auto-detect an available scraper image."""
    global _scraper_image
    if _scraper_image is None:
        try:
            client = docker.from_env()
            # Look for any image with 'scraper' in the name
            images = client.images.list()
            for image in images:
                if image.tags:
                    for tag in image.tags:
                        if 'scraper' in tag.lower():
                            _scraper_image = tag
                            app.logger.info(f"Auto-detected scraper image: {_scraper_image}")
                            break
                if _scraper_image:
                    break

            if not _scraper_image:
                # Fallback to hardcoded name
                _scraper_image = "youtubestats-scraper-tech-enthusiast:latest"
                app.logger.warning(f"Could not detect scraper image, using fallback: {_scraper_image}")
        except Exception as e:
            app.logger.error(f"Error detecting scraper image: {e}")
            _scraper_image = "youtubestats-scraper-tech-enthusiast:latest"  # Fallback
    return _scraper_image

def load_settings():
    """Load settings from file, or return defaults if file doesn't exist."""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        app.logger.error(f"Error loading settings: {e}")
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Save settings to file."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        app.logger.error(f"Error saving settings: {e}")
        return False

# Database connection
def get_db_connection():
    conn = psycopg2.connect(
        host="db",
        database=os.environ.get("POSTGRES_DB"),
        user=os.environ.get("POSTGRES_USER"),
        password=os.environ.get("POSTGRES_PASSWORD"))
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/profiles')
def get_profiles():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT profile_id, profile_name FROM profiles ORDER BY profile_name")
    profiles = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{"id": p[0], "name": p[1]} for p in profiles])

@app.route('/api/contexts')
def get_contexts():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT context_id, context_name FROM experiment_contexts ORDER BY context_name")
    contexts = cur.fetchall()
    app.logger.info(f"Contexts from DB: {contexts}")
    cur.close()
    conn.close()
    return jsonify([{"id": c[0], "name": c[1]} for c in contexts])

@app.route('/api/start-experiment', methods=['POST'])
def start_experiment():
    data = request.json
    experiment_mode = data.get('mode')
    profile_ids = data.get('profiles')
    context_id = data.get('context')
    max_depth = data.get('max_depth')
    concurrent_users = data.get('concurrent_users', 1)

    # Get profile names for better naming
    profile_names = []
    if profile_ids:
        conn = get_db_connection()
        cur = conn.cursor()
        for profile_id in profile_ids:
            cur.execute("SELECT profile_name FROM profiles WHERE profile_id = %s", (profile_id,))
            result = cur.fetchone()
            if result:
                profile_names.append(result[0].replace(' ', '-').lower())
        cur.close()
        conn.close()
    elif experiment_mode == 'sequential_persona':
        # For sequential mode, extract profile IDs from persona_sequence
        persona_sequence = data.get('persona_sequence', [])
        if persona_sequence:
            conn = get_db_connection()
            cur = conn.cursor()
            for seq_item in persona_sequence:
                profile_id = seq_item.get('profile_id')
                if profile_id:
                    cur.execute("SELECT profile_name FROM profiles WHERE profile_id = %s", (profile_id,))
                    result = cur.fetchone()
                    if result:
                        profile_names.append(result[0].replace(' ', '-').lower())
            cur.close()
            conn.close()

    # Generate a descriptive experiment name
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if profile_names:
        profile_part = '-'.join(profile_names[:2])  # Use first 2 profiles max
        if len(profile_names) > 2:
            profile_part += f"-plus{len(profile_names)-2}"
    else:
        profile_part = "random"
    experiment_name = f"{experiment_mode}-{profile_part}-{timestamp}"

    # Load saved settings
    settings = load_settings()

    # Create the config file
    config = {
        'experiment': {
            'mode': experiment_mode,
            'max_depth': max_depth,
            'concurrent_users': concurrent_users
        },
        'database': {
            'url': f"postgresql://{os.environ.get('POSTGRES_USER')}:{os.environ.get('POSTGRES_PASSWORD')}@db:5432/{os.environ.get('POSTGRES_DB')}"
        },
        'llm': {
            'parse_recommendations': {
                'provider': 'openrouter',
                'model': 'mistralai/mistral-small-3.2-24b-instruct'
            },
            'choose_video': {
                'provider': 'openrouter',
                'model': 'mistralai/mistral-small-3.2-24b-instruct'
            },
            'check_relevance': {
                'provider': 'openrouter',
                'model': 'mistralai/mistral-small-3.2-24b-instruct'
            }
        },
        'api_keys': {
            'openai': os.environ.get('OPENAI_API_KEY', ''),
            'azure_openai_key': os.environ.get('AZURE_OPENAI_KEY', ''),
            'azure_openai_endpoint': os.environ.get('AZURE_OPENAI_ENDPOINT', ''),
            'openrouter': os.environ.get('OPENROUTER_API_KEY', '')
        },
        'scraping': {
            'parser_method': settings['parser_method'],
            'max_duration': settings['max_duration'],
            'max_depth': max_depth,
            'browser_type': 'chrome',
            'persona_filter_enabled': settings['persona_filter_enabled'],
            'persona_filter_seconds': settings['persona_filter_seconds'],
            'persona_filter_transcript_seconds': settings['persona_filter_transcript_seconds']
        },
        'selenium': {
            'hub_url': 'http://selenium-hub:4444'
        },
        'logging': {
            'level': 'INFO',
            'selenium_level': 'WARNING'
        }
    }

    if experiment_mode == 'single_persona':
        config['experiment']['profile_id'] = profile_ids[0]
    elif experiment_mode == 'mixed_persona':
        weights = data.get('weights')

        # Normalize weights to sum to 1.0
        weight_values = [float(w) for w in weights.values()]
        total_weight = sum(weight_values)

        if total_weight == 0:
            # If all weights are 0, distribute equally
            normalized_weights = {pid: 1.0 / len(weights) for pid in weights.keys()}
        else:
            # Normalize so they sum to 1.0
            normalized_weights = {pid: float(w) / total_weight for pid, w in weights.items()}

        config['experiment']['persona_mix'] = []
        for profile_id, weight in normalized_weights.items():
            config['experiment']['persona_mix'].append({'profile_id': int(profile_id), 'weight': weight})
    elif experiment_mode == 'sequential_persona':
        persona_sequence = data.get('persona_sequence')
        if not persona_sequence:
            return jsonify({"error": "persona_sequence is required for sequential_persona mode"}), 400
        config['experiment']['persona_sequence'] = persona_sequence
    
    if context_id:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT context_name FROM experiment_contexts WHERE context_id = %s", (context_id,))
        context_name = cur.fetchone()[0]
        cur.close()
        conn.close()
        config['experiment']['context_name'] = context_name

    # Use container paths
    config_file_path = f"/app/configs/{experiment_name}.yaml"
    with open(config_file_path, 'w') as f:
        yaml.dump(config, f)

    # Use Docker SDK to create and start the container directly
    client = docker.from_env()

    # Auto-detect scraper image
    image_name = get_scraper_image()

    container_name = f"scraper-{experiment_name}"

    # Prepare environment variables
    env_vars = {
        'DATABASE_URL': f"postgresql://{os.environ.get('POSTGRES_USER')}:{os.environ.get('POSTGRES_PASSWORD')}@youtube_research_db:5432/{os.environ.get('POSTGRES_DB')}",
        'POSTGRES_USER': os.environ.get('POSTGRES_USER'),
        'POSTGRES_PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
        'POSTGRES_DB': os.environ.get('POSTGRES_DB'),
        'OPENAI_API_KEY': os.environ.get('OPENAI_API_KEY', ''),
        'AZURE_OPENAI_KEY': os.environ.get('AZURE_OPENAI_KEY', ''),
        'AZURE_OPENAI_ENDPOINT': os.environ.get('AZURE_OPENAI_ENDPOINT', ''),
        'OPENROUTER_API_KEY': os.environ.get('OPENROUTER_API_KEY', ''),
        'SELENIUM_HUB_URL': 'http://selenium_hub:4444',
        'BROWSER_TYPE': os.environ.get('BROWSER_TYPE', ''),
        'CONFIG_FILE': '/app/experiment.yaml'
    }

    # Create and start the container
    # Use absolute path from host perspective - get from environment variable
    host_base_path = os.environ.get('HOST_PROJECT_PATH', os.getcwd())
    host_config_path = os.path.join(host_base_path, 'configs', f"{experiment_name}.yaml")

    # Prepare labels for container metadata
    labels = {
        'experiment.mode': experiment_mode,
        'experiment.profiles': ', '.join([name.replace('-', ' ').title() for name in profile_names]) if profile_names else 'Random',
        'experiment.max_depth': str(max_depth),
        'experiment.concurrent_users': str(concurrent_users)
    }

    container = client.containers.run(
        image=image_name,
        name=container_name,
        detach=True,
        environment=env_vars,
        labels=labels,
        volumes={
            host_config_path: {
                'bind': '/app/experiment.yaml',
                'mode': 'ro'
            }
        },
        network=get_docker_network()
    )

    return jsonify({"message": f"Experiment '{experiment_name}' started successfully!"})

@app.route('/api/status')
def get_status():
    client = docker.from_env()
    containers = client.containers.list(all=True)  # Include stopped containers
    experiments = []

    conn = get_db_connection()
    cur = conn.cursor()

    for container in containers:
        if container.name.startswith('scraper-'):
            # Get experiment name from container
            experiment_name = container.name.replace('scraper-', '')

            # Get labels from container
            labels = container.labels
            profiles = labels.get('experiment.profiles', 'N/A')
            max_depth = int(labels.get('experiment.max_depth', 0))
            concurrent_users = int(labels.get('experiment.concurrent_users', 1))

            if max_depth > 0:
                try:
                    # Get ALL sessions for this specific container
                    container_created = container.attrs['Created']

                    cur.execute("""
                        SELECT session_id FROM sessions
                        WHERE start_time >= (TIMESTAMP %s - INTERVAL '30 seconds')
                          AND start_time <= (TIMESTAMP %s + INTERVAL '60 seconds')
                        ORDER BY start_time ASC
                    """, (container_created, container_created))

                    sessions = cur.fetchall()
                    session_ids = [s[0] for s in sessions[:concurrent_users]]

                    # Get active Selenium nodes for this container
                    active_nodes = []
                    if container.status == 'running':
                        try:
                            for node_num in range(1, 12):
                                try:
                                    node_container = client.containers.get(f'selenium_node_{node_num}')
                                    result = node_container.exec_run(
                                        'sh -c "ps aux | grep -i chromium | grep -v grep | grep -v java"',
                                        demux=False
                                    )
                                    if result.exit_code == 0 and result.output and result.output.strip():
                                        active_nodes.append(node_num)
                                except Exception:
                                    continue
                        except Exception as e:
                            app.logger.warning(f"Could not detect active browser nodes: {e}")

                    # Create one entry per session/user
                    for idx, session_id in enumerate(session_ids):
                        # Count context phase videos
                        cur.execute("""
                            SELECT COUNT(DISTINCT source_video_id)
                            FROM recommendation_log
                            WHERE session_id = %s AND was_during_context = true
                        """, (session_id,))
                        context_count = cur.fetchone()[0]

                        # Count persona phase videos
                        cur.execute("""
                            SELECT COUNT(*) FROM recommendation_log
                            WHERE session_id = %s AND was_selected = true AND was_during_context = false
                        """, (session_id,))
                        persona_count = cur.fetchone()[0]

                        # Determine phase for this session
                        cur.execute("""
                            SELECT was_during_context FROM recommendation_log
                            WHERE session_id = %s
                            ORDER BY depth DESC LIMIT 1
                        """, (session_id,))
                        phase_result = cur.fetchone()

                        progress = 0
                        phase = 'Initializing'

                        if phase_result:
                            is_context = phase_result[0]
                            if is_context:
                                phase = f'Context Phase ({context_count}/10)'
                            else:
                                phase = f'Persona Phase ({persona_count}/{max_depth - 10})'

                            # Calculate progress
                            video_count = context_count + persona_count
                            progress = min(100, int((video_count / max_depth) * 100))

                        # Assign view URL from active nodes
                        view_url = None
                        if idx < len(active_nodes) and container.status == 'running':
                            vnc_host = get_vnc_host()
                            view_url = f'http://{vnc_host}:{7900 + active_nodes[idx]}'

                        # Create user-specific name
                        user_name = f"{experiment_name}"
                        if concurrent_users > 1:
                            user_name += f" - User {idx + 1}"

                        experiments.append({
                            'name': user_name,
                            'profiles': profiles,
                            'status': container.status,
                            'progress': progress,
                            'phase': phase,
                            'view_url': view_url,
                            'concurrent_users': concurrent_users,
                            'user_id': idx + 1,
                            'session_id': session_id,
                            'container_name': container.name
                        })

                except Exception as e:
                    app.logger.warning(f"Could not calculate progress: {e}")
                    conn.rollback()

                    # Fallback: show at least the container as one entry
                    experiments.append({
                        'name': experiment_name,
                        'profiles': profiles,
                        'status': container.status,
                        'progress': 0,
                        'phase': 'Initializing',
                        'view_url': None,
                        'concurrent_users': concurrent_users,
                        'user_id': 1,
                        'session_id': None,
                        'container_name': container.name
                    })
            else:
                # No max_depth, just show basic container info
                experiments.append({
                    'name': experiment_name,
                    'profiles': profiles,
                    'status': container.status,
                    'progress': 0,
                    'phase': 'N/A',
                    'view_url': None,
                    'concurrent_users': concurrent_users,
                    'user_id': 1,
                    'session_id': None,
                    'container_name': container.name
                })

    cur.close()
    conn.close()
    return jsonify(experiments)

@app.route('/api/clear-experiments', methods=['POST'])
def clear_experiments():
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True)
        removed_count = 0

        for container in containers:
            if container.name.startswith('scraper-') and container.status == 'exited':
                container.remove()
                removed_count += 1

        return jsonify({"message": f"Cleared {removed_count} exited experiment(s)"})
    except Exception as e:
        app.logger.error(f"Error clearing experiments: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stop-experiment/<experiment_name>', methods=['POST'])
def stop_experiment(experiment_name):
    try:
        client = docker.from_env()
        container_name = f"scraper-{experiment_name}"

        try:
            container = client.containers.get(container_name)
            if container.status == 'running':
                container.stop(timeout=10)
                return jsonify({"message": f"Experiment '{experiment_name}' stopped successfully"})
            else:
                return jsonify({"message": f"Experiment '{experiment_name}' is not running"}), 400
        except docker.errors.NotFound:
            return jsonify({"error": f"Experiment '{experiment_name}' not found"}), 404
    except Exception as e:
        app.logger.error(f"Error stopping experiment: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/add-profile', methods=['POST'])
def add_profile():
    try:
        data = request.json
        profile_name = data.get('name')
        persona_description = data.get('description')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO profiles (profile_name, persona_description) VALUES (%s, %s)", (profile_name, persona_description))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Persona added successfully!"})
    except Exception as e:
        app.logger.error(f"Error adding profile: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/add-context', methods=['POST'])
def add_context():
    try:
        data = request.json
        context_name = data.get('name')
        description = data.get('description')
        video_ids = [v.strip() for v in data.get('videos').split(',')]

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO experiment_contexts (context_name, description, video_ids) VALUES (%s, %s, %s)", (context_name, description, video_ids))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Context added successfully!"})
    except Exception as e:
        app.logger.error(f"Error adding context: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/database/table/<table_name>', methods=['GET'])
def get_table_data(table_name):
    """Get data from a specific table."""
    # Whitelist allowed tables for security
    allowed_tables = [
        'sessions', 'videos', 'recommendation_log', 'profiles',
        'experiment_contexts', 'persona_filter_log'
    ]

    if table_name not in allowed_tables:
        return jsonify({"error": "Invalid table name"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Get column names
        cur.execute(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        columns = [row[0] for row in cur.fetchall()]

        # Get row count
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_rows = cur.fetchone()[0]

        # Get data (last 100 rows, ordered by first column if possible)
        cur.execute(f"SELECT * FROM {table_name} ORDER BY {columns[0]} DESC LIMIT 100")
        rows = cur.fetchall()

        # Convert rows to list of dicts
        data = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                # Convert special types to strings for JSON serialization
                if isinstance(value, (dict, list)):
                    row_dict[col] = str(value)
                else:
                    row_dict[col] = value
            data.append(row_dict)

        cur.close()
        conn.close()

        return jsonify({
            "table": table_name,
            "columns": columns,
            "data": data,
            "total_rows": total_rows,
            "showing": len(data)
        })
    except Exception as e:
        app.logger.error(f"Error fetching table data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get current settings."""
    try:
        settings = load_settings()
        return jsonify(settings)
    except Exception as e:
        app.logger.error(f"Error getting settings: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Save new settings."""
    try:
        data = request.json
        settings = {
            'max_duration': int(data.get('max_duration', 300)),
            'parser_method': data.get('parser_method', 'bs'),
            'persona_filter_enabled': bool(data.get('persona_filter_enabled', True)),
            'persona_filter_seconds': int(data.get('persona_filter_seconds', 60)),
            'persona_filter_transcript_seconds': int(data.get('persona_filter_transcript_seconds', 120))
        }

        if save_settings(settings):
            return jsonify({"message": "Settings saved successfully!", "settings": settings})
        else:
            return jsonify({"error": "Failed to save settings"}), 500
    except Exception as e:
        app.logger.error(f"Error saving settings: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)




