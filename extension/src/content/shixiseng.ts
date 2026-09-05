// 实习僧 content script（M11 auto 通道）：列表页卡片采集 → POST /api/jobs/batch。
// 触发 = 页面加载 + SPA 路由变化（boss.ts 同款轮询模式）；auto 无人访问由
// task_runner 开 tab 触发，用户手动浏览同样收获（岗位事实语义，两种触发等价）。
import { collectListCards, isInternListPage } from "../shared/platforms/shixiseng";
import { reportJobs } from "../shared/jobs_report";

const sentUrls = new Set<string>();

function postJobs(cards: ReturnType<typeof collectListCards>): void {
  reportJobs("shixiseng", cards);
}

function harvest(): void {
  const fresh = collectListCards(document).filter((card) => !sentUrls.has(card.url));
  for (const card of fresh) sentUrls.add(card.url);
  postJobs(fresh);
}

let currentUrl = window.location.href;
function onUrlChanged(): void {
  const next = window.location.href;
  if (next === currentUrl) return;
  currentUrl = next;
  if (isInternListPage(next)) harvest();
}

if (isInternListPage(currentUrl)) {
  harvest();
}
window.setInterval(onUrlChanged, 1_500);

(globalThis as Record<string, unknown>).__talentforge_shixiseng = true;
