"""Job 存储（sqlite3 标准库实现，不用 ORM）：建库建表 / 按 URL 去重写入 / 读回归一化 Job。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from talentforge.domain.job import Job
from talentforge.domain.profile import SalaryRange

DEFAULT_DB_PATH = "data/talentforge.db"

_SCHEMA = """
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
"""


def init_db(path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """打开（必要时创建）jobs 数据库并返回连接。

    ":memory:" 内存库跳过父目录创建；jobs 表幂等创建（IF NOT EXISTS）；
    row_factory 设为 sqlite3.Row 以便按列名取值。
    """
    path_str = str(path)
    if path_str != ":memory:":
        Path(path_str).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path_str)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
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
