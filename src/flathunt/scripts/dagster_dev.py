import os


def main() -> None:
    os.execvp("dagster", ["dagster", "dev", "-m", "flathunt.definitions"])


if __name__ == "__main__":
    main()
