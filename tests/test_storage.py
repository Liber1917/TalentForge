"""存储与归一化测试（内存库建表 / upsert 去重 / list 读回 / 风险扫描 / 卡片→Job 组装）。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from talentforge.domain.job import Job
from talentforge.domain.profile import SalaryRange
from talentforge.sources.normalize import normalize_to_job, scan_risks
from talentforge.storage.db import init_db, list_jobs, upsert_job


def _make_job(**overrides: object) -> Job:
    defaults: dict[str, object] = dict(
        source="boss",
        title="Python 后端工程师",
        company="星辰科技",
        location="深圳",
        url="https://www.zhipin.com/job_detail/base_1.html",
        description="负责分布式系统开发",
        salary=SalaryRange(min_annual=400000, max_annual=800000, currency="CNY"),
        tags=["Python", "分布式"],
        risk_keys=["大小周"],
        scraped_at=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


def test_init_db_memory_creates_jobs_table_with_row_factory() -> None:
    conn = init_db(":memory:")
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "jobs" in tables
    assert conn.row_factory is sqlite3.Row


def test_init_db_file_creates_parent_dirs(tmp_path) -> None:
    db_path = tmp_path / "nested" / "dir" / "talentforge.db"
    conn = init_db(db_path)
    assert db_path.exists()
    assert upsert_job(conn, _make_job()) is True
    assert len(list_jobs(conn)) == 1


def test_upsert_new_job_true_then_duplicate_false() -> None:
    conn = init_db(":memory:")
    assert upsert_job(conn, _make_job()) is True
    # 同 URL 视为同岗位：不更新，返回 False
    assert upsert_job(conn, _make_job(title="改了标题也不更新")) is False
    assert len(list_jobs(conn)) == 1


def test_list_jobs_roundtrips_all_fields() -> None:
    conn = init_db(":memory:")
    job = _make_job()
    upsert_job(conn, job)
    jobs = list_jobs(conn)
    assert len(jobs) == 1
    got = jobs[0]
    assert got.url == job.url
    assert got.source == "boss"
    assert got.title == "Python 后端工程师"
    assert got.company == "星辰科技"
    assert got.location == "深圳"
    assert got.description == "负责分布式系统开发"
    assert got.salary is not None
    assert got.salary.min_annual == 400000
    assert got.salary.max_annual == 800000
    assert got.salary.currency == "CNY"
    assert got.tags == ["Python", "分布式"]
    assert got.risk_keys == ["大小周"]
    assert got.scraped_at == job.scraped_at


def test_list_jobs_orders_newest_first_and_paginates() -> None:
    conn = init_db(":memory:")
    for day in range(3):
        upsert_job(
            conn,
            _make_job(
                url=f"https://www.zhipin.com/job_detail/{day}.html",
                scraped_at=datetime(2026, 8, day + 1, tzinfo=timezone.utc),
            ),
        )
    jobs = list_jobs(conn)
    assert [job.url.rsplit("/", 1)[-1] for job in jobs] == ["2.html", "1.html", "0.html"]
    assert [job.url.rsplit("/", 1)[-1] for job in list_jobs(conn, limit=2)] == [
        "2.html",
        "1.html",
    ]
    assert list_jobs(conn, limit=2, offset=2)[0].url.endswith("0.html")


def test_scan_risks_hits_expected_keywords() -> None:
    assert set(scan_risks("要求适应大小周和偶尔无偿加班")) == {"大小周", "无偿加班"}


def test_scan_risks_no_hit_returns_empty() -> None:
    assert scan_risks("朝九晚五，周末双休，团队氛围好") == []


def test_scan_risks_dedupes_repeated_keyword() -> None:
    assert scan_risks("我们是996团队，坚持996文化") == ["996"]


def test_normalize_to_job_assembles_job_with_risks() -> None:
    card: dict[str, object] = {
        "title": "Java 后端工程师",
        "company": "星环科技",
        "salary_text": "30-45K·14薪",
        "tags": ["Java", "大小周"],
        "href": "https://www.zhipin.com/job_detail/norm_1.html",
        "description": "负责基础架构研发",
    }
    job = normalize_to_job(card, "杭州")
    assert job.source == "boss"
    assert job.title == "Java 后端工程师"
    assert job.company == "星环科技"
    assert job.location == "杭州"
    assert job.url == "https://www.zhipin.com/job_detail/norm_1.html"
    assert job.description == "负责基础架构研发 Java 大小周"
    assert job.tags == ["Java", "大小周"]
    assert "大小周" in job.risk_keys
    assert job.salary is not None
    assert job.salary.min_annual == 420000
    assert job.salary.max_annual == 630000
    assert job.salary.currency == "CNY"


def test_normalize_to_job_without_salary_or_risks() -> None:
    card: dict[str, object] = {
        "title": "运维工程师",
        "company": "某公司",
        "salary_text": "面议",
        "tags": [],
        "href": "https://www.zhipin.com/job_detail/norm_2.html",
        "description": "日常运维与值班",
    }
    job = normalize_to_job(card, "北京")
    assert job.salary is None
    assert job.risk_keys == []
    assert job.description == "日常运维与值班"
