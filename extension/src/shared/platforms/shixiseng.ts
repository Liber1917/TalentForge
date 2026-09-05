// 实习僧平台适配（M11 auto，m11-platform-recon §二）：
// 列表页 SSR 卡片（div.intern-item[data-intern-id]）；标题/数字经字体反爬
// （PUA 码点），公司/城市/标签可读——PUA 剥离后按可读部分采集。
export interface SxsJobCard {
  title: string;
  company: string;
  location: string;
  salary: string;
  url: string;
  tags: string[];
  description: string;
}

const PUA_RE = /[\uE000-\uF8FF]/g;

export function stripPua(text: string): string {
  return text.replace(PUA_RE, "");
}

export function isInternListPage(url: string): boolean {
  try {
    const u = new URL(url);
    return u.hostname.endsWith("shixiseng.com") && /^\/interns/.test(u.pathname);
  } catch {
    return false;
  }
}

function canonicalDetailUrl(href: string | null): string | null {
  if (!href) return null;
  try {
    const u = new URL(href, "https://www.shixiseng.com");
    if (!/\/intern\/inn_/.test(u.pathname)) return null;
    u.search = "";
    u.hash = "";
    return u.toString().replace(/\/$/, "");
  } catch {
    return null;
  }
}

function textOf(el: Element | null): string {
  return stripPua(el?.textContent?.trim() ?? "");
}

function extractLocation(cityText: string): string {
  const m = cityText.match(/(?:天|日|月)\s*(.+)$/);
  return (m ? m[1] : cityText).trim();
}

function extractSalary(text: string): string {
  const m = stripPua(text).match(
    /[\d\-–~]*\s*-\s*[\d\-–~]*\s*[\/／]\s*(?:天|日|月)|\d+\s*[\/／]\s*(?:天|日|月)/,
  );
  return m ? m[0].replace(/\s+/g, "") : "";
}

export function collectListCards(root: ParentNode): SxsJobCard[] {
  const cards: SxsJobCard[] = [];
  root.querySelectorAll<HTMLElement>("div.intern-item[data-intern-id]").forEach((el) => {
    const link = el.querySelector<HTMLAnchorElement>("a.title, a[href*='/intern/inn_']");
    const url = link ? canonicalDetailUrl(link.getAttribute("href")) : null;
    if (!url) return;
    const companyEl = el.querySelector(".company") ?? el.querySelector(".intern-detail__company p");
    const cityText = textOf(el.querySelector(".city"));
    const tags = Array.from(el.querySelectorAll(".intern-label"))
      .map((t) => textOf(t))
      .filter(Boolean);
    cards.push({
      title: textOf(link),
      company: textOf(companyEl),
      location: extractLocation(cityText),
      salary: extractSalary(el.textContent ?? ""),
      url,
      tags,
      description: tags.join("、"),
    });
  });
  return cards;
}
