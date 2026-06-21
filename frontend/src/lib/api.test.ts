import { describe, it, expect } from 'vitest';
import { clipUrl, API_URL, Task, TaskClip } from './api';

describe('clipUrl', () => {
  const dummyTask = {} as Task;

  it('returns null if clip_url is falsy', () => {
    expect(clipUrl(dummyTask, { clip_url: null } as TaskClip)).toBeNull();
    expect(clipUrl(dummyTask, { clip_url: '' } as unknown as TaskClip)).toBeNull();
  });

  it('returns original url if it is absolute http/https', () => {
    expect(clipUrl(dummyTask, { clip_url: 'http://example.com/video.mp4' } as TaskClip)).toBe('http://example.com/video.mp4');
    expect(clipUrl(dummyTask, { clip_url: 'https://example.com/video.mp4' } as TaskClip)).toBe('https://example.com/video.mp4');
  });

  it('prepends API_URL if clip_url is relative with leading slash', () => {
    expect(clipUrl(dummyTask, { clip_url: '/clips/task123/video.mp4' } as TaskClip)).toBe(`${API_URL}/clips/task123/video.mp4`);
  });

  it('prepends API_URL if clip_url is relative without leading slash', () => {
    expect(clipUrl(dummyTask, { clip_url: 'clips/task123/video.mp4' } as TaskClip)).toBe(`${API_URL}/clips/task123/video.mp4`);
  });
});
