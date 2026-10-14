import React, { useEffect, useState, useCallback } from "react";
import { api } from "../services/api";

export default function Header({ currentView, setView }) {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkHealth = useCallback(async () => {
    try {
      const data = await api.getHealth();
      setHealth(data);
    } catch {
      setHealth(null);
    } finally {
      setLoading(false);
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
        if (!ignore) setLoading(false);
      });

    const interval = setInterval(checkHealth, 30000);
    return () => {
      ignore = true;
      clearInterval(interval);
    };
  }, [checkHealth]);

  return (
    <header className="border-b border-zinc-200 bg-white sticky top-0 z-30">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-6">
          <div
            onClick={() => setView({ name: "dashboard" })}
            className="cursor-pointer flex items-center space-x-2"
          >
            <div className="w-8 h-8 bg-black text-white flex items-center justify-center font-bold text-sm tracking-wider">
              VF
            </div>
            <span className="font-semibold text-lg text-black tracking-tight">
              VOXFORM
            </span>
          </div>

          <nav className="flex space-x-2 text-sm">
            <button
              onClick={() => setView({ name: "dashboard" })}
              className={`px-3 py-1.5 rounded-sm transition-colors ${
                currentView.name === "dashboard"
                  ? "bg-zinc-100 font-medium text-black"
                  : "text-zinc-600 hover:text-black hover:bg-zinc-50"
              }`}
            >
              Forms
            </button>
            <button
              onClick={() => setView({ name: "generate" })}
              className={`px-3 py-1.5 rounded-sm transition-colors ${
                currentView.name === "generate"
                  ? "bg-zinc-100 font-medium text-black"
                  : "text-zinc-600 hover:text-black hover:bg-zinc-50"
              }`}
            >
              + Create with AI
            </button>
          </nav>
        </div>

        <div className="flex items-center space-x-3 text-xs">
          {loading ? (
            <span className="text-zinc-400">Checking server...</span>
          ) : health?.status === "ok" ? (
            <div className="flex items-center space-x-2 border border-zinc-200 px-2.5 py-1 bg-zinc-50">
              <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block"></span>
              <span className="text-zinc-700 font-mono">
                {health.ai_mode === "gemini" ? "AI: Gemini Active" : "AI: Demo Mode"}
              </span>
            </div>
          ) : (
            <div className="flex items-center space-x-2 border border-red-200 px-2.5 py-1 bg-red-50 text-red-600">
              <span className="w-2 h-2 rounded-full bg-red-500 inline-block"></span>
              <span>Backend Offline</span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
