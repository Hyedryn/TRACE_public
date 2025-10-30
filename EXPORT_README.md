# Database Export Guide

This guide explains how to export the YouTube Research database for remote analysis.

## Export Formats

### CSV Export
- Creates separate CSV files for each table
- Ideal for analysis in Excel, R, or Python pandas
- Handles arrays and JSON fields by converting to strings

```cmd
python scripts/export_db.py --format csv --output exports/
```

This creates:
- `exports/videos.csv`
- `exports/sessions.csv`
- `exports/recommendation_log.csv`
- `exports/profiles.csv`
- etc.

### JSON Export
- Single JSON file with all table data
- Preserves data types and structure
- Great for programmatic analysis

```cmd
python scripts/export_db.py --format json --output youtube_data.json
```

### SQL Export
- Complete database dump with schema and data
- Can be imported into another PostgreSQL instance
- Requires `pg_dump` to be installed

```cmd
python scripts/export_db.py --format sql --output backup.sql
```

## Advanced Usage

### Export Specific Tables
```cmd
# Only export core analysis tables
python scripts/export_db.py --format csv --output core_data/ --tables videos,recommendation_log,sessions

# Export just video metadata
python scripts/export_db.py --format json --output videos.json --tables videos
```

### Custom Database Connection
```cmd
# Connect to different host/port
python scripts/export_db.py --format csv --output exports/ --host 192.168.1.100 --port 5433

# Use different credentials
python scripts/export_db.py --format json --output data.json --user analyst --password mypass
```

## Database Schema Overview

The main tables you'll want to analyze:

- **videos**: Core video metadata (title, description, channel, etc.)
- **recommendation_log**: Every recommendation received during scraping
- **sessions**: Individual bot journeys with configuration
- **profiles**: User personas used for scraping
- **persona_filter_logs**: Videos filtered by persona relevance

## Prerequisites

### Manual Setup
If you prefer manual setup:

```cmd
# Create virtual environment
python -m venv .venv

# Activate it (Windows)
.venv\Scripts\activate.bat

# Activate it (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r scripts/requirements.txt

# Run export directly
python scripts/export_db.py --format csv --output exports/
```

### SQL Export Requirements
For SQL exports, you need PostgreSQL client tools installed:

**Windows**: Download from https://www.postgresql.org/download/windows/
**Ubuntu/Debian**: `sudo apt-get install postgresql-client`
**Mac**: `brew install postgresql`

## Environment Configuration

The script reads database connection details from `.env`:

```env
POSTGRES_USER=yt_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=youtube_research
```

You can override these with command-line arguments if needed.

## Troubleshooting

### Connection Issues
- Ensure Docker containers are running: `docker-compose up -d`
- Check if database port 5432 is accessible
- Verify credentials in `.env` file

### Large Exports
- For large datasets, CSV format is most memory-efficient
- Consider exporting specific tables rather than all data
- JSON exports load everything into memory

## Example Analysis Workflows

### Python/Pandas Analysis
```python
import pandas as pd

# Load exported CSV data
videos = pd.read_csv('exports/videos.csv')
recommendations = pd.read_csv('exports/recommendation_log.csv')

# Analyze recommendation patterns
rec_stats = recommendations.groupby('source_video_id').size()
```

### R Analysis
```r
library(readr)

# Load data
videos <- read_csv("exports/videos.csv")
recommendations <- read_csv("exports/recommendation_log.csv")

# Analyze selection patterns
selection_rate <- recommendations %>%
  group_by(recommendation_source) %>%
  summarise(selection_rate = mean(was_selected))
```

## Support

For issues with the export script, check:
1. Database connection (can you connect with `docker exec -it youtube_research_db psql -U yt_user youtube_research`)
2. Python environment setup
3. Required dependencies installed
