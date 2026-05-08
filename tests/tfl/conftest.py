from pathlib import Path

import dotenv


def pytest_configure(config):
    env_file = Path(__file__).parents[2] / ".env"
    if env_file.exists():
        dotenv.load_dotenv(env_file)
