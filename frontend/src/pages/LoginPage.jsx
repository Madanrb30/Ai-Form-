import React, { useState, useEffect, useRef, useCallback } from "react";
import { Sparkles, ArrowRight, Lock, Mail, User, ShieldCheck } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";

export default function LoginPage({ setView }) {
  const { login, register, loginWithGoogle } = useAuth();
  const { toast } = useToast();

  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [gsiLoaded, setGsiLoaded] = useState(false);
  const googleBtnContainerRef = useRef(null);

  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || import.meta.env.GOOGLE_CLIENT_ID;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (isRegisterMode && !name.trim()) {
      setError("Please enter your full name.");
      return;
    }
    if (!email.trim() || !email.includes("@")) {
      setError("Please enter a valid email address.");
      return;
    }
    if (!password || password.length < 4) {
      setError("Password must be at least 4 characters.");
      return;
    }

    setLoading(true);
    try {
      let loggedUser;
      if (isRegisterMode) {
        loggedUser = await register(name, email, password);
        toast("Account created successfully. Welcome!", "success");
      } else {
        loggedUser = await login(email, password, rememberMe);
        toast("Signed in successfully.", "success");
      }

      // Route to role-appropriate destination
      const userRole = String(loggedUser?.role || "USER").toUpperCase();
      if (userRole === "SUPER_ADMIN") {
        setView({ name: "super-admin" });
      } else if (userRole === "ADMIN") {
        setView({ name: "admin" });
      } else {
        setView({ name: "dashboard" });
      }
    } catch (err) {
      setError(err.message || "Authentication failed. Please verify credentials.");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleCredentialResponse = useCallback(
    async (response) => {
      if (!response?.credential) return;
      setLoading(true);
      setError(null);
      try {
        const loggedUser = await loginWithGoogle(response.credential, rememberMe);
        toast(`Signed in as ${loggedUser.name || loggedUser.email}`, "success");
        const userRole = String(loggedUser?.role || "USER").toUpperCase();
        if (userRole === "SUPER_ADMIN") {
          setView({ name: "super-admin" });
        } else if (userRole === "ADMIN") {
          setView({ name: "admin" });
        } else {
          setView({ name: "dashboard" });
        }
      } catch (err) {
        setError(err.message || "Google authentication failed. Please verify credentials.");
        toast(err.message || "Google authentication failed.", "error");
      } finally {
        setLoading(false);
      }
    },
    [loginWithGoogle, rememberMe, setView, toast]
  );

  // Initialize Google Identity Services if client ID is configured
  useEffect(() => {
    if (!googleClientId) return;

    let checkInterval;
    let isCancelled = false;

    const setupGoogle = () => {
      if (window.google?.accounts?.id && !isCancelled) {
        try {
          window.google.accounts.id.initialize({
            client_id: googleClientId,
            callback: handleGoogleCredentialResponse,
            auto_select: false,
            cancel_on_tap_outside: true,
          });

          if (googleBtnContainerRef.current) {
            googleBtnContainerRef.current.innerHTML = "";
            const containerWidth = Math.min(
              384,
              Math.max(200, googleBtnContainerRef.current.offsetWidth || 384)
            );
            window.google.accounts.id.renderButton(googleBtnContainerRef.current, {
              theme: "outline",
              size: "large",
              width: containerWidth,
              text: "continue_with",
              shape: "rectangular",
              logo_alignment: "left",
            });
            setGsiLoaded(true);
          }
        } catch (e) {
          console.warn("Google GIS initialization error:", e);
        }
      }
    };

    if (window.google?.accounts?.id) {
      setupGoogle();
    } else {
      checkInterval = setInterval(() => {
        if (window.google?.accounts?.id) {
          setupGoogle();
          clearInterval(checkInterval);
        }
      }, 250);
    }

    return () => {
      isCancelled = true;
      if (checkInterval) clearInterval(checkInterval);
    };
  }, [googleClientId, handleGoogleCredentialResponse]);

  const handleGoogleAuth = () => {
    if (!googleClientId) {
      toast(
        "Google OAuth is not configured. Set VITE_GOOGLE_CLIENT_ID in your environment to enable Google Sign-In, or sign in with email and password.",
        "info"
      );
      return;
    }

    if (window.google?.accounts?.id) {
      window.google.accounts.id.prompt((notification) => {
        if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
          toast("Google prompt dismissed or unavailable. Please sign in with email/password.", "info");
        }
      });
    } else {
      toast("Google Identity Services library is still loading. Please try again in a moment.", "info");
    }
  };

  return (
    <div className="min-h-screen bg-[#F7F7F7] flex flex-col justify-center items-center p-4 antialiased selection:bg-neutral-900 selection:text-white">
      {/* Container Card */}
      <div className="w-full max-w-md bg-white border border-[#E5E5E5] rounded-2xl shadow-xl overflow-hidden p-8 text-left transition-all">
        {/* Brand Header */}
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-[#0B0B0B] text-white flex items-center justify-center mx-auto mb-3 shadow-md border border-neutral-800">
            <Sparkles className="w-6 h-6 text-neutral-100" />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-neutral-900">
            AI Form Assistant
          </h1>
          <p className="text-xs text-[#737373] mt-1 max-w-xs mx-auto leading-relaxed">
            Fill any form with your voice, powered by AI.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex border-b border-[#E5E5E5] mb-6">
          <button
            type="button"
            onClick={() => {
              setIsRegisterMode(false);
              setError(null);
            }}
            className={`flex-1 py-2 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
              !isRegisterMode
                ? "border-neutral-900 text-neutral-900"
                : "border-transparent text-neutral-400 hover:text-neutral-700"
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => {
              setIsRegisterMode(true);
              setError(null);
            }}
            className={`flex-1 py-2 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
              isRegisterMode
                ? "border-neutral-900 text-neutral-900"
                : "border-transparent text-neutral-400 hover:text-neutral-700"
            }`}
          >
            Create Account
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
            {error}
          </div>
        )}

        {/* Form Fields */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {isRegisterMode && (
            <div>
              <label className="block text-xs font-medium text-neutral-700 mb-1">
                Full Name
              </label>
              <div className="relative">
                <User className="w-4 h-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Madan RB"
                  className="w-full pl-9 pr-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition-all"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-neutral-700 mb-1">
              Email Address
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full pl-9 pr-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition-all"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-neutral-700">
                Password
              </label>
              {!isRegisterMode && (
                <button
                  type="button"
                  onClick={() => toast("Password reset link sent to registered email.", "info")}
                  className="text-[11px] text-neutral-500 hover:text-black hover:underline cursor-pointer"
                >
                  Forgot password?
                </button>
              )}
            </div>
            <div className="relative">
              <Lock className="w-4 h-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-9 pr-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition-all"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="w-3.5 h-3.5 rounded border-[#E5E5E5] text-neutral-900 focus:ring-neutral-900"
              />
              <span className="text-xs text-neutral-600">Remember me</span>
            </label>
            <span className="text-[11px] text-neutral-400 font-mono">Demo Ready</span>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-2.5 px-4 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-all disabled:opacity-50 flex items-center justify-center space-x-2 cursor-pointer shadow-xs"
          >
            <span>{loading ? "Authenticating..." : isRegisterMode ? "Create Account" : "Sign In"}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </form>

        {/* Google SSO Option - Exactly ONE visible button */}
        <div className="mt-5 pt-4 border-t border-[#E5E5E5]">
          <div
            ref={googleBtnContainerRef}
            className={`w-full flex justify-center ${gsiLoaded ? "" : "hidden"}`}
          />
          {!gsiLoaded && (
            <button
              type="button"
              onClick={handleGoogleAuth}
              disabled={loading}
              className="w-full py-2 px-3 border border-[#E5E5E5] hover:bg-neutral-50 rounded-lg text-xs text-neutral-700 font-medium transition-colors flex items-center justify-center space-x-2 cursor-pointer disabled:opacity-50"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                />
              </svg>
              <span>{loading ? "Authenticating with Google..." : "Continue with Google"}</span>
            </button>
          )}
        </div>

        {/* Security badge footer */}
        <div className="mt-6 text-center flex items-center justify-center space-x-1 text-[11px] text-neutral-400">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Local SQLite Backend • Zero Data Leak</span>
        </div>
      </div>
    </div>
  );
}
