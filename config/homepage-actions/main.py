#!/usr/bin/env python3
"""Bootstrap for the homepage-actions API (container entrypoint: python main.py)."""

if __name__ == "__main__":
    from server import run_server

    run_server()
