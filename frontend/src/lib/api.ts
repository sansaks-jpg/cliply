/** API client for the clip-ai backend.
 *
 * All requests go to NEXT_PUBLIC_API_URL (the FastAPI service). In dev that's
 * http://localhost:8000; in docker-compose it's the backend service name.
 */
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface TaskClip {
  title: string;
  start_time: number;
  end_time: number;
  score: number;
  hook_sentence: string;
  virality_reason: string;
  clip_url: string | null;
  thumbnail_url?: string | null;
  error?: string | null;
}

export interface Task {
  task_id: string;
  url: string;
  num_clips: number;
  aspect_ratio: string;
  language: string | null;
  subtitle_style: string | null;
  status: "queued" | "processing" | "completed" | "error" | "cancelled";
  progress: number;
  stage: string;
  message: string;
  error: string | null;
  clips: TaskClip[];
  created_at: number;
  updated_at: number;
}

export interface CreateTaskResponse {
  task_id: string;
}

export interface CreateTaskOptions {
  num_clips?: number;
  aspect_ratio?: string;
  language?: string;
  subtitle_style?: string;
}

/** Resolve a clip_url returned by the backend into an absolute URL.
 *
 * Backend returns absolute http URLs when it can build them, or a relative
 * "/clips/{task_id}/{filename}" path. Both forms work once prefixed.
 */
export function clipUrl(task: Task, clip: TaskClip): string | null {
  if (!clip.clip_url) return null;
  if (/^https?:\/\//.test(clip.clip_url)) return clip.clip_url;
  return `${API_URL}${clip.clip_url.startsWith("/") ? "" : "/"}${clip.clip_url}`;
}

export async function createTask(
  url: string,
  opts: CreateTaskOptions = {},
): Promise<CreateTaskResponse> {
  const res = await fetch(`${API_URL}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, ...opts }),
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getTask(taskId: string): Promise<Task> {
  const res = await fetch(`${API_URL}/tasks/${taskId}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load task (${res.status})`);
  }
  return res.json();
}
