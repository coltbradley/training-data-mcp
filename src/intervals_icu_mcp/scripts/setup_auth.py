"""Interactive authentication setup for Intervals.icu MCP."""

from pathlib import Path

from ..auth import update_env_key


def main():
    """Run the interactive API key setup."""
    print("=" * 60)
    print("Intervals.icu MCP - Authentication Setup")
    print("=" * 60)
    print()

    print("This script will help you configure authentication for Intervals.icu.")
    print()

    # Step 1: Get API key
    print("Step 1: Get your API Key")
    print("-" * 60)
    print("1. Go to https://intervals.icu/settings")
    print("2. Scroll down to the 'Developer' section")
    print("3. Click 'Create API Key' if you haven't already")
    print("4. Copy the API key")
    print()

    api_key = input("Enter your API key: ").strip()

    if not api_key:
        print("\n❌ Error: API key is required.")
        return

    # Step 2: Get athlete ID
    print()
    print("Step 2: Get your Athlete ID")
    print("-" * 60)
    print("Your athlete ID can be found in your profile URL.")
    print("Example: https://intervals.icu/athletes/i123456")
    print("The athlete ID would be: i123456")
    print()
    print("Alternatively, it's shown at the top of your settings page.")
    print()

    athlete_id = input("Enter your athlete ID (e.g., i123456): ").strip()

    if not athlete_id:
        print("\n❌ Error: Athlete ID is required.")
        return

    # Validate athlete ID format
    if not athlete_id.startswith("i"):
        print("\n⚠️  Warning: Athlete ID should start with 'i' (e.g., i123456)")
        confirm = input("Continue anyway? (y/n): ").strip().lower()
        if confirm != "y":
            return

    # Save to .env
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        print(f"\n📝 Updating existing .env file at: {env_path}")
    else:
        print(f"\n📝 Creating new .env file at: {env_path}")

    try:
        update_env_key(api_key, athlete_id)

        print("\n" + "=" * 60)
        print("✅ Success! Credentials saved to .env")
        print("=" * 60)
        print()
        print("Your Intervals.icu MCP server is now configured!")
        print()
        print("Next steps:")
        print("  1. Run the MCP server: intervals-icu-mcp")
        print("  2. Configure Claude Desktop to use this server")
        print()
        print("For Claude Desktop configuration, add this to your config:")
        print()
        print("{")
        print('  "mcpServers": {')
        print('    "intervals-icu": {')
        print('      "command": "intervals-icu-mcp"')
        print("    }")
        print("  }")
        print("}")
        print()

    except Exception as e:
        print(f"\n❌ Error saving credentials: {str(e)}")
        return

if __name__ == "__main__":
    main()
