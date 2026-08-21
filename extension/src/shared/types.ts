// Shared domain types: BehaviorEvent contract and PlatformAdapter interface (Task 4/5 fill details).
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
  buildEventMetadata(...args: unknown[]): Record<string, unknown>;
}
