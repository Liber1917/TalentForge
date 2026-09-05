// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import {
  collectListCards,
  isInternListPage,
  stripPua,
} from "../shared/platforms/shixiseng";

// 结构取自 2026-09-02 实抓 DOM：div.intern-item[data-intern-id] 卡片，
// 标题/数字经字体反爬（PUA 码点 U+E000-U+F8FF），公司/城市/标签可读。
const LIST_HTML = `
<div class="result-list clearfix">
  <div data-intern-id="inn_oqgz610h4ysr" class="intern-wrap interns-point intern-item">
    <div class="clearfix intern-detail">
      <div class="f-l intern-detail__job">
        <p><a href="https://www.shixiseng.com/intern/inn_oqgz610h4ysr?pcm=pc_SearchList"
              class="title ellipsis font">\uEA56\uEB93开发实习\uF057</a></p>
        <p class="city ellipsis">\uF231\uF100-\uE931\uE5E7/天 北京</p>
        <p>友邦资讯科技</p>
        <div class="clearfix advantage-wrap tip">
          <span class="intern-label">可转正实习</span>
          <span class="intern-label">周末双休</span>
        </div>
      </div>
      <div class="f-r intern-detail__company">
        <p class="company">友邦资讯科技</p>
        <span class="company__label">互联网/游戏/软件</span>
      </div>
    </div>
  </div>
  <div data-intern-id="inn_abc123" class="intern-wrap interns-point intern-item">
    <div class="clearfix intern-detail">
      <div class="f-l intern-detail__job">
        <p><a href="https://www.shixiseng.com/intern/inn_abc123?pcm=pc_SearchList"
              class="title ellipsis font">Python后端实习</a></p>
        <p class="city ellipsis">150-247/天 上海</p>
        <p>百度</p>
      </div>
      <div class="f-r intern-detail__company">
        <p class="company">百度</p>
      </div>
    </div>
  </div>
</div>`;

describe("stripPua", () => {
  it("removes private-use-area codepoints (font anti-crawl)", () => {
    expect(stripPua("\uEA56\uEB93开发实习\uF057")).toBe("开发实习");
    expect(stripPua("150-247/天")).toBe("150-247/天");
    expect(stripPua("")).toBe("");
  });
});

describe("isInternListPage", () => {
  it("matches search/list URLs", () => {
    expect(isInternListPage("https://www.shixiseng.com/interns?k=Python&city=%E5%8C%97%E4%BA%AC")).toBe(true);
    expect(isInternListPage("https://www.shixiseng.com/intern/inn_x")).toBe(false);
    expect(isInternListPage("https://www.shixiseng.com/")).toBe(false);
  });
});

describe("collectListCards", () => {
  it("extracts cards with canonical URLs and readable fields", () => {
    document.body.innerHTML = LIST_HTML;
    const cards = collectListCards(document);
    expect(cards).toHaveLength(2);

    const first = cards[0]!;
    expect(first.url).toBe("https://www.shixiseng.com/intern/inn_oqgz610h4ysr");
    expect(first.title).toBe("开发实习"); // PUA 剥离后保留可读部分
    expect(first.company).toBe("友邦资讯科技");
    expect(first.location).toContain("北京");
    expect(first.tags).toContain("可转正实习");

    const second = cards[1]!;
    expect(second.title).toBe("Python后端实习");
    expect(second.salary).toBe("150-247/天");
    expect(second.location).toContain("上海");
  });

  it("keeps obfuscated salary as-is when digits are PUA-mangled", () => {
    document.body.innerHTML = LIST_HTML;
    const first = collectListCards(document)[0]!;
    expect(first.salary).toContain("/天"); // 结构保留，数字可能残缺（字体反爬已知局限）
  });

  it("skips cards without a detail link", () => {
    document.body.innerHTML = `
      <div data-intern-id="inn_x" class="intern-item"><div class="intern-detail__job"></div></div>`;
    expect(collectListCards(document)).toHaveLength(0);
  });
});
