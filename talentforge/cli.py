from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import click

from talentforge.api.app import create_app
from talentforge.api.events import handle_events
from talentforge.competency.builder import DefaultCompetencyModelBuilder
from talentforge.decision.verdict import decide
from talentforge.domain.competency import CompetencyModel
from talentforge.domain.match import Match, FitLevel, StructuralAssessment
from talentforge.domain.profile import Profile
from talentforge.llm.client import EnvLLMClient, LLMClient
from talentforge.matcher.coarse import CoarseMatcher
from talentforge.profile.engine import DefaultProfileEngine
from talentforge.profile.pipeline import ProfileUpdatePipeline
from talentforge.profile.resume_io import extract_resume_text
from talentforge.report.generate import generate_report
from talentforge.sources.boss import parse_boss_cards
from talentforge.sources.normalize import normalize_to_job
from talentforge.storage.db import init_db, list_events


def _build_llm() -> LLMClient:
    """构造 LLM 客户端（独立函数便于测试 monkeypatch）。"""
    return EnvLLMClient()


@click.group()
def main() -> None:
    """TalentForge — 锻造人才的求职决策助手。"""


@main.command("decide")
@click.option("--market-fit", type=click.Choice(["high", "low"]), required=True)
@click.option("--growth-fit", type=click.Choice(["high", "low"]), required=True)
@click.option("--risk", multiple=True, help="命中的结构性风险，如 996、无社保")
@click.option("--deal-breaker", multiple=True, help="用户 deal-breaker，命中即不投")
def decide_command(market_fit: str, growth_fit: str, risk: tuple[str, ...], deal_breaker: tuple[str, ...]) -> None:
    """M0 walking skeleton：给定匹配信号，输出三元决策。"""
    match = Match(
        job_id="demo",
        market_fit=FitLevel(market_fit),
        growth_fit=FitLevel(growth_fit),
        structural=StructuralAssessment(risks=list(risk)),
    )
    verdict = decide(match, list(deal_breaker))
    click.echo(f"verdict={verdict.value}")


@main.command("serve-api")
@click.option("--host", type=str, default="127.0.0.1", show_default=True, help="监听地址")
@click.option("--port", type=int, default=8420, show_default=True, help="监听端口")
def serve_api(host: str, port: int) -> None:
    """启动 FastAPI 服务（/api/health、/api/events、静态 web/），替代原 stdlib server。"""
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port)


async def _run_profile_build(explicit: dict[str, Any]) -> Profile:
    engine = DefaultProfileEngine(llm=_build_llm())
    return await engine.build_profile(explicit)


@main.command("profile-build")
@click.option("--name", type=str, default="", help="候选人姓名")
@click.option("--resume-file", type=click.Path(exists=True, dir_okay=False), required=True, help="简历文件（.txt/.md/.pdf/.docx）")
@click.option("--explicit-json", type=click.Path(exists=True, dir_okay=False), default=None, help="显式画像 JSON（八格/效用等）")
def profile_build(name: str, resume_file: str, explicit_json: str | None) -> None:
    """简历 bootstrap 生成画像，输出 Profile JSON 摘要到 stdout。"""
    resume_text = extract_resume_text(resume_file)
    if explicit_json:
        explicit = json.loads(Path(explicit_json).read_text(encoding="utf-8"))
    else:
        explicit = {"name": name}
    explicit.setdefault("resume_text", resume_text)
    profile = asyncio.run(_run_profile_build(explicit))
    click.echo(json.dumps(profile.model_dump(), ensure_ascii=False, indent=2))


async def _run_competency_build(role: str, level: str, jd_text: str) -> CompetencyModel:
    builder = DefaultCompetencyModelBuilder(llm=_build_llm())
    return await builder.build(role, level, [jd_text])


@main.command("competency")
@click.option("--role", required=True, help="目标岗位")
@click.option("--level", required=True, help="招聘级别，如 校招/社招")
@click.option("--jd-file", type=click.Path(exists=True, dir_okay=False), required=True, help="JD 文本文件")
def competency_command(role: str, level: str, jd_file: str) -> None:
    """构建岗位胜任力模型（六维结构化 JSON）到 stdout。"""
    jd_text = Path(jd_file).read_text(encoding="utf-8")
    model = asyncio.run(_run_competency_build(role, level, jd_text))
    click.echo(json.dumps(model.model_dump(), ensure_ascii=False, indent=2))


