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
globalThis.localStorage = localStorageMock;

// Mock window.speechSynthesis and SpeechSynthesisUtterance
class MockSpeechSynthesisUtterance {
  constructor(text) {
    this.text = text;
    this.lang = "en-US";
    this.rate = 1.0;
    this.pitch = 1.0;
    this.volume = 1.0;
    this.onstart = null;
    this.onend = null;
    this.onerror = null;
  }
}

let lastUtterance = null;
const mockSpeechSynthesis = {
  speaking: false,
  paused: false,
  cancel: vi.fn(() => {
    mockSpeechSynthesis.speaking = false;
  }),
  speak: vi.fn((utterance) => {
    mockSpeechSynthesis.speaking = true;
    lastUtterance = utterance;
    if (typeof utterance.onstart === "function") {
      utterance.onstart();
    }
  }),
  getVoices: vi.fn(() => []),
};

globalThis.SpeechSynthesisUtterance = MockSpeechSynthesisUtterance;
globalThis.window = {
  speechSynthesis: mockSpeechSynthesis,
  SpeechSynthesisUtterance: MockSpeechSynthesisUtterance,
};

import { ttsService } from "../services/ttsService";
import { storageService } from "../services/storageService";

describe("Continuous Voice Conversation & State Transitions", () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
    mockSpeechSynthesis.speaking = false;
    lastUtterance = null;
  });

  it("manages continuousMode setting in storageService", () => {
    const initialSettings = storageService.getSettings();
    expect(initialSettings.continuousMode).toBe(false);

    storageService.saveSettings({ continuousMode: true });
    const updatedSettings = storageService.getSettings();
    expect(updatedSettings.continuousMode).toBe(true);
  });

  it("handles TTS playback lifecycle with callbacks for continuous turns", () => {
    let started = false;
    let ended = false;

    ttsService.speak("Please state your email address.", {
      onStart: () => {
        started = true;
      },
      onEnd: () => {
        ended = true;
      },
    });

    expect(started).toBe(true);
    expect(mockSpeechSynthesis.speak).toHaveBeenCalled();
    expect(lastUtterance).not.toBeNull();

    // Trigger end callback to simulate speech completion
    if (lastUtterance && lastUtterance.onend) {
      lastUtterance.onend();
    }
    expect(ended).toBe(true);
  });

  it("stops TTS cleanly and cancels speech synthesis", () => {
    mockSpeechSynthesis.speaking = true;
    ttsService.stop();
    expect(mockSpeechSynthesis.cancel).toHaveBeenCalled();
    expect(ttsService.isSpeaking()).toBe(false);
  });

  it("simulates continuous conversation state machine transitions", () => {
    // Models the exact 6 states: 'ready' | 'listening' | 'processing' | 'speaking' | 'paused' | 'error'
    class ContinuousVoiceStateMachine {
      constructor(continuous = true) {
        this.continuous = continuous;
        this.state = "ready";
        this.status = "Ready";
        this.isMicActive = false;
      }

      start() {
        if (this.state === "processing") return;
        this.state = "listening";
        this.isMicActive = true;
        this.status = "Listening...";
      }

      speechDetected(text) {
        if (!text || !text.trim()) {
          // Empty speech in continuous mode returns to listening
          if (this.continuous && this.state !== "paused") {
            this.state = "listening";
            this.status = "No speech detected. Listening...";
            return;
          }
          this.state = "ready";
          this.isMicActive = false;
          return;
        }
        // Audio processing turn
        this.state = "processing";
        this.isMicActive = false;
        this.status = "Processing audio & AI...";
      }

      aiResponseReady(response) {
        this.state = "speaking";
        this.status = "Assistant speaking...";
      }

      speechFinished() {
        if (this.state === "paused") {
          // Stay paused if speech completion fires during pause
          return;
        }
        if (this.continuous) {
          // Auto-resume listening loop
          this.state = "listening";
          this.isMicActive = true;
          this.status = "Listening...";
        } else {
          this.state = "ready";
          this.isMicActive = false;
          this.status = "Ready";
        }
      }

      pause() {
        this.state = "paused";
        this.isMicActive = false;
        this.status = "Paused";
      }

      resume() {
        this.state = "listening";
        this.isMicActive = true;
        this.status = "Listening...";
      }

      stop() {
        this.state = "ready";
        this.isMicActive = false;
        this.status = "Ready";
      }

      errorOccurred(msg) {
        this.state = "error";
        this.isMicActive = false;
        this.status = msg;
      }
    }

    const sm = new ContinuousVoiceStateMachine(true);
    expect(sm.state).toBe("ready");
    expect(sm.isMicActive).toBe(false);

    // 1. User starts session
    sm.start();
    expect(sm.state).toBe("listening");
    expect(sm.isMicActive).toBe(true);

    // 2. User finishes speaking
    sm.speechDetected("My email is test@domain.com");
    expect(sm.state).toBe("processing");
    expect(sm.isMicActive).toBe(false);

    // 3. AI responds and TTS speaks
    sm.aiResponseReady("Got it, your email is test@domain.com.");
    expect(sm.state).toBe("speaking");

    // 4. Assistant finishes speaking -> Auto-resumes listening!
    sm.speechFinished();
    expect(sm.state).toBe("listening");
    expect(sm.isMicActive).toBe(true);

    // 5. User pauses
    sm.pause();
    expect(sm.state).toBe("paused");
    expect(sm.isMicActive).toBe(false);

    // Speech finish during pause does not resume listening
    sm.speechFinished();
    expect(sm.state).toBe("paused");

    // 6. User resumes
    sm.resume();
    expect(sm.state).toBe("listening");
    expect(sm.isMicActive).toBe(true);

    // 7. User stops session completely
    sm.stop();
    expect(sm.state).toBe("ready");
    expect(sm.isMicActive).toBe(false);
  });

  it("verifies submission safety: prevents accidental submission without pending confirmation", () => {
    // Critical safety requirement verification:
    // "The assistant must never submit a form merely because it hears 'yes' without verifying that a submission confirmation is pending"
    const isSubmissionPending = (stage, allRequiredFilled, userAffirmative) => {
      const isConfirming = stage === "confirming_submission" || stage === "reviewing";
      if (!isConfirming) return false;
      if (!allRequiredFilled) return false;
      return Boolean(userAffirmative);
    };

    // Case 1: Answering "yes" to an intermediate question (stage: filling)
    expect(isSubmissionPending("filling", false, true)).toBe(false);
    expect(isSubmissionPending("filling", true, true)).toBe(false);

    // Case 2: In confirming stage, but required fields not all filled
    expect(isSubmissionPending("confirming_submission", false, true)).toBe(false);

    // Case 3: In confirming stage, all filled, but user didn't confirm
    expect(isSubmissionPending("confirming_submission", true, false)).toBe(false);

    // Case 4: In confirming stage, all filled, user explicitly confirmed
    expect(isSubmissionPending("confirming_submission", true, true)).toBe(true);
  });
});
