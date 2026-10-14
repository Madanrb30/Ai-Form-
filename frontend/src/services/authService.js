// Authentication service handling session persistence and user data
import { api } from "./api";

const STORAGE_KEY = "voxform_user_session";

const DEFAULT_USER = {
  id: "usr_101",
  name: "Madan RB",
  email: "madan@example.com",
  role: "Product Lead",
  avatar: "MR",
  token: "sess_demo_token_8849",
};

export const authService = {
  getCurrentUser() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY) || sessionStorage.getItem(STORAGE_KEY);
      if (stored) {
        return JSON.parse(stored);
      }
    } catch {
      // Fallback
    }
    return DEFAULT_USER;
  },

  login(email, password, remember = true) {
    if (!email || !password) {
      throw new Error("Email and password are required.");
    }
    if (password.length < 4) {
      throw new Error("Password must be at least 4 characters.");
    }

    const name = email.split("@")[0].replace(/[._]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    const words = (name || "User").trim().split(/\s+/);
    const initials = words.length > 1
      ? (words[0][0] + words[1][0]).toUpperCase()
      : (name || "US").slice(0, 2).toUpperCase();

    const user = {
      id: `usr_${Date.now()}`,
      name: name || "Demo User",
      email: email.trim().toLowerCase(),
      role: "User",
      avatar: initials || "DU",
      token: `sess_${Math.random().toString(36).substring(2)}`,
    };

    if (remember) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    } else {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    }

    // Opportunistically authenticate with FastAPI backend if online
    api.login(email.trim().toLowerCase(), password)
      .then((res) => {
        if (res && res.token && res.user) {
          user.token = res.token;
          user.id = String(res.user.id);
          user.role = res.user.role || user.role;
          if (remember) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
          } else {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(user));
          }
        }
      })
      .catch(() => {
        // Silent fallback in background
      });

    return user;
  },

  register(name, email, password) {
    if (!name || !name.trim()) {
      throw new Error("Name is required.");
    }
    if (!email || !email.includes("@")) {
      throw new Error("Valid email is required.");
    }
    if (!password || password.length < 6) {
      throw new Error("Password must be at least 6 characters.");
    }

    const words = name.trim().split(/\s+/);
    const initials = words.length > 1
      ? (words[0][0] + words[1][0]).toUpperCase()
      : name.slice(0, 2).toUpperCase();

    const user = {
      id: `usr_${Date.now()}`,
      name: name.trim(),
      email: email.trim().toLowerCase(),
      role: "User",
      avatar: initials || "U",
      token: `sess_${Math.random().toString(36).substring(2)}`,
    };

    localStorage.setItem(STORAGE_KEY, JSON.stringify(user));

    api.register({ fullName: name.trim(), email: email.trim().toLowerCase(), password })
      .then((res) => {
        if (res && res.token && res.user) {
          user.token = res.token;
          user.id = String(res.user.id);
          user.role = res.user.role || "USER";
          localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
        }
      })
      .catch(() => {
        // Silent fallback
      });

    return user;
  },

  updateProfile(updates) {
    const current = this.getCurrentUser() || DEFAULT_USER;
    const updated = { ...current, ...updates };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    return updated;
  },

  logout() {
    localStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(STORAGE_KEY);
  },
};