@main.command("report")
@click.option(
    "--profile",
    "profile_file",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Profile JSON 文件（name 必需）",
)
@click.option("--query", required=True, help="搜索关键词，如 后端工程师")
@click.option("--city", required=True, help="城市名，如 深圳")
@click.option("--limit", type=int, default=10, show_default=True, help="最多评估岗位数")
@click.option(
    "--db",
    type=click.Path(dir_okay=False),
    default=None,
    help="SQLite 路径（默认 data/talentforge.db）",
)
@click.option(
    "--offline-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="本地 HTML 搜索页，跳过浏览器抓取",
)
def report_command(
    profile_file: str,
    query: str,
    city: str,
    limit: int,
    db: str | None,
    offline_file: str | None,
) -> None:
    """Boss 岗位链路端到端：抓取→归一化→匹配→决策报告 JSON 到 stdout。"""
    profile_data = json.loads(Path(profile_file).read_text(encoding="utf-8"))
    profile = Profile.model_validate(profile_data)
    matcher = CoarseMatcher(_build_llm())
    jobs = None
    if offline_file:
        html = Path(offline_file).read_text(encoding="utf-8")
        jobs = [normalize_to_job(card, city) for card in parse_boss_cards(html)]
    conn = init_db(db) if db else None
    report = asyncio.run(
        generate_report(profile, query, city, limit=limit, matcher=matcher, conn=conn, jobs=jobs)
    )
    click.echo(json.dumps(report, ensure_ascii=False, indent=2))


async def _run_profile_update(pipeline: ProfileUpdatePipeline, profile: Profile, events: list[dict]) -> Profile:
    """消费事件批并返回更新后的 Profile。"""
    return await pipeline.ingest_events(profile, events)


@main.command("events-ingest")
@click.argument("jsonl_path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--db",
    type=click.Path(dir_okay=False),
    default=None,
    help="SQLite 路径（默认 data/talentforge.db）",
)
def events_ingest(jsonl_path: str, db: str | None) -> None:
    """逐行读取事件 JSONL，校验并入库（event_id 幂等去重，不消费）。"""
    conn = init_db(db) if db else init_db()
    events: list[dict] = []
    invalid = 0
    for line in Path(jsonl_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if isinstance(data, dict):
            events.append(data)
        else:
            invalid += 1
    result = handle_events({"events": events}, conn)
    stats = {
        "ingested": result["accepted"],
        "duplicates": result["duplicates"],
        "invalid": invalid + len(result["rejected"]),
    }
    click.echo(json.dumps(stats, ensure_ascii=False))


@main.command("profile-update")
@click.option(
    "--profile",
    "profile_file",
    type=click.Path(dir_okay=False),
    required=True,
    help="Profile JSON 文件（写回更新）",
)
@click.option("--limit", type=int, default=50, show_default=True, help="最多消费最近事件数")
@click.option(
    "--db",
    type=click.Path(dir_okay=False),
    default=None,
    help="SQLite 路径（默认 data/talentforge.db）",
)
def profile_update(profile_file: str, limit: int, db: str | None) -> None:
    """从事件表消费最近事件，更新画像（trial claims 累积）并写回文件。"""
    profile = Profile.model_validate(json.loads(Path(profile_file).read_text(encoding="utf-8")))
    conn = init_db(db) if db else init_db()
    events = list_events(conn, limit=limit)
    before = {claim.text: claim.evidence_count for claim in profile.narrative_claims}
    pipeline = ProfileUpdatePipeline(llm=_build_llm())
    updated = asyncio.run(_run_profile_update(pipeline, profile, events))
    Path(profile_file).write_text(
        json.dumps(updated.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    added = sum(1 for claim in updated.narrative_claims if claim.text not in before)
    updated_count = sum(
        1
        for claim in updated.narrative_claims
        if claim.text in before and claim.evidence_count > before[claim.text]
    )
    click.echo(
        json.dumps({"added_claims": added, "updated_claims": updated_count}, ensure_ascii=False)
    )


@main.command("export")
@click.option("--since", default=None, help="只导出此时间（ISO 串）之后的决策历史")
@click.option("--out", default="talentforge-export.json", help="导出文件路径")
@click.option("--db", default=None, help="数据库路径（默认 data/talentforge.db）")
def export_command(since: str | None, out: str, db: str | None) -> None:
    """导出决策历史 + 岗位 + 画像快照（M10 回测地基，JSON 单文件）。

    回测用法：改完规则后，用同一份导出数据对比新旧 verdict 分布；
    亦可作为用户数据备份。凭据（LLM key / cookie）绝不出现在导出里。
    """
    from talentforge.api.common import load_profile
    from talentforge.storage.db import init_db, list_decisions, list_jobs

    conn = init_db(db or "data/talentforge.db")
    decisions = list_decisions(conn, limit=100000, since=since)
    jobs = [j.model_dump(mode="json") for j in list_jobs(conn, limit=100000)]
    try:
        profile = load_profile().model_dump(mode="json")
    except Exception:  # noqa: BLE001 — 画像缺失不阻断导出
        profile = None
    payload = {
        "exported_at": __import__("datetime").datetime.now().isoformat(),
        "since": since,
        "n_decisions": len(decisions),
        "n_jobs": len(jobs),
        "profile": profile,
        "decisions": decisions,
        "jobs": jobs,
    }
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"已导出 {len(decisions)} 条决策 + {len(jobs)} 条岗位 → {out}")


if __name__ == "__main__":
    main()
