import { describe, it, expect } from "vitest";
import { http, HttpResponse } from "msw";
import { createTask, API_URL } from "../api";

import { server } from "../../test/setup";

describe("api - createTask", () => {
  it("should successfully create a task with only a URL", async () => {
    let requestBody: any;
    server.use(
      http.post(`${API_URL}/tasks`, async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json({ task_id: "test-task-123" });
      })
    );

    const result = await createTask("https://youtube.com/watch?v=123");
    expect(result).toEqual({ task_id: "test-task-123" });
    expect(requestBody).toEqual({ url: "https://youtube.com/watch?v=123" });
  });

  it("should successfully create a task with URL and options", async () => {
    let requestBody: any;
    server.use(
      http.post(`${API_URL}/tasks`, async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json({ task_id: "test-task-456" });
      })
    );

    const opts = { num_clips: 3, subtitle_style: "tiktok" };
    const result = await createTask("https://youtube.com/watch?v=456", opts);

    expect(result).toEqual({ task_id: "test-task-456" });
    expect(requestBody).toEqual({
      url: "https://youtube.com/watch?v=456",
      num_clips: 3,
      subtitle_style: "tiktok"
    });
  });

  it("should throw an error with detail message if response is not ok and contains detail", async () => {
    server.use(
      http.post(`${API_URL}/tasks`, () => {
        return HttpResponse.json({ detail: "Invalid URL provided" }, { status: 400 });
      })
    );

    await expect(createTask("bad-url")).rejects.toThrow("Invalid URL provided");
  });

  it("should throw a default error message if response is not ok and JSON parsing fails", async () => {
    server.use(
      http.post(`${API_URL}/tasks`, () => {
        return new HttpResponse("Not found", { status: 404, headers: { "Content-Type": "text/plain" } });
      })
    );

    await expect(createTask("https://youtube.com/watch?v=123")).rejects.toThrow("Request failed (404)");
  });

  it("should throw a default error message if response is not ok and does not contain detail", async () => {
    server.use(
      http.post(`${API_URL}/tasks`, () => {
        return HttpResponse.json({ otherField: "something" }, { status: 500 });
      })
    );

    await expect(createTask("https://youtube.com/watch?v=123")).rejects.toThrow("Request failed (500)");
  });
});
