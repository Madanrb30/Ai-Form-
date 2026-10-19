import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { authService } from "../services/authService";
import { api } from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => authService.getCurrentUser());
  const [isAuthenticated, setIsAuthenticated] = useState(() => Boolean(user));
  const [loading, setLoading] = useState(true);

  // Validate session against server on startup to prevent stale/forged token bypass
  const verifySession = useCallback(async () => {
    const storedUser = authService.getCurrentUser();
    if (!storedUser || !storedUser.token) {
      setUser(null);
      setIsAuthenticated(false);
      setLoading(false);
      return;
    }

    try {
      const serverProfile = await api.getMe();
      if (serverProfile && serverProfile.id) {
        const verifiedUser = {
          ...storedUser,
          id: String(serverProfile.id),
          name: serverProfile.full_name || storedUser.name,
          email: serverProfile.email || storedUser.email,
          role: String(serverProfile.role || "USER").toUpperCase(),
        };
        setUser(verifiedUser);
        setIsAuthenticated(true);
      } else {
        authService.logout();
        setUser(null);
        setIsAuthenticated(false);
      }
    } catch (err) {
      // If server rejected with 401 or token is invalid, purge and redirect to login
      if (err.status === 401 || err.status === 403) {
        authService.logout();
        setUser(null);
        setIsAuthenticated(false);
      } else {
        // If server is unreachable, do not silently grant access
        authService.logout();
        setUser(null);
        setIsAuthenticated(false);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    verifySession();
  }, [verifySession]);

  const login = async (email, password, remember = true) => {
    const loggedInUser = await authService.login(email, password, remember);
    setUser(loggedInUser);
    setIsAuthenticated(true);
    return loggedInUser;
  };

  const loginWithGoogle = async (credential, remember = true) => {
    const loggedInUser = await authService.loginWithGoogle(credential, remember);
    setUser(loggedInUser);
    setIsAuthenticated(true);
    return loggedInUser;
  };

  const register = async (name, email, password) => {
    const newUser = await authService.register(name, email, password);
    setUser(newUser);
    setIsAuthenticated(true);
    return newUser;
  };

  const logout = () => {
    authService.logout();
    setUser(null);
    setIsAuthenticated(false);
  };

  const updateProfile = (updates) => {
    const updated = authService.updateProfile(updates);
    setUser(updated);
    return updated;
  };

  const role = user?.role ? String(user.role).toUpperCase() : "";
  const isAdmin = role === "ADMIN" || role === "SUPER_ADMIN";
  const isSuperAdmin = role === "SUPER_ADMIN";

  return (
    <AuthContext.Provider
      value={{
        user,
        role,
        isAdmin,
        isSuperAdmin,
        isAuthenticated,
        loading,
        login,
        loginWithGoogle,
        register,
        logout,
        updateProfile,
        verifySession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
