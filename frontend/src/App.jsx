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

function MainApp() {
  const { isAuthenticated } = useAuth();
  const [currentView, setView] = useState(() => ({
    name: "dashboard",
  }));
  const [searchQuery, setSearchQuery] = useState("");

  // If user is not authenticated or explicitly at login screen
  if (!isAuthenticated || currentView.name === "login") {
    return <LoginPage setView={setView} />;
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
