// Local storage management for Form Drafts and App Settings
const DRAFTS_KEY = "voxform_form_drafts";
const SETTINGS_KEY = "voxform_app_settings";

const DEFAULT_SETTINGS = {
  language: "en-US",
  voiceSpeed: 1.0,
  voicePlayback: false,
  voiceConfirmation: true,
  storeTranscripts: true,
  theme: "light",
};

export const storageService = {
  // --- Form Drafts ---
  getDrafts() {
    try {
      const data = localStorage.getItem(DRAFTS_KEY);
      return data ? JSON.parse(data) : {};
    } catch {
      return {};
    }
  },

  getDraft(formId) {
    const drafts = this.getDrafts();
    return drafts[formId] || null;
  },

  saveDraft(formId, formData, formTitle = "Draft Form") {
    const drafts = this.getDrafts();
    drafts[formId] = {
      formId,
      title: formTitle,
      values: formData,
      updatedAt: new Date().toISOString(),
    };
    localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts));
    return drafts[formId];
  },

  deleteDraft(formId) {
    const drafts = this.getDrafts();
    if (drafts[formId]) {
      delete drafts[formId];
      localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts));
    }
  },

  getDraftsCount() {
    return Object.keys(this.getDrafts()).length;
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
