// Local storage management for Form Drafts and App Settings
const SETTINGS_KEY = "voxform_app_settings";

const DEFAULT_SETTINGS = {
  language: "en-US",
  voiceSpeed: 1.0,
  voicePlayback: false,
  voiceConfirmation: true,
  storeTranscripts: true,
  theme: "light",
};

function getCurrentUserId() {
  try {
    const raw = localStorage.getItem("voxform_user_session") || sessionStorage.getItem("voxform_user_session");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.id) {
        return String(parsed.id);
      }
    }
  } catch {
    // ignore parse error
  }
  return "guest";
}

function getDraftsKey(userId) {
  const uid = userId !== undefined && userId !== null ? String(userId) : getCurrentUserId();
  return `voxform_form_drafts_${uid}`;
}

export const storageService = {
  // --- Form Drafts (strictly isolated per user ID) ---
  getDrafts(userId) {
    try {
      const key = getDraftsKey(userId);
      const data = localStorage.getItem(key);
      return data ? JSON.parse(data) : {};
    } catch {
      return {};
    }
  },

  getDraft(formId, userId) {
    const drafts = this.getDrafts(userId);
    return drafts[formId] || null;
  },

  saveDraft(formId, formData, formTitle = "Draft Form", userId) {
    const key = getDraftsKey(userId);
    const drafts = this.getDrafts(userId);
    drafts[formId] = {
      formId,
      title: formTitle,
      values: formData,
      updatedAt: new Date().toISOString(),
    };
    localStorage.setItem(key, JSON.stringify(drafts));
    return drafts[formId];
  },

  deleteDraft(formId, userId) {
    const key = getDraftsKey(userId);
    const drafts = this.getDrafts(userId);
    if (drafts[formId]) {
      delete drafts[formId];
      localStorage.setItem(key, JSON.stringify(drafts));
    }
  },

  getDraftsCount(userId) {
    return Object.keys(this.getDrafts(userId)).length;
  },

  // --- Settings ---
  getSettings() {
    try {
      const data = localStorage.getItem(SETTINGS_KEY);
      return data ? { ...DEFAULT_SETTINGS, ...JSON.parse(data) } : DEFAULT_SETTINGS;
    } catch {
      return DEFAULT_SETTINGS;
    }
  },

  saveSettings(newSettings) {
    const current = this.getSettings();
    const updated = { ...current, ...newSettings };
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(updated));
    return updated;
  },
};
