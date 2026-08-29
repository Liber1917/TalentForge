"""PyInstaller 打包入口：talentforge.exe → 启动 FastAPI 服务并打开浏览器。

分发版（exe）只做一件事：起服务 + 自动开浏览器，小白零命令行。

启动时把工作目录切到用户数据目录（Windows: %APPDATA%\\TalentForge，
Linux: ~/.local/share/talentforge）——双击 exe 时 cwd 不可控（可能落在
无写权限的 Program Files），而全站 data/ 相对路径依赖可写 cwd。
"""
from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path


def _data_dir() -> Path:
    """用户数据目录：Windows %APPDATA%/TalentForge，其他平台 ~/.local/share/talentforge。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "TalentForge"
    return Path.home() / ".local" / "share" / "talentforge"


def _browser_open_later(url: str) -> None:
    """延迟 1.2s 打开浏览器（等服务端口就绪，避免白屏）。"""
    import time

    time.sleep(1.2)
    webbrowser.open(url)


def main() -> None:
    import uvicorn

    from talentforge.api.app import create_app

    # 切到用户数据目录：全站 data/ 相对路径在此可写（exe 双击 cwd 不可控）
    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(data_dir)

    # 打包后 web/ 被 --add-data 解包到 _MEIPASS/web，create_app 需能找到
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
