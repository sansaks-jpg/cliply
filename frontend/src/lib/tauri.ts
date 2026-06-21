"use client";

export interface AppSettings {
  storage_dir: string;
  first_run: boolean;
  gemini_api_key: string;
  openai_api_key: string;
  openai_base_url: string;
  llm_provider: string;
}

export function isTauri(): boolean {
  return typeof window !== 'undefined' && (!!(window as any).__TAURI__ || !!(window as any).__TAURI_INTERNALS__);
}

async function getInvoke() {
  const { invoke } = await import('@tauri-apps/api/core');
  return invoke;
}

export async function getSettings(): Promise<AppSettings | null> {
  if (!isTauri()) return null;
  try {
    const invoke = await getInvoke();
    return await invoke<AppSettings>("get_settings");
  } catch (error) {
    console.error("Failed to get settings:", error);
    return null;
  }
}

export async function setStorageDir(path: string): Promise<void> {
  if (!isTauri()) return;
  try {
    const invoke = await getInvoke();
    await invoke("set_storage_dir", { path });
  } catch (error) {
    console.error("Failed to set storage dir:", error);
  }
}

export async function saveAppSettings(settings: AppSettings): Promise<void> {
  if (!isTauri()) return;
  try {
    const invoke = await getInvoke();
    await invoke("save_app_settings", { newSettings: settings });
  } catch (error) {
    console.error("Failed to save settings:", error);
  }
}

export async function pickStorageDir(): Promise<string | null> {
  if (!isTauri()) return null;
  try {
    const invoke = await getInvoke();
    return await invoke<string | null>("pick_storage_dir");
  } catch (error) {
    console.error("Failed to pick storage dir:", error);
    return null;
  }
}

export async function openStorageDir(path: string): Promise<void> {
  if (!isTauri()) return;
  try {
    const invoke = await getInvoke();
    await invoke("open_storage_dir", { path });
  } catch (error) {
    console.error("Failed to open storage dir:", error);
  }
}

export async function restartBackend(storagePath: string): Promise<void> {
  if (!isTauri()) return;
  try {
    const invoke = await getInvoke();
    await invoke("restart_backend", { storagePath });
  } catch (error) {
    console.error("Failed to restart backend:", error);
  }
}

export async function relaunchApp(): Promise<void> {
  if (!isTauri()) return;
  try {
    const invoke = await getInvoke();
    await invoke("relaunch_app");
  } catch (error) {
    console.error("Failed to relaunch app:", error);
  }
}
