"""M12 防御契约（D31 红线①）：/api/fixtures 永不注册任何后端路由。

前端假数据是视图内嵌 LOCAL_FIXTURE_*（客户端 mock），"演示沙箱物理隔离"
依赖后端不存在 fixtures 端点——写请求打到不存在路由即 404，不可能触达
SQLite/画像文件。本测试把这个事实钉成契约，杜绝未来"顺手加个 demo 端点"。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from talentforge.api.app import create_app
from talentforge.storage.db import init_db


def _client() -> TestClient:
    return TestClient(create_app(conn=init_db(":memory:", check_same_thread=False)))


def test_no_fixture_routes_ever_registered() -> None:
    app = create_app(conn=init_db(":memory:", check_same_thread=False))
    offenders = [
        getattr(route, "path", "")
        for route in app.routes
        if str(getattr(route, "path", "")).startswith("/api/fixtures")
    ]
    assert offenders == [], f"fixtures 路由违反 D31 红线: {offenders}"


def test_fixture_path_writes_return_404() -> None:
    client = _client()
    for path in ("/api/fixtures/chat/turns", "/api/fixtures/jobs/batch", "/api/fixtures/claims/x/confirm"):
        resp = client.post(path, json={})
        # 静态挂载对 POST 回 405、对不存在文件回 404——只要不是任何
        # fixtures 处理器的 2xx，写请求就从未触达业务逻辑。
        assert resp.status_code in (404, 405), f"{path} 不应有 fixtures 路由（got {resp.status_code}）"
