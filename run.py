#!/usr/bin/env python3
"""
Copied from _templates/run.py -- don't edit this file itself; extend
toolkit/cli.py if you need a new flag. See TOOLKIT.md item 5.

    python run.py evaluate --instance 10 --solution solution/generate.py --note "..."
    python run.py verify --instance 10 --artifact artifact.json
"""
import sys

from toolkit.cli import main

if __name__ == "__main__":
    sys.exit(main())
