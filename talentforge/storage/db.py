"""Job / 行为事件存储（sqlite3 标准库实现，不用 ORM）：建库建表 / 去重写入 / 读回归一化数据。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
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
