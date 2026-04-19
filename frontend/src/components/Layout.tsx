import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

const navItem =
  "px-3 py-2 rounded text-sm hover:bg-neutral-800 transition";
const navItemActive = "bg-neutral-800 text-white";

export default function Layout() {
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.authStatus, refetchInterval: 30_000 });

  return (
    <div className="min-h-full grid grid-rows-[auto_1fr]">
      <header className="border-b border-neutral-800 bg-neutral-900">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-lg font-semibold">picture-catalog-app</h1>
            <nav className="flex items-center gap-1">
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  `${navItem} ${isActive ? navItemActive : "text-neutral-300"}`
                }
              >
                Library
              </NavLink>
              <NavLink
                to="/settings"
                className={({ isActive }) =>
                  `${navItem} ${isActive ? navItemActive : "text-neutral-300"}`
                }
              >
                Settings
              </NavLink>
            </nav>
          </div>
          <div className="text-xs text-neutral-400">
            {auth.data?.connected ? (
              <span className="text-emerald-400">
                ● Dropbox: {auth.data.account?.email ?? "connected"}
              </span>
            ) : (
              <span className="text-amber-400">● Dropbox: not connected</span>
            )}
          </div>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-6 w-full">
        <Outlet />
      </main>
    </div>
  );
}
