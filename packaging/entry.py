"""PyInstaller 打包入口：talentforge.exe → 启动 FastAPI 服务并打开浏览器。

分发版（exe）只做一件事：起服务 + 自动开浏览器，小白零命令行。
"""
from __future__ import annotations

import threading
import webbrowser
from pathlib import Path


def _browser_open_later(url: str) -> None:
    """延迟 1.2s 打开浏览器（等服务端口就绪，避免白屏）。"""
    import time

    time.sleep(1.2)
    webbrowser.open(url)


def main() -> None:
    import uvicorn

    from talentforge.api.app import create_app

    # 打包后 web/ 被 --add-data 解包到 _MEIPASS/web，create_app 需能找到
    import sys

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        from talentforge.api import app as app_module

        candidate = Path(meipass) / "web"
        if candidate.exists():
            app_module.DEFAULT_WEB_DIR = candidate

    app = create_app()
    host, port = "127.0.0.1", 8420
    threading.Thread(target=_browser_open_later, args=(f"http://{host}:{port}/",), daemon=True).start()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
