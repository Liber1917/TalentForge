// Shared domain types: BehaviorEvent contract and PlatformAdapter interface.

export const EVENT_TYPES = {
  click: "click",
  scroll: "scroll",
  search: "search",
  view: "view",
  comment: "comment",
  like: "like",
  favorite: "favorite",
} as const;

export type EventType = (typeof EVENT_TYPES)[keyof typeof EVENT_TYPES];

/** Strong-signal actions: worth an immediate flush and heavier downstream weight. */
export const STRONG_SIGNAL_TYPES: ReadonlySet<string> = new Set<string>([
  EVENT_TYPES.comment,
  EVENT_TYPES.like,
  EVENT_TYPES.favorite,
]);

export function isStrongSignal(type: string): boolean {
  return STRONG_SIGNAL_TYPES.has(type);
}

/** Self-generated identity for events; unique per producer + stable across storage moves. */
export function newEventId(): string {
  const cryptoApi = globalThis.crypto;
  if (typeof cryptoApi?.randomUUID === "function") return cryptoApi.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export interface BehaviorEvent {
  event_id: string;
  type: string;
  url: string;
  title: string;
  timestamp: string;
  source_platform: string;
  context: {
    pageType: string;
    domSnapshot?: string;
    viewport: { width: number; height: number };
    scrollPosition: { x: number; y: number };
  };
  metadata: Record<string, unknown>;
}

export interface PlatformAdapter {
  sourcePlatform: string;
  detectPageType(url: string): string;
  extractContentId(url: string): string | null;
  cardSelector?: string;
  inferActionType(target: Element | null): string | null;
  buildEventMetadata(url: string): Record<string, unknown>;
}
