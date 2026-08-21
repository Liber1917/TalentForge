import { describe, expect, it } from "vitest";
import {
  DEFAULT_BACKEND_BASE,
  eventsEndpoint,
} from "../shared/backend-endpoint";

describe("backend-endpoint", () => {
  it("builds the default events endpoint", () => {
    expect(DEFAULT_BACKEND_BASE).toBe("http://127.0.0.1:8420");
    expect(eventsEndpoint()).toBe("http://127.0.0.1:8420/api/events");
  });

  it("builds the endpoint from a custom base", () => {
    expect(eventsEndpoint("http://localhost:9999")).toBe(
      "http://localhost:9999/api/events",
    );
  });
});
