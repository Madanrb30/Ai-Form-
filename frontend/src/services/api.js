const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";

class ApiError extends Error {
  constructor(message, status = 0, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

function getStoredToken() {
  try {
    const raw = localStorage.getItem("voxform_user_session") || sessionStorage.getItem("voxform_user_session");
    if (raw) {
      const parsed = JSON.parse(raw);
      return parsed.token || null;
    }
  } catch {
    // Ignore parse error
  }
  return null;
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const timeoutMs = options.timeout || 25000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;

  const headers = {
    Accept: "application/json",
    ...options.headers,
  };

  if (!isFormData && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  // Inject Bearer token if session exists and not explicitly overridden
  const token = getStoredToken();
  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const config = {
    ...options,
    headers,
    signal: controller.signal,
  };

  try {
    const res = await fetch(url, config);
    clearTimeout(timer);

    if (res.status === 204) {
      return null;
    }

    const contentType = res.headers.get("content-type");
    let data;
    if (contentType && contentType.includes("application/json")) {
      data = await res.json();
    } else {
      data = await res.text();
    }

    if (!res.ok) {
      const errMsg =
        (typeof data === "object" && (data?.detail?.message || data?.detail || data?.message)) ||
        `HTTP Error ${res.status}: ${res.statusText}`;
      const errDetails = typeof data === "object" && data?.detail?.errors ? data.detail.errors : null;
      throw new ApiError(typeof errMsg === "string" ? errMsg : JSON.stringify(errMsg), res.status, errDetails);
    }

    return data;
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") {
      throw new ApiError(`Request to ${endpoint} timed out after ${timeoutMs / 1000}s`, 408);
    }
    if (err instanceof ApiError) {
      throw err;
    }
    // Network / connection error
    throw new ApiError(
      `Cannot connect to backend server at ${API_BASE}. Please ensure FastAPI is running. (${err.message})`,
      0
    );
  }
}

export const api = {
  // Health & System
  getHealth: () => request("/health"),

  // Authentication
  login: (email, password) =>
    request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: ({ fullName, email, password }) =>
    request("/auth/register", {
      method: "POST",
      body: JSON.stringify({ full_name: fullName, email, password }),
    }),
  getMe: () => request("/auth/me"),

  // Form Creation & Management
  generateForm: (prompt) =>
    request("/forms/generate", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),
  uploadDocument: (file) => {
    const formData = new FormData();
    formData.append("file", file);
    return request("/forms/upload-document", {
      method: "POST",
      body: formData,
    });
  },
  getForms: () => request("/forms"),
  getForm: (id) => request(`/forms/${id}`),
  createForm: (formData) =>
    request("/forms", {
      method: "POST",
      body: JSON.stringify(formData),
    }),
  updateForm: (id, formData) =>
    request(`/forms/${id}`, {
      method: "PUT",
      body: JSON.stringify(formData),
    }),
  deleteForm: (id) => request(`/forms/${id}`, { method: "DELETE" }),

  // Submissions & PDF Export
  createSubmission: (formId, responseJson) =>
    request(`/forms/${formId}/submissions`, {
      method: "POST",
      body: JSON.stringify({ response_json: responseJson }),
    }),
  getSubmissions: (formId) => request(`/forms/${formId}/submissions`),
  getSubmissionPdfUrl: (formId, subId) =>
    `${API_BASE}/forms/${formId}/submissions/${subId}/pdf`,

  // Cloud Speech-to-Text Transcription via Groq Whisper-large-v3-turbo
  transcribeAudio: (audioBlob, { filename = "recording.webm", language = null } = {}) => {
    const formData = new FormData();
    formData.append("file", audioBlob, filename);
    if (language) {
      formData.append("language", language);
    }
    return request("/voice/transcribe", {
      method: "POST",
      body: formData,
    });
  },

  // Voice & Stateful Conversational Assistant
  voiceMap: (formId, transcript) =>
    request(`/forms/${formId}/voice-map`, {
      method: "POST",
      body: JSON.stringify({ transcript }),
    }),
  postConversationTurn: (formId, { transcript, sessionId, currentValues }) =>
    request(`/forms/${formId}/conversation`, {
      method: "POST",
      body: JSON.stringify({
        transcript,
        session_id: sessionId || null,
        current_values: currentValues || {},
      }),
    }),

  // Server-side Autosave Drafts
  getDraft: (formId) => request(`/forms/${formId}/draft`),
  saveDraft: (formId, valuesJson) =>
    request(`/forms/${formId}/draft`, {
      method: "POST",
      body: JSON.stringify({ values_json: valuesJson }),
    }),
  deleteDraft: (formId) => request(`/forms/${formId}/draft`, { method: "DELETE" }),
};
