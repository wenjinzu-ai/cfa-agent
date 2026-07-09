from __future__ import annotations

import uvicorn

from src.common.settings import get_config


def main():
    config = get_config()
    uvicorn.run(
        "src.api.server:app",
        host=config.app.host,
        port=config.app.port,
        reload=config.app.debug,
    )


if __name__ == "__main__":
    main()