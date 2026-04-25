"""Launch Dagster UI in development mode."""

import os


def main() -> None:
    """Execute the Dagster dev command with flathunt definitions."""
    os.execvp("dagster", ["dagster", "dev", "-m", "flathunt.definitions"])


if __name__ == "__main__":
    main()
