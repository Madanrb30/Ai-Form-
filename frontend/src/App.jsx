import React, { useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ToastProvider } from "./context/ToastContext";
import AppLayout from "./components/layout/AppLayout";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import CreateFormPage from "./pages/CreateFormPage";
import VoiceAssistantPage from "./pages/VoiceAssistantPage";
import FormEditorPage from "./pages/FormEditorPage";
import ReviewFormPage from "./pages/ReviewFormPage";
import HistoryPage from "./pages/HistoryPage";
import SettingsPage from "./pages/SettingsPage";
import SubmissionsPage from "./pages/SubmissionsPage";
import AdminDashboardPage from "./pages/AdminDashboardPage";
import SuperAdminDashboardPage from "./pages/SuperAdminDashboardPage";

function MainApp() {
  const { isAuthenticated, loading, role, isAdmin, isSuperAdmin } = useAuth();
  const [currentView, setView] = useState(() => ({
    name: "dashboard",
  }));
  const [searchQuery, setSearchQuery] = useState("");

  // Show clean minimal spinner during startup token verification
  if (loading) {
    return (
      <div className="min-h-screen bg-white flex flex-col items-center justify-center p-4">
        <div className="w-8 h-8 border-2 border-neutral-900 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-neutral-500 font-mono mt-3">Verifying session...</p>
      </div>
    );
  }

  // If user is not authenticated or explicitly at login screen
  if (!isAuthenticated || currentView.name === "login") {
    return <LoginPage setView={setView} />;
  }

  // Protected route role guards: non-admins cannot access admin / super-admin consoles
  if (currentView.name === "super-admin" && !isSuperAdmin) {
    return (
      <AppLayout
        currentView={{ name: isAdmin ? "admin" : "dashboard" }}
        setView={setView}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
      >
        <DashboardPage setView={setView} searchQuery={searchQuery} setSearchQuery={setSearchQuery} />
      </AppLayout>
    );
  }

  if (currentView.name === "admin" && !isAdmin) {
    return (
      <AppLayout
        currentView={{ name: "dashboard" }}
        setView={setView}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
      >
        <DashboardPage setView={setView} searchQuery={searchQuery} setSearchQuery={setSearchQuery} />
      </AppLayout>
    );
  }

  // Non-admins cannot access form creation, document generation, or editor pages
  if (
    (currentView.name === "create" || currentView.name === "generate" || currentView.name === "editor") &&
    !isAdmin
  ) {
    return (
      <AppLayout
        currentView={{ name: "dashboard" }}
        setView={setView}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
      >
        <DashboardPage setView={setView} searchQuery={searchQuery} setSearchQuery={setSearchQuery} />
      </AppLayout>
    );
  }

  return (
    <AppLayout
      currentView={currentView}
      setView={setView}
      searchQuery={searchQuery}
      setSearchQuery={setSearchQuery}
    >
      {currentView.name === "dashboard" && (
        <DashboardPage
          setView={setView}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
        />
      )}

      {(currentView.name === "create" || currentView.name === "generate") && (
        <CreateFormPage setView={setView} />
      )}

      {currentView.name === "fill" && (
        <VoiceAssistantPage
          formId={currentView.formId}
          formTitle={currentView.formTitle}
          setView={setView}
        />
      )}

      {currentView.name === "editor" && (
        <FormEditorPage
          formId={currentView.formId}
          formTitle={currentView.formTitle}
          setView={setView}
        />
      )}

      {currentView.name === "review" && (
        <ReviewFormPage
          formId={currentView.formId}
          formTitle={currentView.formTitle}
          values={currentView.values}
          pdfFilledFields={currentView.pdfFilledFields}
          needsReviewFields={currentView.needsReviewFields}
          manuallyEditedFields={currentView.manuallyEditedFields}
          initialSubmissionSuccess={currentView.initialSubmissionSuccess}
          setView={setView}
        />
      )}

      {(currentView.name === "history" || currentView.name === "forms") && (
        <HistoryPage setView={setView} />
      )}

      {currentView.name === "settings" && (
        <SettingsPage setView={setView} />
      )}

      {currentView.name === "submissions" && (
        <SubmissionsPage
          formId={currentView.formId}
          formTitle={currentView.formTitle}
          setView={setView}
        />
      )}

      {currentView.name === "admin" && (
        <AdminDashboardPage setView={setView} />
      )}

      {currentView.name === "super-admin" && (
        <SuperAdminDashboardPage setView={setView} />
      )}
    </AppLayout>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <MainApp />
      </ToastProvider>
    </AuthProvider>
  );
}
