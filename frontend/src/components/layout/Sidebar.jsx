import React from "react";
import {
  LayoutDashboard,
  FileText,
  PlusCircle,
  History,
  Settings,
  LogOut,
  Sparkles,
  ChevronRight,
  ShieldCheck,
  X,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";

export default function Sidebar({ currentView, setView, isMobileOpen, setIsMobileOpen }) {
  const { user, logout, isAdmin } = useAuth();

  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "forms", label: "My Forms", icon: FileText },
    { id: "create", label: "Create Form", icon: PlusCircle },
    { id: "history", label: "History", icon: History },
    { id: "settings", label: "Settings", icon: Settings },
    ...(isAdmin ? [{ id: "admin", label: "Admin Console", icon: ShieldCheck }] : []),
  ];

  const handleNavClick = (viewName) => {
    setView({ name: viewName });
    if (setIsMobileOpen) setIsMobileOpen(false);
  };

  const handleLogout = () => {
    logout();
    setView({ name: "login" });
    if (setIsMobileOpen) setIsMobileOpen(false);
  };

  const content = (
    <div className="h-full flex flex-col justify-between bg-[#0B0B0B] text-[#F5F5F5] select-none border-r border-neutral-900">
      {/* Brand & Top Header */}
      <div>
        <div className="p-5 flex items-center justify-between border-b border-neutral-900/80">
          <button
            onClick={() => handleNavClick("dashboard")}
            className="flex items-center space-x-3 text-left focus:outline-none group cursor-pointer"
          >
            <div className="w-9 h-9 rounded-lg bg-neutral-900 border border-neutral-800 flex items-center justify-center text-white shadow-inner group-hover:border-neutral-700 transition-colors">
              <Sparkles className="w-4 h-4 text-neutral-200" />
            </div>
            <div>
              <span className="font-semibold text-sm tracking-tight text-white block">
                AI Form Assistant
              </span>
              <span className="text-[11px] font-mono text-neutral-400 block -mt-0.5">
                v1.0 • Monochrome
              </span>
            </div>
          </button>

          {setIsMobileOpen && (
            <button
              onClick={() => setIsMobileOpen(false)}
              className="lg:hidden p-1.5 text-neutral-400 hover:text-white rounded-md"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Navigation Items */}
        <nav className="p-3 space-y-1 mt-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive =
              currentView.name === item.id ||
              (item.id === "forms" && ["fill", "editor", "review", "submissions"].includes(currentView.name));

            return (
              <button
                key={item.id}
                onClick={() => handleNavClick(item.id)}
                className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-lg text-xs font-medium transition-all group cursor-pointer ${
                  isActive
                    ? "bg-neutral-800/90 text-white shadow-xs border border-neutral-700/60"
                    : "text-neutral-400 hover:text-neutral-100 hover:bg-neutral-900/60"
                }`}
              >
                <div className="flex items-center space-x-3">
                  <Icon
                    className={`w-4 h-4 transition-colors ${
                      isActive ? "text-white" : "text-neutral-500 group-hover:text-neutral-300"
                    }`}
                  />
                  <span>{item.label}</span>
                </div>
                {isActive && (
                  <ChevronRight className="w-3.5 h-3.5 text-neutral-400" />
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* User Section & Logout */}
      <div className="p-3 border-t border-neutral-900/90 bg-[#090909]">
        <div className="p-2.5 rounded-lg bg-neutral-900/70 border border-neutral-800/80 flex items-center justify-between mb-2">
          <div className="flex items-center space-x-2.5 min-w-0">
            <div className="w-8 h-8 rounded-full bg-neutral-800 border border-neutral-700 flex items-center justify-center text-xs font-semibold text-neutral-200 shrink-0">
              {user?.avatar || "MR"}
            </div>
            <div className="truncate text-left">
              <p className="text-xs font-medium text-neutral-200 truncate">
                {user?.name || "Madan RB"}
              </p>
              <p className="text-[11px] text-neutral-500 truncate font-mono">
                {user?.email || "madan@example.com"}
              </p>
              {user?.role && (
                <span className="inline-block mt-0.5 px-1.5 py-0.2 rounded text-[9px] font-mono font-medium uppercase tracking-wider bg-neutral-800 text-neutral-300 border border-neutral-700/60">
                  {user.role}
                </span>
              )}
            </div>
          </div>
        </div>

        <button
          onClick={handleLogout}
          className="w-full flex items-center space-x-2.5 px-3 py-2 rounded-lg text-xs font-medium text-neutral-400 hover:text-red-400 hover:bg-red-950/20 transition-colors cursor-pointer"
        >
          <LogOut className="w-3.5 h-3.5" />
          <span>Sign Out</span>
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Sidebar */}
      <aside className="hidden lg:block w-64 h-screen sticky top-0 shrink-0 z-20">
        {content}
      </aside>

      {/* Mobile Backdrop & Drawer */}
      {isMobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div
            className="fixed inset-0 bg-black/60 backdrop-blur-xs transition-opacity"
            onClick={() => setIsMobileOpen(false)}
          />
          <div className="relative w-72 max-w-[80vw] h-full shadow-2xl z-10 animate-in slide-in-from-left duration-200">
            {content}
          </div>
        </div>
      )}
    </>
  );
}
