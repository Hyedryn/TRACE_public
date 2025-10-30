# Setup Guide - Running on Any Computer

This guide explains how to run the YouTube Research Platform on a different computer or remote server.

## Prerequisites

- Docker and Docker Compose installed
- Git (to clone the repository)
- Ports available: 5001 (GUI), 5432 (PostgreSQL), 4444 (Selenium Hub), 7901-7911 (VNC)

## Step-by-Step Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd YoutubeStats  # Or whatever you name the directory
```

**Note**: The directory name doesn't matter - the system auto-detects Docker network and image names.

### 2. Configure Environment Variables

Copy the example environment file and edit it:

```bash
cp .env.example .env
nano .env  # or use your preferred editor
```

**Required settings:**
- `POSTGRES_PASSWORD`: Set a secure database password
- `OPENROUTER_API_KEY`: Your OpenRouter API key (or other LLM provider)
- `YOUTUBE_API_KEY`: Your YouTube Data API v3 key

**Optional but recommended:**
- `VNC_HOST`: If running on a remote server, set this to your server's IP or hostname

### 3. Configure VNC Access

**For local development (same computer):**
```bash
# In .env file:
VNC_HOST=localhost
```

**For remote server access:**
```bash
# In .env file - replace with your server's IP or hostname:
VNC_HOST=192.168.1.100
# or
VNC_HOST=myserver.example.com
```

The "Watch" buttons in the GUI will use this hostname to generate VNC URLs like:
- `http://192.168.1.100:7901` (for User 1)
- `http://192.168.1.100:7902` (for User 2)
- etc.

### 4. Build and Start Services

```bash
# Build all images
docker-compose build

# Start all services
docker-compose up -d gui
```

This will automatically start:
- PostgreSQL database
- Selenium Hub
- 11 Selenium nodes (for concurrent browser sessions)
- Flask GUI application

### 5. Access the GUI

Open your browser to:
- Local: `http://localhost:5001`
- Remote: `http://<server-ip>:5001`

## Architecture Features

### Auto-Detection
The system automatically detects:
- **Docker network name** (based on your directory name)
- **Scraper image name** (finds any image with 'scraper' in the name)
- **VNC hostname** (from request or VNC_HOST environment variable)

This means you can:
- Clone to any directory name
- Run on any machine
- Access from anywhere

### Port Configuration

If default ports conflict on your system, you can change them in `docker-compose.yml`:

```yaml
gui:
  ports:
    - "5001:5001"  # Change left side to different port (e.g., "8080:5001")
```

## Remote Access Example

**Scenario**: Running on a server at `192.168.1.50`, accessing from laptop

1. **On the server**:
   ```bash
   # In .env
   VNC_HOST=192.168.1.50

   # Start services
   docker-compose up -d gui
   ```

2. **On your laptop**:
   - Open browser to `http://192.168.1.50:5001`
   - Start an experiment with 5 concurrent users
   - Click "Watch" on any user to view their browser at `http://192.168.1.50:7901` etc.

## Troubleshooting

### "Could not detect Docker network"
- Check GUI container logs: `docker logs gui`
- The system will fall back to `youtubestats_default`
- Usually auto-detection works; this is a non-critical warning

### "Could not detect scraper image"
- Run `docker images | grep scraper` to check if scraper image exists
- Build it with: `docker-compose build scraper-tech-enthusiast`

### VNC links not working
- Check `VNC_HOST` in `.env` matches your server's IP/hostname
- Ensure ports 7901-7911 are accessible from your client machine
- Check firewall settings if accessing remotely

## Files That Are Portable

✅ **These work anywhere:**
- All Python code
- Docker Compose configuration
- Database schemas

❌ **These are machine-specific:**
- `.env` file (contains your credentials)
- `configs/` directory (generated experiment configs)
- PostgreSQL data volume (database contents)

## Migration to New Machine

To move an existing setup:

1. **Export database** (optional, to keep data):
   ```bash
   docker exec youtube_research_db pg_dump -U yt_user youtube_research > backup.sql
   ```

2. **Copy files to new machine**:
   ```bash
   # Copy entire directory except .env
   rsync -av --exclude='.env' --exclude='configs/' YoutubeStats/ newmachine:YoutubeStats/
   ```

3. **On new machine**:
   ```bash
   cd YoutubeStats
   cp .env.example .env
   # Edit .env with your settings
   docker-compose up -d gui
   ```

4. **Import database** (optional):
   ```bash
   docker exec -i youtube_research_db psql -U yt_user youtube_research < backup.sql
   ```

## Security Notes

- Never commit `.env` to version control (already in `.gitignore`)
- Use strong passwords for `POSTGRES_PASSWORD`
- Restrict port access if running on public server
- VNC connections are unencrypted - use VPN or SSH tunnel for sensitive work
