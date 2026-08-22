// Backend base URL and endpoint construction.
export const DEFAULT_BACKEND_BASE = "http://127.0.0.1:8420";

export function eventsEndpoint(base: string = DEFAULT_BACKEND_BASE): string {
  return `${base}/api/events`;
}

export function backendEndpoint(base: string = DEFAULT_BACKEND_BASE): string {
  return `${base}/api`;
}
