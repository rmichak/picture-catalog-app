import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, startDropboxAuth } from "../api/client";

export default function Settings() {
  const qc = useQueryClient();
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.authStatus });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const [folder, setFolder] = useState("");

  const indexMutation = useMutation({
    mutationFn: () => api.startIndex(folder),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["photos"] }),
  });

  return (
    <div className="space-y-8 max-w-2xl">
      <section>
        <h2 className="text-2xl font-semibold mb-3">Settings</h2>
        <p className="text-sm text-neutral-400">
          Connect Dropbox, then point the indexer at a folder to start cataloging.
        </p>
      </section>

      <section className="space-y-3 border border-neutral-800 rounded-lg p-5">
        <h3 className="font-semibold">Dropbox</h3>
        {auth.data?.connected ? (
          <div className="text-sm space-y-1">
            <p className="text-emerald-400">Connected</p>
            <p className="text-neutral-300">{auth.data.account?.name}</p>
            <p className="text-neutral-500 text-xs">{auth.data.account?.email}</p>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-neutral-300">
              Not connected. Click below to authorize this app on your Dropbox account.
            </p>
            <button
              onClick={startDropboxAuth}
              className="px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium"
            >
              Connect Dropbox
            </button>
          </div>
        )}
      </section>

      <section className="space-y-3 border border-neutral-800 rounded-lg p-5">
        <h3 className="font-semibold">Indexer</h3>
        <p className="text-sm text-neutral-400">
          Folder path inside Dropbox to scan (leave blank for the entire app folder, or enter a path
          like <code className="text-neutral-200">/Photos</code>).
        </p>
        <input
          value={folder}
          onChange={(e) => setFolder(e.target.value)}
          placeholder="/Photos"
          className="w-full px-3 py-2 rounded bg-neutral-900 border border-neutral-700 text-sm"
          disabled={!auth.data?.connected}
        />
        <button
          disabled={!auth.data?.connected || indexMutation.isPending}
          onClick={() => indexMutation.mutate()}
          className="px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-500 disabled:bg-neutral-700 disabled:text-neutral-400 text-white text-sm font-medium"
        >
          {indexMutation.isPending ? "Starting…" : "Start indexing"}
        </button>
        {indexMutation.data && (
          <p className="text-xs text-neutral-400">{indexMutation.data.message}</p>
        )}
        {indexMutation.error && (
          <p className="text-xs text-red-400">{String(indexMutation.error)}</p>
        )}
      </section>

      <section className="space-y-2 border border-neutral-800 rounded-lg p-5">
        <h3 className="font-semibold">Health</h3>
        <pre className="text-xs text-neutral-400 bg-neutral-950 p-3 rounded overflow-auto">
          {JSON.stringify(health.data, null, 2)}
        </pre>
      </section>
    </div>
  );
}
