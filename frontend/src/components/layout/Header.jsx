import React, { useEffect, useState, useCallback } from "react";
import { Menu, Bell, Search, Mic, CheckCircle2, AlertCircle } from "lucide-react";
import { api } from "../../services/api";

export default function Header({ currentView, setView, onOpenMobileMenu, searchQuery, setSearchQuery }) {
  const [health, setHealth] = useState(null);
  const [checking, setChecking] = useState(true);

  const checkHealth = useCallback(async () => {
    try {
      const data = await api.getHealth();
      setHealth(data);
    } catch {
      setHealth(null);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    api
      .getHealth()
      .then((data) => {
        if (!ignore) setHealth(data);
      })
      .catch(() => {
        if (!ignore) setHealth(null);
      })
      .finally(() => {
        if (!ignore) setChecking(false);
      });

    const interval = setInterval(checkHealth, 25000);
    return () => {
      ignore = true;
      clearInterval(interval);
    };
  }, [checkHealth]);

  return (
    <header className="h-14 border-b border-[#E5E5E5] bg-white sticky top-0 z-10 px-4 sm:px-6 flex items-center justify-between">
      {/* Left: Mobile Menu & Breadcrumb */}
      <div className="flex items-center space-x-3">
        <button
          onClick={onOpenMobileMenu}
          className="lg:hidden p-1.5 -ml-1 text-neutral-600 hover:text-black rounded-md hover:bg-neutral-100 cursor-pointer"
          aria-label="Open navigation menu"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div className="flex items-center space-x-2 text-xs">
          <span className="font-semibold text-neutral-900 tracking-tight capitalize">
            {currentView.name === "dashboard"
              ? "Dashboard"
              : currentView.name === "create"
              ? "Create Form"
              : currentView.name === "fill"
              ? "AI Voice Assistant"
              : currentView.name === "editor"
              ? "Form Editor"
              : currentView.name === "review"
              ? "Review & Submit"
              : currentView.name === "history"
              ? "Form History"
              : currentView.name === "settings"
              ? "Settings"
              : currentView.name}
          </span>
          {currentView.formTitle && (
            <>
              <span className="text-neutral-400">/</span>
              <span className="text-neutral-600 truncate max-w-[200px]">
                {currentView.formTitle}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Right: Quick Search, Backend Status, Notification */}
      <div className="flex items-center space-x-3 sm:space-x-4">
        {setSearchQuery && (
          <div className="hidden md:flex items-center relative">
            <Search className="w-3.5 h-3.5 text-neutral-400 absolute left-2.5 pointer-events-none" />
            <input
              type="text"
              placeholder="Search forms..."
              value={searchQuery || ""}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-3 py-1 text-xs border border-[#E5E5E5] rounded-md bg-[#F7F7F7] focus:bg-white focus:outline-none focus:border-neutral-900 w-44 transition-all"
            />
          </div>
        )}

        {/* Backend health status pill */}
        <div className="flex items-center">
          {checking ? (
            <span className="text-[11px] text-neutral-400 font-mono">Checking API...</span>
          ) : health?.status === "ok" ? (
            <div
              className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full bg-neutral-100 border border-neutral-200 text-[11px] text-neutral-800 font-mono"
              title="FastAPI server is connected and ready"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="hidden sm:inline">
                {health.ai_mode === "gemini" ? "Gemini AI" : "AI Ready"}
              </span>
              <span className="sm:hidden">Online</span>
            </div>
          ) : (
            <div
              className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full bg-red-50 border border-red-200 text-[11px] text-red-700"
              title="FastAPI server is unreachable. Check port 8090."
            >
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
              <span>Backend Offline</span>
            </div>
          )}
        </div>

        {/* Voice Assistant Shortcut Button */}
        {currentView.name !== "fill" && (
          <button
            onClick={() => setView({ name: "forms" })}
            className="hidden sm:flex items-center space-x-1.5 text-xs text-neutral-600 hover:text-black px-2.5 py-1 rounded-md border border-[#E5E5E5] hover:bg-[#F7F7F7] transition-colors cursor-pointer"
            title="Start voice form filling"
          >
            <Mic className="w-3 h-3 text-neutral-800" />
            <span>Voice Fill</span>
          </button>
        )}

        {/* Notification bell button */}
        <button
          className="p-1 text-neutral-400 hover:text-neutral-800 rounded-md hover:bg-neutral-100 transition-colors"
          title="Notifications"
        >
          <Bell className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
