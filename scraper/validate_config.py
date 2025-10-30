#!/usr/bin/env python3
"""Configuration validation script for the YouTube scraper."""

import sys
from pydantic import ValidationError
from config import get_config


def main():
    """Validate the current configuration."""
    print("🔧 YouTube Scraper Configuration Validator\n")

    try:
        # Load configuration. Pydantic's validation runs automatically here.
        config = get_config()
        print("✅ Configuration loaded and structurally valid.")

        # --- CORRECTED: Display the new experiment configuration ---
        print("\n🔬 Experiment Configuration:")
        exp = config.experiment
        print(f"  Mode: {exp.mode}")

        # Display context details
        if exp.context_name:
            print(f"  Context: From database (Name: '{exp.context_name}')")
        elif exp.context_video_ids:
            print(f"  Context: Direct list ({len(exp.context_video_ids)} videos)")
        else:
            print("  Context: No context phase configured")

        # Display mode-specific details
        if exp.mode == 'single_persona':
            print(f"  Persona Profile ID: {exp.profile_id}")
        elif exp.mode == 'mixed_persona':
            print("  Persona Mix:")
            for mix in exp.persona_mix:
                print(f"    - Profile {mix.profile_id}: {mix.weight * 100:.0f}% chance")
        elif exp.mode == 'sequential_persona':
            print("  Persona Sequence:")
            for seq in exp.persona_sequence:
                print(f"    - Profile {seq.profile_id}: runs for {seq.steps} steps")

        # Display Database URL
        print("\n📋 Database Configuration:")
        db_url = config.database.url
        print(f"  Database URL: {db_url[:50]}..." if len(db_url) > 50 else f"  Database URL: {db_url}")

        print("\n🤖 LLM Configuration:")
        llm_tasks = [
            ("Parse Recommendations", config.llm.parse_recommendations),
            ("Choose Video", config.llm.choose_video),
            ("Check Relevance", config.llm.check_relevance)
        ]

        for task_name, task_config in llm_tasks:
            if task_config:
                print(f"  {task_name}: {task_config.provider} ({task_config.model})")
            else:
                print(f"  {task_name}: Not configured")

        print("\n⚙️ Scraping Configuration:")
        print(f"  Parser Method: {config.scraping.parser_method}")
        print(f"  Max Duration: {config.scraping.max_duration}s")
        print(f"  Max Depth: {config.scraping.max_depth}")
        print(f"  Browser: {config.scraping.browser_type}")
        persona_status = "enabled" if config.scraping.persona_filter_enabled else "disabled"
        print(f"  Persona Filter: {persona_status}")
        if config.scraping.persona_filter_enabled:
            print(f"    Filter Duration: {config.scraping.persona_filter_seconds}s")
            print(f"    Transcript Duration: {config.scraping.persona_filter_transcript_seconds}s")

        print("\n🔑 API Keys Configuration:")
        api_keys = [
            ("OpenAI", config.api_keys.openai),
            ("Azure OpenAI Key", config.api_keys.azure_openai_key),
            ("Azure OpenAI Endpoint", config.api_keys.azure_openai_endpoint),
            ("OpenRouter", config.api_keys.openrouter)
        ]
        for key_name, key_value in api_keys:
            status = "✅ Set" if key_value else "❌ Not set"
            print(f"  {key_name}: {status}")

        print("\n🌐 Network Configuration:")
        selenium_hub = config.selenium.hub_url or "local"
        print(f"  Selenium Hub: {selenium_hub}")

        print("\n📊 Logging Configuration:")
        print(f"  Log Level: {config.logging.level}")
        print(f"  Selenium Log Level: {config.logging.selenium_level}")

        # --- CORRECTED: Use the existing API key validation method ---
        print("\n🔍 Validation Results:")
        # This method now primarily checks for missing API keys.
        issues = config.validate_configuration()

        if not issues:
            print("✅ All validation checks passed!")
            print("\n🎉 Configuration is ready for use!")
            return 0

        print("❌ Configuration issues found:")
        for issue in issues:
            print(f"  - {issue}")

        print("\n💡 To fix these issues, check your .env or config.yaml file.")
        return 1

    # --- CORRECTED: Provide more specific error handling for validation ---
    except ValidationError as e:
        print(f"\n❌ Configuration validation failed! Pydantic found the following errors:")
        print(e)
        print("\n💡 To fix these issues:")
        print("  1. Carefully check your config.yaml for typos or incorrect structures.")
        print("  2. Ensure you have provided the required fields for your chosen experiment 'mode'.")
        print("  3. See config.example.yaml for reference.")
        return 1
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")
        print("\n💡 Troubleshooting:")
        print("  - Check that all required environment variables are set if not using a config file.")
        print("  - Verify your config file syntax (YAML/JSON).")
        return 1


if __name__ == "__main__":
    sys.exit(main())

