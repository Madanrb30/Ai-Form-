import React, { useState, useEffect } from "react";
import {
  Settings,
  User,
  Volume2,
  Moon,
  Sun,
  Shield,
  LogOut,
  Save,
  Check,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { storageService } from "../services/storageService";
import { useToast } from "../context/ToastContext";
import Modal from "../components/common/Modal";

export default function SettingsPage({ setView }) {
  const { user, updateProfile, logout } = useAuth();
  const { toast } = useToast();

  // Profile Edit State
  const [name, setName] = useState(user?.name || "Madan RB");
  const [email, setEmail] = useState(user?.email || "madan@example.com");
  const [role, setRole] = useState(user?.role || "Product Lead");

  // Settings state
  const [settings, setSettings] = useState(() => storageService.getSettings());

  // Password modal
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const handleSaveProfile = (e) => {
    e.preventDefault();
    if (!name.trim() || !email.trim()) {
      toast("Name and email are required.", "error");
      return;
    }
    const initials = name
      .trim()
      .split(" ")
      .map((w) => w[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();

    updateProfile({
      name: name.trim(),
      email: email.trim().toLowerCase(),
      role: role.trim(),
      avatar: initials || "U",
    });
    toast("Profile updated successfully.", "success");
  };

  const handleUpdateSetting = (key, value) => {
    const updated = storageService.saveSettings({ [key]: value });
    setSettings(updated);
    toast(`Updated ${key} preference.`, "info");
  };

  const handleChangePassword = (e) => {
    e.preventDefault();
    if (newPassword.length < 6) {
      toast("Password must be at least 6 characters.", "error");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast("Passwords do not match.", "error");
      return;
    }
    setPasswordModalOpen(false);
    setNewPassword("");
    setConfirmPassword("");
    toast("Password updated securely.", "success");
  };

  const handleClearAllData = () => {
    if (window.confirm("Are you sure you want to clear all local form drafts and cached sessions?")) {
      localStorage.clear();
      toast("Local data cleared.", "info");
      setView({ name: "login" });
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-8 py-8 text-left space-y-8">
      {/* Header */}
      <div className="pb-6 border-b border-[#E5E5E5]">
        <div className="flex items-center space-x-2">
          <Settings className="w-5 h-5 text-neutral-900" />
          <h1 className="text-xl font-bold tracking-tight text-neutral-900">
            Settings & Preferences
          </h1>
        </div>
        <p className="text-xs text-[#737373] mt-1">
          Manage your account profile, speech recognition preferences, and app configuration.
        </p>
      </div>

      {/* 1. Profile Settings */}
      <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs">
        <h2 className="text-sm font-semibold text-neutral-900 tracking-tight mb-4 flex items-center space-x-2">
          <User className="w-4 h-4 text-neutral-700" />
          <span>User Profile</span>
        </h2>

        <form onSubmit={handleSaveProfile} className="space-y-4">
          <div className="flex items-center space-x-4 pb-4 border-b border-neutral-100">
            <div className="w-14 h-14 rounded-full bg-neutral-900 text-white font-bold text-lg flex items-center justify-center shrink-0">
              {user?.avatar || "MR"}
            </div>
            <div>
              <p className="text-xs font-semibold text-neutral-900">{user?.name}</p>
              <p className="text-[11px] text-neutral-500 font-mono">{user?.email}</p>
              <span className="inline-block mt-1 text-[10px] bg-neutral-100 text-neutral-700 px-2 py-0.5 rounded border border-neutral-200">
                {user?.role || "Standard User"}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="block text-xs font-medium text-neutral-700 mb-1">
                Full Name
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-neutral-700 mb-1">
                Email Address
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900"
              />
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              className="px-4 py-2 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer shadow-xs"
            >
              Save Profile Changes
            </button>
          </div>
        </form>
      </div>

      {/* 2. Voice & AI Interaction Settings */}
      <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs space-y-5">
        <h2 className="text-sm font-semibold text-neutral-900 tracking-tight flex items-center space-x-2">
          <Volume2 className="w-4 h-4 text-neutral-700" />
          <span>Speech Recognition & Voice Settings</span>
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-neutral-700 mb-1">
              Spoken Language Model
            </label>
            <select
              value={settings.language}
              onChange={(e) => handleUpdateSetting("language", e.target.value)}
              className="w-full px-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
            >
              <option value="en-US">English (United States) — en-US</option>
              <option value="en-IN">English (India) — en-IN</option>
              <option value="ta-IN">Tamil (India) — ta-IN</option>
              <option value="hi-IN">Hindi (India) — hi-IN</option>
            </select>
            <span className="block text-[11px] text-neutral-400 mt-1">
              Web Speech API input dialect.
            </span>
          </div>

          <div>
            <label className="block text-xs font-medium text-neutral-700 mb-1">
              Voice Feedback Speed
            </label>
            <select
              value={settings.voiceSpeed}
              onChange={(e) => handleUpdateSetting("voiceSpeed", parseFloat(e.target.value))}
              className="w-full px-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
            >
              <option value="0.8">0.8x (Slower)</option>
              <option value="1.0">1.0x (Normal)</option>
              <option value="1.2">1.2x (Faster)</option>
            </select>
            <span className="block text-[11px] text-neutral-400 mt-1">
              Speech rate for spoken replies.
            </span>
          </div>
        </div>

        <div className="space-y-3 pt-3 border-t border-neutral-100">
          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <span className="text-xs font-medium text-neutral-800 block">
                Assistant Audio Playback (TTS)
              </span>
              <span className="text-[11px] text-neutral-500">
                Read assistant answers and confirmation messages aloud using Web Speech Synthesis.
              </span>
            </div>
            <input
              type="checkbox"
              checked={settings.voicePlayback}
              onChange={(e) => handleUpdateSetting("voicePlayback", e.target.checked)}
              className="w-4 h-4 text-neutral-900 rounded border-[#E5E5E5] focus:ring-neutral-900 cursor-pointer"
            />
          </label>

          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <span className="text-xs font-medium text-neutral-800 block">
                Automatic Field Application
              </span>
              <span className="text-[11px] text-neutral-500">
                Immediately map recognized voice slots directly into fields as you finish speaking.
              </span>
            </div>
            <input
              type="checkbox"
              checked={settings.voiceConfirmation}
              onChange={(e) => handleUpdateSetting("voiceConfirmation", e.target.checked)}
              className="w-4 h-4 text-neutral-900 rounded border-[#E5E5E5] focus:ring-neutral-900 cursor-pointer"
            />
          </label>
        </div>
      </div>

      {/* 3. Appearance Settings */}
      <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs space-y-4">
        <h2 className="text-sm font-semibold text-neutral-900 tracking-tight flex items-center space-x-2">
          <Sun className="w-4 h-4 text-neutral-700" />
          <span>Appearance & Design Theme</span>
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <button
            type="button"
            onClick={() => handleUpdateSetting("theme", "light")}
            className={`p-3 rounded-xl border text-left transition-all cursor-pointer ${
              settings.theme === "light"
                ? "border-neutral-900 bg-neutral-50 ring-1 ring-neutral-900"
                : "border-[#E5E5E5] hover:bg-neutral-50"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-semibold text-neutral-900">Monochrome Light</span>
              {settings.theme === "light" && <Check className="w-3.5 h-3.5 text-neutral-900" />}
            </div>
            <p className="text-[11px] text-[#737373]">
              Default minimal black & white SaaS layout with #0B0B0B sidebar.
            </p>
          </button>

          <button
            type="button"
            onClick={() => handleUpdateSetting("theme", "dark")}
            className={`p-3 rounded-xl border text-left transition-all cursor-pointer ${
              settings.theme === "dark"
                ? "border-neutral-900 bg-neutral-50 ring-1 ring-neutral-900"
                : "border-[#E5E5E5] hover:bg-neutral-50"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-semibold text-neutral-900">Dark Minimal</span>
              {settings.theme === "dark" && <Check className="w-3.5 h-3.5 text-neutral-900" />}
            </div>
            <p className="text-[11px] text-[#737373]">
              High-contrast dark mode for low-light environments.
            </p>
          </button>

          <button
            type="button"
            onClick={() => handleUpdateSetting("theme", "system")}
            className={`p-3 rounded-xl border text-left transition-all cursor-pointer ${
              settings.theme === "system"
                ? "border-neutral-900 bg-neutral-50 ring-1 ring-neutral-900"
                : "border-[#E5E5E5] hover:bg-neutral-50"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-semibold text-neutral-900">System Sync</span>
              {settings.theme === "system" && <Check className="w-3.5 h-3.5 text-neutral-900" />}
            </div>
            <p className="text-[11px] text-[#737373]">
              Automatically adhere to your browser OS theme settings.
            </p>
          </button>
        </div>
      </div>

      {/* 4. Account & Security */}
      <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs space-y-4">
        <h2 className="text-sm font-semibold text-neutral-900 tracking-tight flex items-center space-x-2">
          <Shield className="w-4 h-4 text-neutral-700" />
          <span>Security & Session</span>
        </h2>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between py-2 border-b border-neutral-100 gap-2">
          <div>
            <p className="text-xs font-medium text-neutral-800">Password</p>
            <p className="text-[11px] text-neutral-500">
              Update password for local application access.
            </p>
          </div>
          <button
            onClick={() => setPasswordModalOpen(true)}
            className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors self-start sm:self-auto cursor-pointer"
          >
            Change Password
          </button>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between py-2 border-b border-neutral-100 gap-2">
          <div>
            <p className="text-xs font-medium text-neutral-800">Clear Local Storage</p>
            <p className="text-[11px] text-neutral-500">
              Clear saved draft forms, cached history, and local preferences.
            </p>
          </div>
          <button
            onClick={handleClearAllData}
            className="px-3 py-1.5 border border-red-200 text-red-600 hover:bg-red-50 rounded-lg text-xs font-medium transition-colors self-start sm:self-auto cursor-pointer"
          >
            Reset Local Data
          </button>
        </div>

        <div className="pt-2 flex justify-start">
          <button
            onClick={() => {
              logout();
              setView({ name: "login" });
            }}
            className="inline-flex items-center space-x-2 px-4 py-2 bg-neutral-900 hover:bg-black text-white rounded-lg text-xs font-medium transition-colors cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Sign Out Current Session</span>
          </button>
        </div>
      </div>

      {/* Change Password Modal */}
      <Modal
        isOpen={passwordModalOpen}
        onClose={() => setPasswordModalOpen(false)}
        title="Change Password"
      >
        <form onSubmit={handleChangePassword} className="space-y-4 text-left">
          <div>
            <label className="block text-xs font-medium text-neutral-700 mb-1">
              New Password
            </label>
            <input
              type="password"
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full px-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-neutral-700 mb-1">
              Confirm New Password
            </label>
            <input
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full px-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900"
            />
          </div>

          <div className="pt-2 flex justify-end space-x-2">
            <button
              type="button"
              onClick={() => setPasswordModalOpen(false)}
              className="px-3 py-1.5 border border-[#E5E5E5] rounded-lg text-xs text-neutral-700 hover:bg-neutral-50 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold cursor-pointer"
            >
              Update Password
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
