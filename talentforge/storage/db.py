"""Job / 行为事件存储（sqlite3 标准库实现，不用 ORM）：建库建表 / 去重写入 / 读回归一化数据。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from talentforge.domain.job import Job
from talentforge.domain.profile import SalaryRange

DEFAULT_DB_PATH = "data/talentforge.db"

_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS jobs (
        job_url TEXT PRIMARY KEY,
        source TEXT,
        title TEXT,
        company TEXT,
        location TEXT,
        salary_json TEXT,
        tags_json TEXT,
        description TEXT,
        risk_keys_json TEXT,
        scraped_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT,
        url TEXT,
        title TEXT,
        source_platform TEXT,
        context_json TEXT,
        metadata_json TEXT,
        received_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_url TEXT,
        source TEXT,
        title TEXT,
        company TEXT,
        verdict TEXT,
        reason TEXT,
        gaps_json TEXT,
        competency_json TEXT,
        profile_snapshot_json TEXT,
        decided_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS collection_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        url TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        dwell_ms INTEGER NOT NULL DEFAULT 15000,
        runner TEXT,
        result_json TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        claimed_at TEXT,
        finished_at TEXT
    )
    """,
)


def init_db(
    path: str | Path = DEFAULT_DB_PATH,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """打开（必要时创建）数据库并返回连接。

    ":memory:" 内存库跳过父目录创建；jobs / events 表幂等创建（IF NOT EXISTS）；
    row_factory 设为 sqlite3.Row 以便按列名取值。check_same_thread 透传给
    sqlite3.connect（HTTP server 多线程场景传 False）。
    """
    path_str = str(path)
    if path_str != ":memory:":
        Path(path_str).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path_str, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    for statement in _SCHEMA:
        conn.execute(statement)
    conn.commit()
    return conn


def upsert_job(conn: sqlite3.Connection, job: Job) -> bool:
    """插入岗位（按 job_url 去重）：新插入返回 True，同 URL 已存在返回 False（不更新）。"""
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO jobs
            (job_url, source, title, company, location,
             salary_json, tags_json, description, risk_keys_json, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job.url,
            job.source,
            job.title,
            job.company,
            job.location,
            job.salary.model_dump_json() if job.salary is not None else None,
            json.dumps(job.tags, ensure_ascii=False),
            job.description,
            json.dumps(job.risk_keys, ensure_ascii=False),
            job.scraped_at.isoformat(),
        ),
    )
    conn.commit()
    return cursor.rowcount > 0


def insert_event(
    conn: sqlite3.Connection,
    event_id: str,
    event_type: str,
    url: str,
    title: str,
    source_platform: str,
    context_json: str,
    metadata_json: str,
    received_at: str,
) -> bool:
    """插入行为事件（按 event_id 幂等去重）：新插入返回 True，同 event_id 已存在返回 False。"""
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO events
            (event_id, event_type, url, title, source_platform,
             context_json, metadata_json, received_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            event_type,
            url,
            title,
            source_platform,
            context_json,
            metadata_json,
            received_at,
        ),
    )
    conn.commit()
    return cursor.rowcount > 0


def _load_json(value: str | None) -> dict:
    """反序列化 JSON 字段：空串/损坏返回空 dict。"""
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def list_events(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    """按接收时间倒序读回最近事件（limit 条），context/metadata 反序列化为 dict。"""
    rows = conn.execute(
        "SELECT * FROM events ORDER BY received_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "url": row["url"],
            "title": row["title"],
            "source_platform": row["source_platform"],
            "context": _load_json(row["context_json"]),
            "metadata": _load_json(row["metadata_json"]),
            "received_at": row["received_at"],
        }
        for row in rows
    ]


def list_jobs(conn: sqlite3.Connection, limit: int = 100, offset: int = 0) -> list[Job]:
    """按抓取时间倒序读回岗位列表（limit/offset 分页），JSON 字段反序列化为 Job。"""
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY scraped_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    jobs: list[Job] = []
    for row in rows:
        salary = None
        if row["salary_json"]:
            salary = SalaryRange.model_validate_json(row["salary_json"])
        jobs.append(
            Job(
                source=row["source"],
                title=row["title"],
                company=row["company"],
                location=row["location"],
                url=row["job_url"],
                description=row["description"] or "",
                salary=salary,
                tags=json.loads(row["tags_json"] or "[]"),
                risk_keys=json.loads(row["risk_keys_json"] or "[]"),
                scraped_at=datetime.fromisoformat(row["scraped_at"]),
            )
        )
    return jobs


def insert_decision(
    conn: sqlite3.Connection,
    job_url: str,
    source: str,
    title: str,
    company: str,
    verdict: str,
    reason: str,
    gaps: list,
    competency: list,
    profile_snapshot: dict | None = None,
    decided_at: str | None = None,
) -> None:
    """落一条决策历史（append-only，回测地基）：每次决策都追加，不覆盖。"""
    if decided_at is None:
        decided_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO decisions
            (job_url, source, title, company, verdict, reason,
             gaps_json, competency_json, profile_snapshot_json, decided_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_url,
            source,
            title,
            company,
            verdict,
            reason,
            json.dumps(gaps, ensure_ascii=False),
            json.dumps(competency, ensure_ascii=False),
            json.dumps(profile_snapshot, ensure_ascii=False) if profile_snapshot else None,
            decided_at,
        ),
    )
    conn.commit()


