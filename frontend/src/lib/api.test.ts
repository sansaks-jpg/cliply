import { describe, it, expect } from "vitest";
import { clipUrl, API_URL, Task, TaskClip } from "./api";

describe("clipUrl", () => {
  // Mock task as it's not actually used by the current implementation of clipUrl
  const mockTask = {} as Task;

  it("returns null if clip_url is null", () => {
    const mockClip = { clip_url: null } as TaskClip;
    expect(clipUrl(mockTask, mockClip)).toBeNull();
  });

  it("returns null if clip_url is an empty string", () => {
    const mockClip = { clip_url: "" } as TaskClip;
    expect(clipUrl(mockTask, mockClip)).toBeNull();
  });

  it("returns absolute http URLs unmodified", () => {
    const mockClip = { clip_url: "http://example.com/clip.mp4" } as TaskClip;
    expect(clipUrl(mockTask, mockClip)).toBe("http://example.com/clip.mp4");
  });

  it("returns absolute https URLs unmodified", () => {
    const mockClip = { clip_url: "https://example.com/clip.mp4" } as TaskClip;
    expect(clipUrl(mockTask, mockClip)).toBe("https://example.com/clip.mp4");
  });

  it("prepends API_URL to relative paths starting with a slash", () => {
    const mockClip = { clip_url: "/clips/123/clip.mp4" } as TaskClip;
    expect(clipUrl(mockTask, mockClip)).toBe(`${API_URL}/clips/123/clip.mp4`);
  });

  it("prepends API_URL with a slash to relative paths not starting with a slash", () => {
    const mockClip = { clip_url: "clips/123/clip.mp4" } as TaskClip;
    expect(clipUrl(mockTask, mockClip)).toBe(`${API_URL}/clips/123/clip.mp4`);
  });
});
