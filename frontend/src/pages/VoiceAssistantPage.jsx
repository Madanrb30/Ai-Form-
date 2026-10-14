import React, { useEffect, useState, useCallback } from "react";
import {
  ArrowRight,
  ArrowLeft,
  Save,
  Send,
  Volume2,
  VolumeX,
  Edit3,
  Loader2,
  Square,
  X,
} from "lucide-react";
import { api } from "../services/api";
import { storageService } from "../services/storageService";
import { ttsService } from "../services/ttsService";
import { useVoiceRecognition } from "../hooks/useVoiceRecognition";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import MicrophoneButton from "../components/voice/MicrophoneButton";
import AudioWaveform from "../components/voice/AudioWaveform";
import VoiceTranscriptPanel from "../components/voice/VoiceTranscriptPanel";
import FormRenderer from "../components/forms/FormRenderer";

export default function VoiceAssistantPage({ formId, setView }) {
  const { user } = useAuth();
  const { toast } = useToast();

  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [serverError, setServerError] = useState(null);

  // Form values & validation state
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [highlightedFields, setHighlightedFields] = useState([]);
  const [aiFilledFields, setAiFilledFields] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [missingFields, setMissingFields] = useState([]);
  const [needsReviewFields, setNeedsReviewFields] = useState({});

  // Voice Interaction State (9 explicit states):
  // 'idle' | 'requesting' | 'listening' | 'transcribing' | 'processing' | 'filling' | 'waiting' | 'error' | 'completed'
  const [voiceState, setVoiceState] = useState("idle");
  const [statusMessage, setStatusMessage] = useState("Assistant ready. Click the microphone to start speaking.");
  const [conversation, setConversation] = useState([
    {
      role: "assistant",
      text: "I'm ready to help you fill this form. You can start speaking now.",
      meta: "Ready",
    },
  ]);

  const [simulatedText, setSimulatedText] = useState("");
  const [ttsEnabled, setTtsEnabled] = useState(() => storageService.getSettings().voicePlayback);

  // Cloud Audio Recording & Speech Recognition Hook (Groq Whisper-large-v3-turbo)
  const {
    isSupported,
    isListening,
    isRecording,
    isTranscribing,
    recordingTimeFormatted,
    transcript,
    setTranscript,
    interimTranscript,
    error: speechError,
    transcriptionMeta,
    startListening,
    stopListening,
    cancelListening,
    resetTranscript,
  } = useVoiceRecognition();

  // Load Form Data & Drafts
  useEffect(() => {
    let isMounted = true;
    const fetchForm = async () => {
      setLoading(true);
      setServerError(null);
      try {
        const [formData, serverDraft] = await Promise.all([
          api.getForm(formId),
          api.getDraft(formId).catch(() => null),
        ]);
        if (!isMounted) return;
        setForm(formData);

        // Check for saved draft (server or local storage)
        const localDraft = storageService.getDraft(formId, user?.id);
        const draftValues = serverDraft?.values_json || localDraft?.values || {};
        const initial = {};

        formData.schema_json?.fields?.forEach((f) => {
          if (draftValues[f.name] !== undefined) {
            initial[f.name] = draftValues[f.name];
          } else if (f.default_value !== null && f.default_value !== undefined) {
            initial[f.name] = f.default_value;
          } else if (f.type === "checkbox") {
            initial[f.name] = false;
          } else {
            initial[f.name] = "";
          }
        });

        setValues(initial);
        if (serverDraft || localDraft) {
          toast("Restored previously saved draft progress.", "info");
        }
      } catch (err) {
        if (isMounted) {
          setServerError(`Failed to load form: ${err.message}`);
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchForm();
    return () => {
      isMounted = false;
    };
  }, [formId, toast]);

  // Synchronize Voice Recognition & Cloud Whisper State
  useEffect(() => {
    if (speechError) {
      setVoiceState("error");
      setStatusMessage(speechError);
    } else if (isTranscribing) {
      setVoiceState("transcribing");
      setStatusMessage("Transcribing audio via Groq Whisper cloud API (whisper-large-v3-turbo)...");
    } else if (isRecording) {
      setVoiceState("listening");
      setStatusMessage(`Recording audio... (${recordingTimeFormatted}). Speak clearly, then click stop.`);
    }
  }, [isRecording, isTranscribing, recordingTimeFormatted, speechError]);

  // Handle Speech Extraction Mapping via Conversational AI API
  const processTranscript = useCallback(
    async (spokenText) => {
      if (!spokenText || !spokenText.trim() || !form) return;

      const userText = spokenText.trim();
      setVoiceState("processing");
      setStatusMessage("Processing natural language with conversational AI...");

      // Add user speech to conversation
      setConversation((prev) => [
        ...prev,
        {
          role: "user",
          text: userText,
          meta: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);

      try {
        setVoiceState("filling");
        setStatusMessage("Analyzing speech with stateful conversational assistant...");

        let turnRes;
        try {
          turnRes = await api.postConversationTurn(formId, {
            transcript: userText,
            sessionId,
            currentValues: values,
          });
        } catch (turnErr) {
          console.warn("Conversational turn error, falling back to voiceMap:", turnErr);
          const mapRes = await api.voiceMap(formId, userText);
          turnRes = {
            session_id: sessionId || "local",
            assistant_response: "Got your information.",
            updated_values: { ...values, ...(mapRes.mapped_fields || {}) },
            newly_filled: Object.keys(mapRes.mapped_fields || {}),
            confirmed_fields: [],
            missing_fields: [],
            is_completed: false,
          };
        }

        if (turnRes.session_id) {
          setSessionId(turnRes.session_id);
        }

        const updated = turnRes.updated_values || values;
        setValues(updated);
        setMissingFields(turnRes.missing_fields || []);

        const matchedKeys = turnRes.newly_filled || [];
        const reviews = turnRes.needs_review || {};
        setNeedsReviewFields(reviews);

        if (matchedKeys.length > 0) {
          setHighlightedFields(matchedKeys);
          setAiFilledFields((prev) => Array.from(new Set([...prev, ...matchedKeys])));

          setTimeout(() => {
            setHighlightedFields([]);
          }, 3000);
        }

        setErrors((prev) => {
          const next = { ...prev };
          matchedKeys.forEach((k) => delete next[k]);
          Object.assign(next, reviews);
          return next;
        });

        // Autosave draft server-side and locally
        const activeSessionId = turnRes.session_id || sessionId;
        api.saveDraft(formId, updated, activeSessionId).catch(() => {});
        storageService.saveDraft(formId, updated, form?.title || "Form Draft", user?.id);

        if (turnRes.is_submitted || turnRes.submission_id) {
          // Form successfully submitted by the conversational agent!
          storageService.deleteDraft(formId, user?.id);
          setVoiceState("completed");
          setStatusMessage("Form submitted successfully!");
          toast("Form response submitted successfully!", "success");

          const submissionReply = turnRes.assistant_response || "Your form has been successfully submitted!";

          setConversation((prev) => [
            ...prev,
            {
              role: "assistant",
              text: submissionReply,
              meta: `Submitted #${turnRes.submission_id}`,
            },
          ]);

          if (ttsEnabled) {
            ttsService.speak(submissionReply);
          }

          setTimeout(() => {
            setView({
              name: "review",
              formId,
              formTitle: form?.title,
              values: turnRes.updated_values || updated,
              initialSubmissionSuccess: {
                id: turnRes.submission_id,
                form_id: formId,
                created_at: new Date().toISOString(),
              },
            });
          }, 1800);
          return;
        }

        const assistantReply = turnRes.assistant_response || "Information updated.";

        setConversation((prev) => [
          ...prev,
          {
            role: "assistant",
            text: assistantReply,
            meta: matchedKeys.length > 0 ? `Updated ${matchedKeys.length} field(s)` : "Guidance",
          },
        ]);

        if (turnRes.is_completed) {
          setVoiceState("completed");
          setStatusMessage("All required fields are completed! Ready for submission.");
          toast("All required fields are completed! Speak 'submit' or click to submit.", "success");
        } else {
          setVoiceState("waiting");
          setStatusMessage(
            matchedKeys.length > 0
              ? `Populated ${matchedKeys.length} field(s). Ready for next detail.`
              : "Assistant ready. Speak your next detail."
          );
        }

        if (ttsEnabled) {
          ttsService.speak(assistantReply);
        }
      } catch (err) {
        setVoiceState("error");
        setStatusMessage(`AI processing error: ${err.message}`);
        toast(`Voice mapping error: ${err.message}`, "error");
      } finally {
        resetTranscript();
        setSimulatedText("");
      }
    },
    [form, formId, sessionId, values, resetTranscript, ttsEnabled, toast]
  );

  // Automatically trigger processing when transcription completes
  useEffect(() => {
    if (!isListening && !isTranscribing && transcript && transcript.trim()) {
      processTranscript(transcript);
    }
  }, [isListening, isTranscribing, transcript, processTranscript]);

  // Voice Commands Handler
  const handleToggleListening = () => {
    if (isTranscribing) return;
    if (isListening || isRecording) {
      stopListening();
    } else {
      if (!isSupported) {
        toast("Audio recording is not supported in this browser environment. Please use manual input below.", "error");
        return;
      }
      setVoiceState("requesting");
      setStatusMessage("Requesting microphone permission...");
      startListening();
    }
  };

  // Draft Save Handler
  const handleSaveDraft = async () => {
    storageService.saveDraft(formId, values, form?.title || "Form Draft", user?.id);
    try {
      await api.saveDraft(formId, values, sessionId);
      toast("Draft progress saved to cloud database and local storage.", "success");
    } catch {
      toast("Draft progress saved to local storage.", "info");
    }
  };

  // Direct Submission Handler
  const [submitting, setSubmitting] = useState(false);
  const handleDirectSubmit = async () => {
    setSubmitting(true);
    try {
      const response = await api.createSubmission(formId, values);
      storageService.deleteDraft(formId, user?.id);
      toast("Form response submitted successfully!", "success");
      setView({
        name: "review",
        formId,
        formTitle: form?.title,
        values,
        initialSubmissionSuccess: response,
      });
    } catch (err) {
      toast(`Submission failed: ${err.message}`, "error");
    } finally {
      setSubmitting(false);
    }
  };

  // Form Progress Calculator
  const fields = form?.schema_json?.fields || [];
  const requiredFields = fields.filter((f) => f.required);
  const filledRequiredCount = requiredFields.filter((f) => {
    const val = values[f.name];
    return val !== undefined && val !== null && String(val).trim() !== "" && val !== false;
  }).length;

  const totalFilledCount = fields.filter((f) => {
    const val = values[f.name];
    return val !== undefined && val !== null && String(val).trim() !== "" && val !== false;
  }).length;

  const progressPercent =
    requiredFields.length > 0
      ? Math.round((filledRequiredCount / requiredFields.length) * 100)
      : Math.round((totalFilledCount / Math.max(1, fields.length)) * 100);

  // Sample prompt generator for quick testing
  const samplePrompts = fields.slice(0, 3).map((f) => {
    if (f.name.includes("name")) return `My name is Madan RB`;
    if (f.name.includes("email")) return `Email is madan@example.com`;
    if (f.name.includes("phone")) return `Phone number is 9876543210`;
    if (f.name.includes("dob") || f.name.includes("birth")) return `Date of birth is 15th August 1998`;
    if (f.type === "select" && f.options?.[0]) return `${f.label} is ${f.options[0]}`;
    return `${f.label} is sample`;
  });

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto py-24 text-center">
        <div className="inline-block w-8 h-8 border-2 border-neutral-900 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-[#737373] mt-3 font-mono">Loading form schema...</p>
      </div>
    );
  }

  if (serverError && !form) {
    return (
      <div className="max-w-md mx-auto py-20 px-4 text-left">
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700">
          <p className="font-semibold">Unable to load form</p>
          <p className="mt-1">{serverError}</p>
        </div>
        <button
          onClick={() => setView({ name: "dashboard" })}
          className="mt-4 px-4 py-2 bg-neutral-900 text-white rounded-lg text-xs"
        >
          Return to Dashboard
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-8 py-6 text-left">
      {/* Top Breadcrumb & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-[#E5E5E5] gap-4">
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setView({ name: "dashboard" })}
            className="p-1.5 rounded-lg border border-[#E5E5E5] hover:bg-neutral-100 text-neutral-600 hover:text-black transition-colors cursor-pointer"
            title="Back to Dashboard"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-lg font-bold tracking-tight text-neutral-900">
                {form?.title}
              </h1>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-neutral-100 border border-neutral-200 text-neutral-600">
                ID #{formId}
              </span>
            </div>
            <p className="text-xs text-[#737373] mt-0.5 line-clamp-1">
              {form?.description || "Voice-assisted form filling session."}
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-2">
          {/* TTS Speech Synthesis Toggle */}
          <button
            onClick={() => {
              const next = !ttsEnabled;
              setTtsEnabled(next);
              storageService.saveSettings({ voicePlayback: next });
              toast(next ? "Voice audio playback enabled." : "Voice audio playback muted.", "info");
            }}
            className={`p-2 rounded-lg border text-xs flex items-center space-x-1.5 transition-colors cursor-pointer ${
              ttsEnabled
                ? "bg-neutral-900 text-white border-neutral-900"
                : "border-[#E5E5E5] text-neutral-600 hover:bg-neutral-50"
            }`}
            title="Toggle Assistant Speech Synthesis"
          >
            {ttsEnabled ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline">{ttsEnabled ? "Audio On" : "Muted"}</span>
          </button>

          <button
            onClick={handleSaveDraft}
            className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors flex items-center space-x-1.5 cursor-pointer"
          >
            <Save className="w-3.5 h-3.5" />
            <span>Save Draft</span>
          </button>

          {progressPercent === 100 ? (
            <button
              onClick={handleDirectSubmit}
              disabled={submitting}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold transition-colors flex items-center space-x-1.5 cursor-pointer shadow-xs disabled:opacity-50"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Submitting...</span>
                </>
              ) : (
                <>
                  <span>Submit Form Now</span>
                  <Send className="w-3.5 h-3.5" />
                </>
              )}
            </button>
          ) : (
            <button
              onClick={() =>
                setView({
                  name: "review",
                  formId,
                  formTitle: form?.title,
                  values,
                })
              }
              className="px-4 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors flex items-center space-x-1.5 cursor-pointer shadow-xs"
            >
              <span>Review & Submit</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Progress Bar Header */}
      <div className="mt-4 p-3.5 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center space-x-3">
          <span className="text-xs font-semibold text-neutral-900">
            Form Completion:
          </span>
          <div className="w-40 sm:w-64 bg-neutral-200 h-2 rounded-full overflow-hidden">
            <div
              className="bg-neutral-900 h-full transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span className="text-xs font-bold text-neutral-900 font-mono">
            {progressPercent}%
          </span>
        </div>

        <div className="text-[11px] text-neutral-500 font-mono">
          Required: {filledRequiredCount}/{requiredFields.length} completed • AI Fields: {aiFilledFields.length}
        </div>
      </div>

      {/* Split-Screen Workspace (Left: Voice Assistant, Right: Live Form Preview) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mt-6 items-start">
        {/* LEFT PANEL: Voice Assistant */}
        <div className="lg:col-span-5 space-y-4">
          {/* Main Voice Control Card */}
          <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 text-center space-y-5 shadow-xs">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase tracking-widest text-neutral-400">
                Interactive Voice Engine
              </span>
              <div className="flex items-center space-x-2">
                {isRecording && (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-red-100 text-red-700 border border-red-200 animate-pulse font-semibold">
                    ● REC {recordingTimeFormatted}
                  </span>
                )}
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded-full uppercase ${
                    isListening || isRecording
                      ? "bg-red-50 text-red-700 border border-red-200 animate-pulse"
                      : isTranscribing
                      ? "bg-amber-50 text-amber-700 border border-amber-200 animate-pulse"
                      : "bg-neutral-100 text-neutral-600 border border-neutral-200"
                  }`}
                >
                  {voiceState}
                </span>
              </div>
            </div>

            {/* Circular Microphone Button */}
            <div className="py-2 flex justify-center">
              <MicrophoneButton
                state={voiceState}
                onClick={handleToggleListening}
                disabled={isTranscribing}
                size="lg"
              />
            </div>

            {/* Audio Waveform */}
            <div>
              <AudioWaveform isListening={isListening || isRecording} count={24} height="h-8" />
            </div>

            {/* Status Message */}
            <div className="bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl p-3 text-xs text-neutral-700 space-y-1">
              <p className="font-medium">{statusMessage}</p>
              {transcriptionMeta?.model && (
                <p className="text-[10px] text-neutral-400 font-mono">
                  Cloud Whisper STT: {transcriptionMeta.model}
                  {transcriptionMeta.duration ? ` • ${transcriptionMeta.duration.toFixed(1)}s audio` : ""}
                </p>
              )}
            </div>

            {/* Action Buttons: Stop / Cancel / Clear */}
            <div className="flex items-center justify-center space-x-3 pt-1">
              {isTranscribing ? (
                <button
                  type="button"
                  disabled
                  className="px-4 py-1.5 bg-neutral-100 text-neutral-500 rounded-lg text-xs font-medium border border-neutral-200 flex items-center space-x-1.5 cursor-not-allowed"
                >
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Transcribing Audio...</span>
                </button>
              ) : isRecording ? (
                <>
                  <button
                    type="button"
                    onClick={stopListening}
                    className="px-4 py-1.5 bg-neutral-900 text-white rounded-lg text-xs font-medium hover:bg-neutral-800 transition-colors cursor-pointer flex items-center space-x-1.5 shadow-xs"
                  >
                    <Square className="w-3 h-3 fill-current" />
                    <span>Stop & Transcribe</span>
                  </button>
                  <button
                    type="button"
                    onClick={cancelListening}
                    className="px-3 py-1.5 border border-red-200 bg-red-50 hover:bg-red-100 text-red-700 rounded-lg text-xs transition-colors cursor-pointer flex items-center space-x-1"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>Cancel</span>
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={handleToggleListening}
                  className="px-4 py-1.5 bg-[#111111] text-white rounded-lg text-xs font-medium hover:bg-neutral-800 transition-colors cursor-pointer"
                >
                  Start Speaking
                </button>
              )}

              <button
                type="button"
                onClick={() => {
                  resetTranscript();
                  setConversation([
                    {
                      role: "assistant",
                      text: "Conversation reset. I'm ready to listen.",
                      meta: "Reset",
                    },
                  ]);
                }}
                className="px-3 py-1.5 border border-[#E5E5E5] hover:bg-neutral-50 text-neutral-600 rounded-lg text-xs transition-colors cursor-pointer"
              >
                Reset Chat
              </button>
            </div>
          </div>

          {/* Transcript & Conversation Panel */}
          <VoiceTranscriptPanel
            messages={conversation}
            interimTranscript={interimTranscript}
            currentStatus={voiceState}
            statusMessage={statusMessage}
            onSimulateVoice={processTranscript}
            simulatedText={simulatedText}
            setSimulatedText={setSimulatedText}
            samplePrompts={samplePrompts}
          />
        </div>

        {/* RIGHT PANEL: Live Form Preview */}
        <div className="lg:col-span-7 space-y-4">
          <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs">
            <div className="flex items-center justify-between pb-4 border-b border-[#E5E5E5] mb-5">
              <div>
                <h3 className="text-sm font-semibold text-neutral-900 tracking-tight">
                  Live Form Preview
                </h3>
                <p className="text-[11px] text-[#737373]">
                  Values automatically populate as you speak. You can also edit manually.
                </p>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={() =>
                    setView({
                      name: "editor",
                      formId,
                      formTitle: form?.title,
                    })
                  }
                  className="inline-flex items-center space-x-1 px-2.5 py-1 text-xs border border-[#E5E5E5] hover:border-black rounded-lg transition-colors cursor-pointer"
                >
                  <Edit3 className="w-3 h-3" />
                  <span>Editor View</span>
                </button>
              </div>
            </div>

            {/* Attention / Ambiguity Review Banner */}
            {Object.keys(needsReviewFields).length > 0 && (
              <div className="mb-5 p-3.5 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 text-left">
                <div className="flex items-center justify-between pb-1.5 border-b border-amber-200/60 mb-2">
                  <span className="font-semibold flex items-center space-x-1.5">
                    <span>Field Confirmation Needed</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => setNeedsReviewFields({})}
                    className="text-[11px] text-amber-700 hover:text-amber-950 font-medium cursor-pointer"
                  >
                    Dismiss
                  </button>
                </div>
                <div className="space-y-1 text-[11px]">
                  {Object.entries(needsReviewFields).map(([k, msg]) => {
                    const fieldLabel = form?.schema_json?.fields?.find((f) => f.name === k)?.label || k;
                    return (
                      <div key={k} className="flex items-start space-x-1.5">
                        <span className="font-semibold text-amber-950">{fieldLabel}:</span>
                        <span>{msg}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Live Interactive Form Fields */}
            <FormRenderer
              schema={form?.schema_json}
              values={values}
              onChange={setValues}
              errors={errors}
              highlightedFields={highlightedFields}
              aiFilledFields={aiFilledFields}
            />

            {/* Bottom Actions */}
            <div className="mt-8 pt-4 border-t border-[#E5E5E5] flex items-center justify-between">
              <button
                type="button"
                onClick={() => {
                  const initial = {};
                  form?.schema_json?.fields?.forEach((f) => {
                    initial[f.name] = f.type === "checkbox" ? false : "";
                  });
                  setValues(initial);
                  setAiFilledFields([]);
                  setErrors({});
                  toast("Form fields cleared.", "info");
                }}
                className="text-xs text-neutral-500 hover:text-black cursor-pointer"
              >
                Clear All Fields
              </button>

              <button
                type="button"
                onClick={() =>
                  setView({
                    name: "review",
                    formId,
                    formTitle: form?.title,
                    values,
                  })
                }
                className="inline-flex items-center space-x-2 px-5 py-2 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-all shadow-xs cursor-pointer"
              >
                <span>Continue to Review</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
