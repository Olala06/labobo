"""Compatibility entry point: launch the local standard-library web UI."""
from genomic_detective.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["serve", "--open"]))
