# YouTube Scraper

## Architecture Overview

The scraper is organized into focused modules:

### Core Modules

-   **`config.py`** - Configuration models and validation for experiments.
-   **`database.py`** - Database operations and connection management.
-   **`browser_manager.py`** - Browser setup, cookie handling, and DOM interactions.
-   **`video_parser.py`** - Video duration parsing and watching functionality.
-   **`recommendation_parser.py`** - HTML parsing for recommendations (LLM & BeautifulSoup).
-   **`llm_services.py`** - LLM service integrations and structured API calls.
-   **`scraper_main.py`** - Main orchestration logic for running experiments.

## Key Benefits

1.  **Separation of Concerns** - Each module has a single, well-defined responsibility.
2.  **Testability** - Individual components can be tested in isolation.
3.  **Maintainability** - Changes to specific functionality are localized.
4.  **Code Reusability** - Modules can be imported and used independently.
5.  **🎯 Powerful Configuration** - Define complex experiments in a clean, readable YAML format.
6.  **🔒 Type Safety** - Pydantic validation ensures the correctness of all configurations before a run.
7.  **🚀 Modern LLM Integration** - Structured output using Pydantic models for reliable choices.
8.  **🔬 Flexible Experiment Design** - Define complex research scenarios directly in the configuration, including mixing personas, running random benchmarks, and sequencing persona behaviors.

## Configuration

The scraper uses a powerful and clean configuration system centered around a single `config.yaml` file. This file defines the entire behavior of a scraper run, from the initial context to the persona-driven choices.

### 🔬 **The Experiment Block**

The core of the system is the `experiment` block in your `config.yaml`. It defines the two main phases of a scraper run:

1.  **Context Phase:** The initial set of videos watched to prime the YouTube algorithm. This is defined using either a reusable `context_name` from the database or a direct `context_video_ids` list.
2.  **Persona Phase:** The main journey where the scraper makes choices based on a defined `mode`.

### **Complete `config.yaml` Example**

This example demonstrates a "mixed persona" experiment that uses a pre-defined context from the database.

```yaml
# In config.yaml

# The experiment block defines the scraper's entire journey.
experiment:
  # Option 1 (Recommended): Use a named, reusable context from the database.
  # This context must be added first using `scripts/add_context.py`.
  context_name: "Initial Tech Exploration"

  # Option 2 (For quick tests): Provide a direct list of video IDs.
  # context_video_ids: ["dQw4w9WgXcQ", "y6120QOlsfU"]

  # The mode for the main navigation phase.
  mode: "mixed_persona"
  
  # Configuration for the chosen mode.
  persona_mix:
    - profile_id: 1
      weight: 0.7  # 70% chance to use the 'Tech Enthusiast' persona
    - profile_id: 2
      weight: 0.3  # 30% chance to use another persona

database:
  url: "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"

llm:
  choose_video:
    provider: "openrouter" 
    model: "mistralai/mistral-small"
  check_relevance:
    provider: "openrouter"
    model: "mistralai/mistral-small"

# API keys are best loaded from a .env file using substitution.
api_keys:
  openrouter: "${OPENROUTER_API_KEY}"

scraping:
  parser_method: "bs"
  max_duration: 300
  max_depth: 50
  browser_type: "chrome"
```

### **Experiment Modes**

You can configure the `mode` in the `experiment` block to achieve different research goals.

#### 1. Single Persona (`single_persona`)

This is the classic mode where the scraper consistently acts as one user.

```yaml
experiment:
  context_name: "Initial News Context"
  mode: "single_persona"
  profile_id: 3 # The ID of the persona to use for every choice.
```

#### 2. Mixed Persona (`mixed_persona`)

At each step, the scraper randomly chooses a persona based on the defined weights. This is useful for simulating a user with multiple interests.

```yaml
experiment:
  context_name: "General Interest Context"
  mode: "mixed_persona"
  persona_mix:
    - profile_id: 1
      weight: 0.6 # 60% chance
    - profile_id: 2
      weight: 0.4 # 40% chance
```

#### 3. Sequential Persona (`sequential_persona`)

The scraper acts as one persona for a set number of steps, then switches to another. This can simulate a user's interests changing over time.

```yaml
experiment:
  context_name: "Initial Tech Context"
  mode: "sequential_persona"
  persona_sequence:
    - profile_id: 1
      steps: 20  # Act as persona 1 for the first 20 video choices.
    - profile_id: 4
      steps: 30  # Then, switch to persona 4 for the next 30 choices.
```

#### 4. Random Choice (`random_choice`)

The scraper ignores all personas and chooses the next video completely at random. **This is critical for establishing a baseline** to measure the algorithm's behavior without persona-driven influence.

```yaml
experiment:
  context_name: "Initial Tech Context"
  mode: "random_choice"
  # No profile_id or persona mix is needed here.
```

### ✅ **Configuration Validation**

Before running a scraper, you can validate your `config.yaml` to catch any structural or logical errors:

```bash
python validate_config.py
```

## Database Operations

Database operations in `database.py` are designed for traceability:

-   Connection management with a robust connection pool.
-   Session creation now logs the entire `experiment` configuration.
-   **Logs the specific persona ID and choice method (`persona` or `random`) used for every single video selection**, enabling detailed and precise analysis.

## LLM Services

LLM interactions use structured output with Pydantic models for high reliability:

### Supported Providers

-   **OpenAI**
-   **Azure OpenAI**
-   **OpenRouter** (Recommended for model variety)

### Pydantic Models

-   `VideoRecommendation`: Structure for a single recommended video.
-   `RecommendationsList`: A list of recommendations.
-   `VideoChoice`: The LLM's decision on which video to watch next, with justification.
-   `RelevanceCheck`: The LLM's assessment of a video's relevance to a persona.
