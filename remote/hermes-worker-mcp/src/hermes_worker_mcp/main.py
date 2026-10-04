from __future__ import annotations
import logging
import uvicorn
from .server import app, settings

def main():
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    uvicorn.run(
        app,
        host=settings.tail_ip,
        port=settings.port,
        log_level=settings.log_level.lower(),
        server_header=False,
    )

if __name__ == "__main__":
    main()
