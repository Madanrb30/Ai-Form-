import { describe, it, expect, beforeEach, vi } from "vitest";

// In Node environment, mock localStorage and sessionStorage
const createStorageMock = () => {
  let store = {};
  return {
    getItem: vi.fn((key) => store[key] || null),
    setItem: vi.fn((key, value) => {
      store[key] = String(value);
    }),
    removeItem: vi.fn((key) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
  };
};

const localStorageMock = createStorageMock();
const sessionStorageMock = createStorageMock();

// Attach to globalThis
globalThis.localStorage = localStorageMock;
globalThis.sessionStorage = sessionStorageMock;

import { authService } from "../services/authService";
import { storageService } from "../services/storageService";

describe("Frontend Services Unit Tests", () => {
  beforeEach(() => {
    localStorageMock.clear();
    sessionStorageMock.clear();
  });

  it("handles user authentication and session persistence", () => {
    const user = authService.login("testuser@example.com", "password123", true);
    expect(user.email).toBe("testuser@example.com");
    expect(user.avatar).toBe("TE");

    const current = authService.getCurrentUser();
    expect(current).not.toBeNull();
    expect(current.email).toBe("testuser@example.com");

    authService.logout();
    expect(localStorageMock.removeItem).toHaveBeenCalledWith("voxform_user_session");
  });

  it("handles form drafts saving, retrieval, and deletion", () => {
    const draftData = { full_name: "Madan RB", email: "madan@test.com" };
    storageService.saveDraft(101, draftData, "Test Form");

    const retrieved = storageService.getDraft(101);
    expect(retrieved).not.toBeNull();
    expect(retrieved.values.full_name).toBe("Madan RB");
    expect(storageService.getDraftsCount()).toBe(1);

    storageService.deleteDraft(101);
    expect(storageService.getDraft(101)).toBeNull();
    expect(storageService.getDraftsCount()).toBe(0);
  });

  it("handles app voice settings updates", () => {
    const defaults = storageService.getSettings();
    expect(defaults.language).toBe("en-US");

    storageService.saveSettings({ language: "ta-IN", voicePlayback: true });
    const updated = storageService.getSettings();
    expect(updated.language).toBe("ta-IN");
    expect(updated.voicePlayback).toBe(true);
  });
});
