import React, { useEffect } from "react";
import { X } from "lucide-react";

export default function Modal({ isOpen, onClose, title, children, maxWidth = "max-w-md" }) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      document.body.style.overflow = "hidden";
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.body.style.overflow = "auto";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-xs transition-opacity"
        onClick={onClose}
      />

      {/* Modal Card */}
      <div
        className={`relative bg-white border border-[#E5E5E5] rounded-xl shadow-2xl w-full ${maxWidth} z-10 p-6 text-left transform transition-all animate-in fade-in zoom-in-95 duration-150`}
      >
        <div className="flex items-center justify-between pb-3 border-b border-[#E5E5E5] mb-4">
          <h3 className="text-sm font-semibold text-neutral-900 tracking-tight">
            {title}
          </h3>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-900 p-1 rounded-md hover:bg-neutral-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div>{children}</div>
      </div>
    </div>
  );
}
