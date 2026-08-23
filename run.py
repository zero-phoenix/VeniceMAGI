"""Lanzador de VeniceMAGI (punto de entrada del exe)."""
import asyncio
import sys

from vmagi.app import main

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
