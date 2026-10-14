import React, { useState } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";

export default function AppLayout({ currentView, setView, children, searchQuery, setSearchQuery }) {
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-white text-[#111111] flex flex-row font-sans antialiased">
      {/* Sidebar (Desktop + Mobile drawer) */}
      <Sidebar
        currentView={currentView}
        setView={setView}
        isMobileOpen={isMobileOpen}
        setIsMobileOpen={setIsMobileOpen}
      />

      {/* Main Workspace Area */}
      <div className="flex-1 flex flex-col min-w-0 min-h-screen bg-[#FFFFFF]">
        <Header
          currentView={currentView}
          setView={setView}
          onOpenMobileMenu={() => setIsMobileOpen(true)}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
        />

        <main className="flex-1 bg-[#FFFFFF] overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
