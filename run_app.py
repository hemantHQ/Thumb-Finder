"""Run Thumb Finder directly from source for local debugging (no EXE build)."""
import sys

from thumb_finder.app import main

if __name__ == "__main__":
    raise SystemExit(main())
