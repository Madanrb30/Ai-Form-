// Authentication service handling session persistence and user data
import { api } from "./api";

const STORAGE_KEY = "voxform_user_session";

export const authService = {
  getCurrentUser() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY) || sessionStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed && typeof parsed.token === "string" && parsed.token.trim() && !parsed.token.startsWith("sess_")) {
          return parsed;
        }
        // Purge legacy/stale mock sessions
        localStorage.removeItem(STORAGE_KEY);
        sessionStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Fallback
    }
    return null;
  },

  async login(email, password, remember = true) {
    if (!email || !password) {
      throw new Error("Email and password are required.");
    }
    if (password.length < 4) {
      throw new Error("Password must be at least 4 characters.");
    }

    const cleanEmail = email.trim().toLowerCase();
    const res = await api.login(cleanEmail, password);

    if (!res || !res.token) {
      throw new Error("Authentication failed: No access token received from server.");
    }

    const resUser = res.user || {};
    const name = resUser.full_name || cleanEmail.split("@")[0].replace(/[._]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    const words = (name || "User").trim().split(/\s+/);
    const initials = resUser.avatar || (words.length > 1
      ? (words[0][0] + words[1][0]).toUpperCase()
      : (name || "US").slice(0, 2).toUpperCase());

    const user = {
      id: String(resUser.id || ""),
      name: name,
      email: resUser.email || cleanEmail,
      role: resUser.role || "USER",
      avatar: initials,
      token: res.token,
    };

    if (remember) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
      sessionStorage.removeItem(STORAGE_KEY);
    } else {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(user));
      localStorage.removeItem(STORAGE_KEY);
    }

    return user;
  },

  async loginWithGoogle(credential, remember = true) {
    if (!credential) {
      throw new Error("Google credential is required.");
    }

    const res = await api.loginWithGoogle(credential);
    if (!res || !res.token) {
      throw new Error("Google authentication failed: No access token received from server.");
    }

    const resUser = res.user || {};
    const name = resUser.full_name || resUser.email?.split("@")[0] || "User";
    const words = name.trim().split(/\s+/);
    const initials = resUser.avatar || (words.length > 1
      ? (words[0][0] + words[1][0]).toUpperCase()
      : name.slice(0, 2).toUpperCase());

    const user = {
      id: String(resUser.id || ""),
      name: name,
      email: resUser.email || "",
      role: resUser.role || "USER",
      avatar: initials,
      token: res.token,
    };

    if (remember) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
      sessionStorage.removeItem(STORAGE_KEY);
    } else {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(user));
      localStorage.removeItem(STORAGE_KEY);
    }

    return user;
  },

  async register(name, email, password) {
    if (!name || !name.trim()) {
      throw new Error("Name is required.");
    }
    if (!email || !email.includes("@")) {
      throw new Error("Valid email is required.");
    }
    if (!password || password.length < 6) {
      throw new Error("Password must be at least 6 characters.");
    }

    const cleanEmail = email.trim().toLowerCase();
    const cleanName = name.trim();
    const res = await api.register({ fullName: cleanName, email: cleanEmail, password });

    if (!res || !res.token) {
      throw new Error("Registration failed: No access token received from server.");
    }

    const resUser = res.user || {};
    const words = cleanName.split(/\s+/);
    const initials = resUser.avatar || (words.length > 1
      ? (words[0][0] + words[1][0]).toUpperCase()
      : cleanName.slice(0, 2).toUpperCase());

    const user = {
      id: String(resUser.id || ""),
      name: resUser.full_name || cleanName,
      email: resUser.email || cleanEmail,
      role: resUser.role || "USER",
      avatar: initials,
      token: res.token,
    };

    localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    sessionStorage.removeItem(STORAGE_KEY);
    return user;
  },

  updateProfile(updates) {
    const current = this.getCurrentUser();
    if (!current) return null;
    const updated = { ...current, ...updates };
    if (localStorage.getItem(STORAGE_KEY)) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    } else {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    }
    return updated;
  },

  logout() {
    localStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(STORAGE_KEY);
  },
};
