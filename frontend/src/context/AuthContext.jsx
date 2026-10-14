import React, { createContext, useContext, useState, useEffect } from "react";
import { authService } from "../services/authService";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => authService.getCurrentUser());
  const [isAuthenticated, setIsAuthenticated] = useState(() => Boolean(user));

  useEffect(() => {
    setIsAuthenticated(Boolean(user));
  }, [user]);

  const login = async (email, password, remember = true) => {
    const loggedInUser = await authService.login(email, password, remember);
    setUser(loggedInUser);
    return loggedInUser;
  };

  const register = async (name, email, password) => {
    const newUser = await authService.register(name, email, password);
    setUser(newUser);
    return newUser;
  };

  const logout = () => {
    authService.logout();
    setUser(null);
  };

  const updateProfile = (updates) => {
    const updated = authService.updateProfile(updates);
    setUser(updated);
    return updated;
  };

  const role = user?.role ? String(user.role).toUpperCase() : "USER";
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
        login,
        register,
        logout,
        updateProfile,
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
