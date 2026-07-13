"""Allow running the CLI as ``python3 -m vam`` (PATH-independent)."""
from .cli import main

if __name__ == "__main__":
    main()
