// Bilibili content-script entry (document_idle, isolated world). Wires the
// bilibili adapter into the collector kernel.
import { BILIBILI_ADAPTER } from "../shared/platforms/bilibili";
import { startCollector } from "./kernel";

const collector = startCollector(BILIBILI_ADAPTER);

void collector;

(globalThis as Record<string, unknown>).__talentforge_bilibili = true;
