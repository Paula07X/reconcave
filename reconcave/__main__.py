"""Allows `python -m reconcave ...` as an alternative to installing the
console script or running `python -m reconcave.cli ...`."""

try:
    from .cli import main
except ImportError:
    # Launched directly as a bare script (e.g. an IDE's "Run" button picked
    # this file as the startup file) rather than as part of the package.
    # Patch sys.path with the project root and retry as an absolute import.
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from reconcave.cli import main

if __name__ == "__main__":
    main()
