export type Health = {
  status: string;
  time: string;
  dropbox_connected: boolean;
  db_reachable: boolean;
};

export type DropboxAccount = {
  name: string;
  email: string;
  account_id: string;
};

export type AuthStatus = {
  connected: boolean;
  account?: DropboxAccount;
  error?: string;
};

export type Photo = {
  id: number;
  dropbox_path: string;
  name: string;
  size_bytes: number;
  content_hash: string | null;
  status: string;
};

export type PhotoListResponse = {
  total: number;
  items: Photo[];
};

export type FoldersResponse = {
  folder: string;
  children: string[];
};

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/healthz"),
  authStatus: () => request<AuthStatus>("/auth/dropbox/status"),
  listPhotos: (limit = 50, offset = 0) =>
    request<PhotoListResponse>(`/photos?limit=${limit}&offset=${offset}`),
  listFolders: (folder = "") =>
    request<FoldersResponse>(`/folders?folder=${encodeURIComponent(folder)}`),
  startIndex: (folder = "") =>
    request<{ started: boolean; folder: string; message: string }>(
      `/index/start?folder=${encodeURIComponent(folder)}`,
      { method: "POST" },
    ),
};

export const startDropboxAuth = () => {
  window.location.href = `${BASE}/auth/dropbox/start`;
};
