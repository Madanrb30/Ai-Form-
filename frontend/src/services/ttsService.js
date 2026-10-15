// Web Speech API text-to-speech synthesis service
export const ttsService = {
  _isCancelled: false,

  isSupported() {
    return typeof window !== "undefined" && "speechSynthesis" in window;
  },

  getVoices() {
    if (!this.isSupported()) return [];
    return window.speechSynthesis.getVoices() || [];
  },

  speak(text, options = {}) {
    if (!this.isSupported() || !text) {
      if (typeof options.onEnd === "function") {
        setTimeout(options.onEnd, 50);
      }
      return;
    }

    try {
      this._isCancelled = false;
      window.speechSynthesis.cancel(); // Stop any pending utterances

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = options.rate || 1.0;
      utterance.pitch = options.pitch || 1.0;
      utterance.lang = options.lang || "en-US";

      if (typeof options.onStart === "function") {
        utterance.onstart = () => {
          if (!this._isCancelled && typeof options.onStart === "function") {
            options.onStart();
          }
        };
      }

      utterance.onend = () => {
        if (!this._isCancelled && typeof options.onEnd === "function") {
          options.onEnd();
        }
      };

      utterance.onerror = (e) => {
        if (!this._isCancelled) {
          if (typeof options.onError === "function") {
            options.onError(e);
          } else if (typeof options.onEnd === "function") {
            options.onEnd();
          }
        }
      };

      // Pick a natural voice if available
      const voices = this.getVoices();
      if (voices && voices.length > 0) {
        const preferred =
          voices.find(
            (v) =>
              v.lang.startsWith(utterance.lang.slice(0, 2)) &&
              (v.name.includes("Google") || v.name.includes("Natural") || v.name.includes("Premium"))
          ) || voices.find((v) => v.lang.startsWith(utterance.lang.slice(0, 2)));
        if (preferred) {
          utterance.voice = preferred;
        }
      }

      window.speechSynthesis.speak(utterance);
    } catch {
      if (!this._isCancelled && typeof options.onEnd === "function") {
        options.onEnd();
      }
    }
  },

  stop() {
    this._isCancelled = true;
    if (this.isSupported()) {
      window.speechSynthesis.cancel();
    }
  },

  isSpeaking() {
    return this.isSupported() && Boolean(window.speechSynthesis.speaking);
  },
};
