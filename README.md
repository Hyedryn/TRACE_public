# YouTube Algorithm Analysis Engine

This project provides a scalable and automated framework for studying the YouTube recommendation algorithm. It uses persona-driven bots to simulate user journeys, log recommendation data, and enrich it with detailed video metadata for in-depth analysis.

## Table of Contents

-   [Features](#features)
-   [Architecture](#architecture)
-   [Prerequisites](#prerequisites)
-   [Project Setup](#project-setup)
    -   [Step 1: Configure Core Secrets (.env)](#step-1-configure-core-secrets-env)
    -   [Step 2: Manage Research Assets](#step-2-manage-research-assets)
    -   [Step 3: Define Your Experiment (configs/*.yaml)](#step-3-define-your-experiment-configsyaml)
-   [Running an Experiment](#running-an-experiment)
    -   [Step 1: Start Core Infrastructure](#step-1-start-core-infrastructure)
    -   [Step 2: Add a Scraper Service to docker-compose.yml](#step-2-add-a-scraper-service-to-docker-composeyml)
    -   [Step 3: Launch the Scraper](#step-3-launch-the-scraper)
    -   [Step 4: Stopping the Application](#step-4-stopping-the-application)
-   [Database Schema](#database-schema)
-   [How It Works](#how-it-works)

## Features

-   🔬 **Advanced Experiment Design:** Configure complex research scenarios—such as mixing personas, A/B testing, or simulating changing interests—directly in a clean YAML file.
-   🔄 **Reproducible Runs:** Each scraper session logs the *exact* configuration that was used, ensuring that every run is fully traceable and reproducible.
-   📊 **Baseline Comparison:** A built-in "random choice" mode allows you to establish a crucial baseline for algorithmic behavior, free from any persona influence.
-   🧩 **Modular Research Assets:** Personas and video "contexts" are stored in the database as reusable components that can be mixed and matched across different experiments.
-   **Scalable Scraping:** Run multiple, isolated scraper instances simultaneously, each executing a different experiment configuration.
-   **Automated Data Enrichment:** A background worker fetches detailed video metadata, transcripts, and statistics using the YouTube Data API.
-   **Dockerized Environment:** Fully containerized for easy setup, consistent execution, and scalability.
- **Flexible Parsing:** Choose between a fast, robust BeautifulSoup-based parser (default) or a more powerful LLM-based parser for extracting video recommendations.

## Architecture

The system is composed of several services orchestrated by Docker Compose:

1.  **`db` (PostgreSQL):** The central database that stores all collected data, including research assets (profiles, contexts) and results (sessions, videos, recommendations).
2.  **`selenium-hub` and `selenium-node-*`:** A Selenium Grid setup that allows multiple scrapers to run in parallel. The `hub` routes commands to one or more `node` containers, each providing an isolated Chrome browser instance.
3.  **`enrichment_worker`:** A background service that continuously polls the database for new videos and enriches them with metadata (title, description, transcript, etc.) from the YouTube API.
4.  **`scraper-*` Services:** Individual scraper bots. Each service runs an independent scraping session for a specific user profile, connecting to the `selenium-hub` to perform its tasks.

```
+--------------------------+      +--------------------------+
|   Scraper (Profile 1)    |----->|                          |
+--------------------------+      |      Selenium Hub        |      +--------------------------+
                                  |                          |----->|      YouTube.com         |
+--------------------------+      +--------------------------+      +--------------------------+
|   Scraper (Profile 2)    |----->|                          |
+--------------------------+      |    (Routes to Nodes)     |
                                  +-------------+------------+
                                                |
                                                | (DB Operations)
                                                v
+--------------------------+      +--------------------------+      +--------------------------+
|    Enrichment Worker     |----->|      PostgreSQL DB       |<---->|      YouTube API         |
+--------------------------+      +--------------------------+      +--------------------------+
```

## Prerequisites

- [Docker](https://www.docker.com/get-started) and `docker-compose` must be installed on your system.

## Project Setup

Setting up the project involves three key stages: configuring secrets, defining your research assets, and creating an experiment file.

### Step 1: Configure Core Secrets (.env)

The `.env` file in the project root is now used **only for secrets** like API keys and database credentials. All experimental parameters are defined in dedicated config files.

1.  Create a file named `.env`.
2.  Add your credentials. At a minimum, you will need:

    ```env
    # PostgreSQL Credentials
    POSTGRES_USER=your_db_user
    POSTGRES_PASSWORD=your_db_password
    POSTGRES_DB=youtube_research

    # YouTube Data API Key (for the enrichment worker)
    YOUTUBE_API_KEY=your_youtube_api_key

    # API Key for your chosen LLM Provider (e.g., OpenRouter)
    OPENROUTER_API_KEY=your_openrouter_api_key
    ```

### Step 2: Manage Research Assets

Personas and video contexts are reusable assets stored in the database. You manage them with simple command-line scripts.

#### Managing Personas (`scripts/add_profile.py`)

A "profile" or "persona" is a detailed text description of a user type.

**Prerequisites:**

1.  The core infrastructure (specifically the `db` service) must be running:
    ```bash
    docker-compose up -d db
    ```
2.  You need to install the script's dependencies:
    ```bash
    pip install -r scripts/requirements.txt
    ```
    
**Usage:**

```bash
python scripts/add_profile.py --name "News Junkie" --desc "A user who is highly engaged with current events, political commentary, and breaking news from a variety of sources."
```

The script will output the new `profile_id`, which you will use in your experiment config files.

#### Managing Contexts (`scripts/add_context.py`)

A "context" is a named, reusable list of YouTube video IDs. It's used to prime the YouTube algorithm with an initial viewing history before the main experiment begins.

**Prerequisites:**

1.  The core infrastructure (specifically the `db` service) must be running:
    ```bash
    docker-compose up -d db
    ```
2.  You need to install the script's dependencies:
    ```bash
    pip install -r scripts/requirements.txt
    ```
    
**Usage:**

```bash
python scripts/add_context.py --name "Initial News Context" --desc "A mix of center-left and center-right news reports to establish a general political interest." --videos video_id_1 video_id_2
```

### Step 3: Define Your Experiment (configs/*.yaml)

This is where you bring your assets together. In the `configs/` directory, create a YAML file for each experiment you want to run. This file is a complete "recipe" for a scraper's journey.

**Example: `configs/mixed-political-news-experiment.yaml`**

```yaml
# This experiment simulates a user who watches both pro-Israel and pro-Palestine content.
experiment:
  # 1. Start with a reusable context from the database.
  context_name: "General Middle East News Context"

  # 2. Define the behavior for the main part of the journey.
  mode: "mixed_persona"
  
  # 3. Specify the parameters for the chosen mode.
  persona_mix:
    - profile_id: 2  # Corresponds to 'Pro-Israel' persona
      weight: 0.5    # 50% chance to be chosen at each step
    - profile_id: 3  # Corresponds to 'Pro-Palestine' persona
      weight: 0.5    # 50% chance

# Other parameters for this specific run
scraping:
  max_depth: 100
  # ... other scraping settings

database:
  url: "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"

# ... llm, api_keys, etc.
```


## Running an Experiment

The application supports **two modes of operation**: a user-friendly **GUI Dashboard** (recommended) and a **Manual Docker Compose** method for advanced users.

---

## Mode 1: GUI Dashboard (Recommended)

The GUI provides a web-based interface for managing all aspects of your experiments without editing configuration files or docker-compose.yml manually.

### Starting the GUI

1. **Start all services** including the GUI dashboard:

```bash
docker-compose up -d --build
```

This will start:
- PostgreSQL database (`db`)
- Selenium Hub and Node(s) for browser automation
- Enrichment worker for metadata collection
- **GUI Dashboard** on port 5001

2. **Access the dashboard** in your web browser:

```
http://localhost:5001
```

### Using the GUI Dashboard

The dashboard provides a complete interface for managing experiments:

#### 1. **Adding Personas**

Before running experiments, you need to define personas (user profiles):

- Click **"Add Persona to Database"** button
- Enter a **Persona Name** (e.g., "Tech Enthusiast", "News Junkie")
- Enter a **Persona Description** - a detailed text description of the user's interests, demographics, and viewing habits
- Click **"Save Persona"**

The persona is now stored in the database and can be reused across multiple experiments.

#### 2. **Adding Contexts**

Contexts are reusable sets of videos used to prime the YouTube algorithm before the main experiment:

- Click **"Add Context"** button
- Enter a **Context Name** (e.g., "Tech News Context")
- Enter a **Description** (optional)
- Enter **Video IDs** separated by commas (e.g., `dQw4w9WgXcQ, jNQXAC9IVRw`)
- Click **"Save Context"**

#### 3. **Configuring and Starting Experiments**

The GUI supports four experiment modes:

##### 🎯 **Single Persona Mode**
- The bot consistently uses one persona throughout the entire experiment
- **Setup:** Select one profile from the dropdown menu
- **Use case:** Study how YouTube recommendations evolve for a specific user type

##### 🎲 **Mixed Persona Mode**
- The bot randomly switches between multiple personas at each decision step
- **Setup:**
  1. Enter the number of personas you want to mix
  2. Click **"Generate Selectors"**
  3. Select a persona for each slot
  4. Assign a **weight** to each persona (determines probability of selection)
- **Use case:** Simulate a user with diverse or conflicting interests

##### 📊 **Sequential Persona Mode**
- The bot cycles through personas in order, one after another
- **Setup:**
  1. Enter the number of personas
  2. Click **"Generate Selectors"**
  3. Select personas in the order you want them executed
- **Use case:** Study how recommendation patterns change when a user's interests evolve over time

##### 🎰 **Random Choice Mode**
- The bot randomly selects videos from recommendations without using any persona logic
- **Setup:** No persona selection required
- **Use case:** Establish a baseline for comparison - pure algorithmic recommendations without persona influence

##### Common Configuration:
- **Context:** Select a context to prime the algorithm (required)
- **Max Depth:** Number of videos to watch in the experiment (e.g., 50)
- **Concurrent Users:** Number of parallel user sessions to run (default: 1)

Click **"Start Experiment"** to launch your experiment.

#### 4. **Monitoring Experiments**

The **Running Experiments** panel shows real-time status:

- **Experiment Name:** Auto-generated based on mode and timestamp
- **Profile(s):** Which persona(s) are being used
- **Status:** Running or Exited
- **Phase:** Current phase (Context Phase or Persona Phase) with progress
- **Progress:** Percentage complete (videos watched / max depth)
- **Actions:**
  - **Watch:** View the live browser session via VNC
  - **Stop:** Terminate a running experiment

The status refreshes automatically every 5 seconds.

#### 5. **Settings**

Click the **"Settings"** button in the top-right to configure scraping behavior:

- **Max Duration:** Maximum time (seconds) to watch each video
- **Parser Method:** Choose between BeautifulSoup (fast) or Selenium (slower but more accurate)
- **Persona Filter:** Enable/disable filtering of irrelevant videos
  - **Persona Filter Seconds:** Watch time for filtered videos
  - **Transcript Analysis Seconds:** Amount of transcript to analyze for relevance

These settings apply to all newly started experiments.

#### 6. **Database Viewer**

Click **"Database"** to browse all stored data:
- View tables: sessions, videos, recommendation_log, profiles, contexts, persona_filter_log
- Inspect the last 100 rows of any table
- Useful for debugging and data verification

### Cleaning Up

To remove completed experiments from the dashboard:
- Click **"Clear Exited"** to remove all stopped experiments from the list

To stop all services:
```bash
docker-compose down
```

---

## Mode 2: Manual Docker Compose (Advanced)

For advanced users who want fine-grained control or need to script experiments, you can manually configure and launch scrapers.

### Step 1: Start Core Infrastructure

First, launch the essential background services. The `--build` flag ensures the images are up-to-date, and `-d` runs them in detached mode.

Open a terminal in the project root and run:

```bash
docker-compose up -d --build db selenium-hub selenium-node-1 selenium-node-2 enrichment_worker
```

### Step 2: Add a Scraper Service to docker-compose.yml

Define a new service for your experiment. This involves mounting your experiment's config file into the container and telling the scraper to use it.

**Example:**

```yaml
# In docker-compose.yml
services:
  # ... (db, selenium-hub, etc.)

  # Add a new service for your experiment
  scraper-mixed-political:
    <<: *scraper-defaults
    container_name: scraper_mixed_political
    volumes:
      # Mount your specific experiment file into the container
      - ./configs/mixed-political-news-experiment.yaml:/app/experiment.yaml
    environment:
      <<: *scraper-env
      # Tell the scraper which config file to use
      CONFIG_FILE: /app/experiment.yaml
```

### Step 3: Launch the Scraper

With the core services running, launch your newly defined scraper service in a new terminal.

```bash
docker-compose up --build scraper-mixed-political
```

You can repeat steps 2 and 3 to run multiple, different experiments simultaneously.

### Step 4: Stopping the Application

To stop all running services (including the core infrastructure and all scrapers), run the following command from any of the terminals:

```bash
docker-compose down
```

This will gracefully stop and remove all containers associated with the project.


## Database Schema

The PostgreSQL database (`init.sql`) defines the core structure for data storage:

-   **`profiles`**: Stores the user personas (`profile_id`, `profile_name`, `persona_description`).
-   **`experiment_contexts`**: Stores the reusable, named lists of video IDs for context-setting.
-   **`sessions`**: Tracks each individual experiment. The `experiment_config` (JSONB) column stores the *exact* YAML configuration used for the run, ensuring perfect reproducibility.
-   **`videos`**: A central repository for every unique video encountered, enriched with metadata.
-   **`recommendation_log`**: The most critical table, logging every recommended video, its rank, and whether the bot selected it.

## How It Works

1.  **Initialization:** A scraper container starts. It reads the `CONFIG_FILE` environment variable to load its unique YAML experiment file.
2.  **Context Phase:** The scraper checks for a `context_name` or `context_video_ids` in its configuration. If found, it "watches" these videos in sequence to establish a baseline viewing history.
3.  **Experiment Phase:** The scraper enters its main loop. At **each step**, it consults the `experiment.mode` to determine its decision-making logic (e.g., pick a persona based on weights, choose randomly, etc.).
4.  **Data Logging:** All recommendations are logged. The chosen video's log entry is enriched with data about *how* and *why* it was chosen (the choice method and persona ID used for that specific step).
5.  **Enrichment:** The `enrichment_worker` runs in the background, continually polling the database for new video IDs and enriching them with full metadata from the YouTube API.