# YouTube Recommendation Analysis

This directory contains the code for analyzing the YouTube recommendation data collected by the main scraping application. The primary goal is to compare recommendation patterns for different personas (e.g., "Pro-Palestine" vs. "Pro-Israel") and investigate the presence of recommendation loops or filter bubbles.

## Contents

- `analysis.py`: The main Python script for fetching data, performing analysis, and generating visualizations.
- `requirements.txt`: Lists the Python dependencies required to run the analysis.
- `Dockerfile`: Provides a containerized environment for reproducible analysis.

## Prerequisites

Before running the analysis, ensure the following:

1.  **Database is running:** The PostgreSQL database (`db` service) from the main `docker-compose.yml` must be up and accessible.
2.  **Profiles exist:** The specific user profiles you wish to analyze (e.g., "Pro-Palestine", "Pro-Israel") must have been created in the database using `scripts/add_profile.py`.
3.  **Data is collected:** Scraper bots for the respective profiles must have been run to populate the `recommendation_log` and `videos` tables in the database.

## Setup

To set up the analysis environment, you can either install the dependencies directly or use Docker.

### Option 1: Local Setup (Recommended for Development)

1.  Navigate to the `analysis` directory:
    ```bash
    cd analysis
    ```
2.  Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

### Option 2: Dockerized Setup (Recommended for Reproducibility)

1.  Navigate to the root of the project directory (where `docker-compose.yml` is located).
2.  Build the Docker image for the analysis service:
    ```bash
    docker build -t youtube-analysis ./analysis
    ```

## Usage

### Running the Analysis Locally

After setting up locally, simply run the Python script:

```bash
python analysis.py
```

### Running the Analysis with Docker

From the root of the project directory, run the Docker container. Ensure your PostgreSQL database is running and accessible (e.g., via `docker-compose up -d db`). The `--network host` flag allows the container to connect to your host's network, enabling it to reach the database running on `localhost`.

```bash
docker run --network host youtube-analysis
```

## Output

The `analysis.py` script will print various analysis results to the console. Additionally, it will generate image files (e.g., `.png`) for visualizations in the `analysis` directory. For example, `channel_diversity.png` will be created to compare the diversity of recommended channels between profiles.

## Customization

You can modify `analysis.py` to add more sophisticated analysis, generate different types of plots, or focus on specific aspects of the recommendation data relevant to your research questions.