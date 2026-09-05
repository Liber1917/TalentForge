// 智联平台适配（M11 auto，m11-platform-recon §一）：
// 数据通道 = 页面世界 fetch/XHR 调 fe-api.zhaopin.com/c/i/*（无页面绑定
// token）。MAIN-world 注入走 manifest "world": "MAIN"（扩展注入不受页面
// CSP 约束——inline <script> 注入方案已被实测 CSP 拦截否决）；截获响应经
// postMessage 桥回 isolated world（content/zhaopin.ts）上报——isolated 侧
// 走 service worker 中转，无 Origin/PNA 问题。
export interface ZpJobCard {
  title: string;
  company: string;
  location: string;
  salary: string;
  url: string;
  tags: string[];
  description: string;
}

export const ZHAOPIN_HOOK_MARKER = "TF_ZHAOPIN_API_DATA";

export function isZhaopinSearchUrl(url: string): boolean {
  try {
    const u = new URL(url);
    if (!u.hostname.endsWith("zhaopin.com")) return false;
    return u.hostname.startsWith("sou.") || /^\/sou/.test(u.pathname);
  } catch {
    return false;
  }
}

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

function nameOf(v: unknown): string {
  if (typeof v === "object" && v !== null) return str((v as Record<string, unknown>).name);
  return str(v);
}

export function mapFeApiItem(item: unknown): ZpJobCard | null {
  if (typeof item !== "object" || item === null) return null;
  const o = item as Record<string, unknown>;
  const title = str(o.name) || str(o.jobName);
  if (!title) return null;
  const company = nameOf(o.company) || str(o.companyName);
  const district = nameOf(o.district);
  const location = [nameOf(o.city), district].filter(Boolean).join("·");

  let salary = "";
  const s60 = typeof o.salary60 === "object" && o.salary60 !== null
    ? (o.salary60 as Record<string, unknown>)
    : {};
  const from = typeof s60.from === "number" ? s60.from : 0;
  const to = typeof s60.to === "number" ? s60.to : 0;
  if (from || to) salary = `${from}-${to}K/月`;
  if (!salary) salary = str(o.salaryReal);

  const id = str(o.number) || str(o.positionId);
  const tags = [
    ...(Array.isArray(o.welfare) ? o.welfare.map(str).filter(Boolean) : []),
    ...(Array.isArray(o.skills) ? o.skills.map(str).filter(Boolean) : []),
  ];
  return {
    title,
    company,
    location,
    salary,
    url: id ? `https://jobs.zhaopin.com/${id}.htm` : "",
    tags,
    description: tags.join("、") || str(o.jobSummary),
  };
}

// ---- MAIN-world hook（由 content/zhaopin-main.ts 于页面世界执行）----

export function isFeApiUrl(u: unknown): boolean {
  return typeof u === "string" && u.includes("fe-api.zhaopin.com") && u.includes("/c/i/");
}

export function installZhaopinHook(win: Window & typeof globalThis): void {
  const w = win as Window & typeof globalThis & { __tfZhaopinHooked?: boolean };
  if (w.__tfZhaopinHooked) return;
  w.__tfZhaopinHooked = true;

  const post = (url: string, data: unknown): void => {
    win.postMessage({ type: ZHAOPIN_HOOK_MARKER, url, data }, "*");
  };

  const originalFetch = win.fetch?.bind(win);
  if (originalFetch) {
    win.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const p = originalFetch(input as RequestInfo, init);
      if (isFeApiUrl(url)) {
        void p.then((res: Response) => {
          void res.clone().json().then((d: unknown) => post(url, d)).catch(() => undefined);
        }).catch(() => undefined);
      }
      return p;
    }) as typeof fetch;
  }

  const proto = win.XMLHttpRequest.prototype as XMLHttpRequest & {
    __tfUrl?: unknown;
    open: (m: string, u: string | URL, ...rest: unknown[]) => void;
    send: (...rest: unknown[]) => void;
  };
  const originalOpen = proto.open;
  const originalSend = proto.send;
  proto.open = function (this: XMLHttpRequest & { __tfUrl?: unknown }, method: string, url: string | URL, ...rest: unknown[]) {
    this.__tfUrl = url;
    return originalOpen.call(this, method, url, ...(rest as []));
  };
  proto.send = function (this: XMLHttpRequest & { __tfUrl?: unknown }, ...rest: unknown[]) {
    if (isFeApiUrl(this.__tfUrl)) {
      this.addEventListener("load", () => {
        try {
          post(String(this.__tfUrl), JSON.parse(this.responseText));
        } catch {
          // malformed json — skip
        }
      });
    }
    return originalSend.apply(this, rest as []);
  };
}
