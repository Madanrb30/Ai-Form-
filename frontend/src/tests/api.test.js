import { describe, it, expect, vi, beforeEach } from "vitest";

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
globalThis.localStorage = localStorageMock;
globalThis.sessionStorage = sessionStorageMock;

import { api } from "../services/api";

describe("Frontend API Service Unit Tests", () => {
  beforeEach(() => {
    localStorageMock.clear();
    sessionStorageMock.clear();
    vi.restoreAllMocks();
  });

  it("handles successful health check response", async () => {
    const mockHealth = {
      status: "ok",
      service: "AI Voice Form Builder",
      database: "healthy",
      ai_mode: "demo",
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: {
        get: () => "application/json",
      },
      json: async () => mockHealth,
    });

    const res = await api.getHealth();
    expect(res.status).toBe("ok");
    expect(res.ai_mode).toBe("demo");
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/health"),
      expect.any(Object)
    );
  });

  it("throws friendly ApiError when backend returns 400 with details", async () => {
    const errorPayload = {
      detail: {
        message: "Form validation failed",
        errors: ["'Full Name' is required."],
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      headers: {
        get: () => "application/json",
      },
      json: async () => errorPayload,
    });

    await expect(api.createSubmission(1, {})).rejects.toThrow("Form validation failed");
  });

  it("throws connection error if network is completely down", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("Failed to fetch"));

    await expect(api.getForms()).rejects.toThrow("Cannot connect to backend server");
  });

  it("sends audio blob to /voice/transcribe and parses response", async () => {
    const mockTranscribe = {
      text: "My name is Madan",
      model: "whisper-large-v3-turbo",
      duration: 2.5,
      language: "en",
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: {
        get: () => "application/json",
      },
      json: async () => mockTranscribe,
    });

    const dummyBlob = new Blob(["dummy-audio-content"], { type: "audio/webm" });
    const res = await api.transcribeAudio(dummyBlob, { language: "en" });

    expect(res.text).toBe("My name is Madan");
    expect(res.model).toBe("whisper-large-v3-turbo");
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/voice/transcribe"),
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData),
      })
    );
  });

  it("ignores mock sess_ tokens and does not attach them in Authorization header", async () => {
    localStorage.setItem("voxform_user_session", JSON.stringify({ token: "sess_placeholder_123" }));

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: async () => [],
    });

    await api.getForms();

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/forms"),
      expect.objectContaining({
        headers: expect.not.objectContaining({
          Authorization: expect.stringContaining("sess_"),
        }),
      })
    );
    localStorage.clear();
  });

  it("attaches real JWT Bearer token in Authorization header", async () => {
    localStorage.setItem("voxform_user_session", JSON.stringify({ token: "eyJhbGciOiJIUzI1NiJ9.payload.sig" }));

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: async () => [],
    });

    await api.getForms();

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/forms"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig",
        }),
      })
    );
    localStorage.clear();
  });

  it("clears stale session storage when server returns 401 Unauthorized", async () => {
    localStorage.setItem("voxform_user_session", JSON.stringify({ token: "expired.jwt.token" }));

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      headers: { get: () => "application/json" },
      json: async () => ({ detail: "Invalid authentication token." }),
    });

    await expect(api.getForms()).rejects.toThrow("Invalid authentication token.");
    expect(localStorage.getItem("voxform_user_session")).toBeNull();
  });
});

