import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

export default function Library() {
  const photos = useQuery({
    queryKey: ["photos"],
    queryFn: () => api.listPhotos(100, 0),
    refetchInterval: 5_000,
  });

  if (photos.isLoading) {
    return <p className="text-neutral-400">Loading…</p>;
  }
  if (photos.error) {
    return <p className="text-red-400">Error: {String(photos.error)}</p>;
  }

  const total = photos.data?.total ?? 0;
  const items = photos.data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-2xl font-semibold">Library</h2>
        <p className="text-sm text-neutral-400">{total.toLocaleString()} photos cataloged</p>
      </div>

      {items.length === 0 ? (
        <div className="border border-dashed border-neutral-700 rounded-lg p-8 text-center text-neutral-400">
          <p className="mb-2">No photos cataloged yet.</p>
          <p className="text-sm">
            Connect Dropbox in <span className="text-neutral-200">Settings</span> and start indexing.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-neutral-800 border border-neutral-800 rounded-lg overflow-hidden">
          {items.map((p) => (
            <li key={p.id} className="px-4 py-3 flex items-center justify-between hover:bg-neutral-900">
              <div className="min-w-0">
                <p className="text-sm truncate">{p.name}</p>
                <p className="text-xs text-neutral-500 truncate">{p.dropbox_path}</p>
              </div>
              <div className="text-xs text-neutral-500 ml-4 shrink-0">
                <span className="px-2 py-0.5 rounded bg-neutral-800">{p.status}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