def list_decisions(
    conn: sqlite3.Connection,
    limit: int = 200,
    since: str | None = None,
) -> list[dict]:
    """按决策时间倒序读回决策历史（limit 条）；since 过滤（ISO 时间串，含该时刻）。

    回测地基：字段含 verdict/reason/gaps/competency/profile_snapshot，JSON 已反序列化。
    """
    sql = "SELECT * FROM decisions"
    params: list = []
    if since:
        sql += " WHERE decided_at >= ?"
        params.append(since)
    sql += " ORDER BY decided_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "id": row["id"],
            "job_url": row["job_url"],
            "source": row["source"],
            "title": row["title"],
            "company": row["company"],
            "verdict": row["verdict"],
            "reason": row["reason"],
            "gaps": _load_json_list(row["gaps_json"]),
            "competency": _load_json_list(row["competency_json"]),
            "profile_snapshot": _load_json(row["profile_snapshot_json"]),
            "decided_at": row["decided_at"],
        }
        for row in rows
    ]


def _load_json_list(value: str | None) -> list:
    """反序列化 JSON 数组字段：空串/损坏返回空 list（非 dict 字段用）。"""
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


# ---------------- M11 采集任务（D30 auto 通道） ----------------

_TASK_ACTIVE_STATUSES = ("pending", "running")
_TASK_TERMINAL_STATUSES = ("done", "failed", "aborted")
_MAX_TASK_DWELL_MS = 30_000


def enqueue_task(
    conn: sqlite3.Connection, platform: str, url: str, dwell_ms: int = 15_000
) -> int | None:
    """auto 采集任务入队：同平台同 URL 未完成（pending/running）→ 去重拒绝 None。

    dwell_ms 服务端封顶 30s（M11 护栏：单任务停留预算）。
    """
    dup = conn.execute(
        "SELECT id FROM collection_tasks WHERE platform=? AND url=? AND status IN (?, ?)",
        (platform, url, *_TASK_ACTIVE_STATUSES),
    ).fetchone()
    if dup is not None:
        return None
    cursor = conn.execute(
        """
        INSERT INTO collection_tasks (platform, url, status, dwell_ms, created_at)
        VALUES (?, ?, 'pending', ?, ?)
        """,
        (
            platform,
            url,
            min(int(dwell_ms), _MAX_TASK_DWELL_MS),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def claim_next_task(conn: sqlite3.Connection, runner: str) -> dict | None:
    """原子领取最早的 pending 任务（pending→running）；无任务返回 None。"""
    with conn:
        row = conn.execute(
            "SELECT * FROM collection_tasks WHERE status='pending' ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        cursor = conn.execute(
            "UPDATE collection_tasks SET status='running', runner=?, claimed_at=? "
            "WHERE id=? AND status='pending'",
            (runner, datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        if cursor.rowcount != 1:
            return None
    fresh = conn.execute(
        "SELECT * FROM collection_tasks WHERE id=?", (row["id"],)
    ).fetchone()
    return dict(fresh)


def report_task(
    conn: sqlite3.Connection,
    task_id: int,
    status: str,
    inserted: int | None = None,
    risk_signal: str | None = None,
    error: str | None = None,
) -> bool:
    """runner 回报终态（done/failed/aborted）；仅 running 任务可回报，成功返回 True。

    risk_signal 非空（风控信号）随 result 落库——platform_in_cooldown 据此判定冷却。
    """
    if status not in _TASK_TERMINAL_STATUSES:
        raise ValueError(f"非法任务终态: {status}")
    result: dict[str, object] = {}
    if inserted is not None:
        result["inserted"] = inserted
    if risk_signal:
        result["risk_signal"] = risk_signal
    cursor = conn.execute(
        "UPDATE collection_tasks SET status=?, result_json=?, error=?, finished_at=? "
        "WHERE id=? AND status='running'",
        (
            status,
            json.dumps(result, ensure_ascii=False) if result else None,
            error,
            datetime.now(timezone.utc).isoformat(),
            task_id,
        ),
    )
    conn.commit()
    return cursor.rowcount == 1


def count_tasks_today(conn: sqlite3.Connection, platform: str) -> int:
    """当日该平台入队任务数（配额口径，不分状态）。"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM collection_tasks WHERE platform=? AND created_at LIKE ?",
        (platform, f"{today}%"),
    ).fetchone()
    return int(row["n"])


def platform_in_cooldown(
    conn: sqlite3.Connection, platform: str, minutes: int = 30
) -> bool:
    """平台冷却判定：minutes 窗口内有带 risk_signal 的已完结任务 → True。"""
    threshold = (
        datetime.now(timezone.utc) - timedelta(minutes=minutes)
    ).isoformat()
    row = conn.execute(
        "SELECT 1 FROM collection_tasks "
        "WHERE platform=? AND finished_at IS NOT NULL AND finished_at >= ? "
        "AND result_json LIKE '%\"risk_signal\"%' LIMIT 1",
        (platform, threshold),
    ).fetchone()
    return row is not None


def list_tasks(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    """按入队时间倒序读回采集任务（设置页/验收可见性）。"""
    rows = conn.execute(
        "SELECT * FROM collection_tasks ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(row) for row in rows]
