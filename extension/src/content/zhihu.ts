// Zhihu content-script entry (document_idle, isolated world). Wires the zhihu
// adapter into the collector kernel.
import { ZHIHU_ADAPTER } from "../shared/platforms/zhihu";
import { startCollector } from "./kernel";

const collector = startCollector(ZHIHU_ADAPTER);

void collector;

(globalThis as Record<string, unknown>).__talentforge_zhihu = true;
