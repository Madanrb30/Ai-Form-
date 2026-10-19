import React, { useEffect, useState, useCallback, useRef } from "react";
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
  Mic,
  Radio,
  Pause,
  Play,
  RotateCcw,
  FastForward,
  Upload,
  Download,
  FileText,
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
import PdfUploadModal from "../components/forms/PdfUploadModal";

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
  const [pdfFilledFields, setPdfFilledFields] = useState([]);
  const [manuallyEditedFields, setManuallyEditedFields] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [missingFields, setMissingFields] = useState([]);
  const [needsReviewFields, setNeedsReviewFields] = useState({});

  // PDF Extraction & Export State
  const [pdfUploadModalOpen, setPdfUploadModalOpen] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);

  // Voice Interaction State (10 explicit states for ChatGPT Voice Mode):
  // 'idle' | 'initializing' | 'listening' | 'recording' | 'transcribing' | 'processing' | 'speaking' | 'confirmation' | 'error' | 'stopped'
  const [voiceState, setVoiceState] = useState("idle");
  const [statusMessage, setStatusMessage] = useState("Assistant ready. Click 'Start Voice Assistant' to begin natural conversation.");
  const [conversation, setConversation] = useState([
    {
      role: "assistant",
      text: "I'm ready to help you fill this form. Click 'Start Voice Assistant' to begin.",
      meta: "Ready",
    },
  ]);

  const [simulatedText, setSimulatedText] = useState("");
  const [ttsEnabled, setTtsEnabled] = useState(() => storageService.getSettings().voicePlayback);
  const [continuousMode, setContinuousMode] = useState(() => Boolean(storageService.getSettings().continuousMode));

  // Refs for safe continuous lifecycle and unmount protection
  const continuousModeRef = useRef(continuousMode);
  useEffect(() => {
    continuousModeRef.current = continuousMode;
  }, [continuousMode]);

  const voiceStateRef = useRef(voiceState);
  useEffect(() => {
    voiceStateRef.current = voiceState;
  }, [voiceState]);

  const isMountedRef = useRef(true);
  const isSubmittedRef = useRef(false);
  const isStoppedRef = useRef(false);
  const isProcessingTurnRef = useRef(false);
  const draftSaveTimeoutRef = useRef(null);

  // Cloud Audio Recording & Speech Recognition Hook (Sarvam AI primary, Groq Whisper fallback)
  const {
    isSupported,
    isListening,
    isRecording,
    isTranscribing,
    recordingSeconds,
    recordingTimeFormatted,
    maxRecordingSeconds,
    warningThresholdSeconds,
    remainingSeconds,
    isApproachingLimit,
    isLimitReached,
    transcript,
    interimTranscript,
    error: speechError,
    transcriptionMeta,
    startListening,
    stopListening,
    cancelListening,
    resetTranscript,
  } = useVoiceRecognition();

  // Debounced server-side draft saver with instant local storage persistence
  const scheduleDraftSave = useCallback(
    (updatedValues, activeSessionId) => {
      // 1. Immediately persist to client local storage (0ms latency, refresh resilient)
      storageService.saveDraft(formId, updatedValues, form?.title || "Form Draft", user?.id);

      // 2. Debounce backend network save to coalesce rapid conversational turns
      if (draftSaveTimeoutRef.current) {
        clearTimeout(draftSaveTimeoutRef.current);
      }
      draftSaveTimeoutRef.current = setTimeout(() => {
        api.saveDraft(formId, updatedValues, activeSessionId).catch(() => {});
      }, 1200);
    },
    [formId, form?.title, user?.id]
  );

  // Lifecycle teardown on unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      ttsService.stop();
      cancelListening();
      if (draftSaveTimeoutRef.current) {
        clearTimeout(draftSaveTimeoutRef.current);
      }
    };
  }, [cancelListening]);

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
  }, [formId, toast, user?.id]);

  // Synchronize Voice Recognition & Cloud Whisper State
  useEffect(() => {
    if (isStoppedRef.current || isSubmittedRef.current) return;

    if (speechError) {
      const isNoSpeech =
        speechError.toLowerCase().includes("no speech was detected") ||
        speechError.toLowerCase().includes("no speech detected");

      if (isNoSpeech && continuousModeRef.current && voiceStateRef.current !== "stopped" && !isSubmittedRef.current) {
        setStatusMessage("No speech detected. Listening for your response...");
        setVoiceState("listening");
        const timer = setTimeout(() => {
          if (isMountedRef.current && continuousModeRef.current && !isStoppedRef.current && voiceStateRef.current !== "stopped" && !isSubmittedRef.current) {
            startListening({ autoStopOnSilence: true, silenceDuration: 1800 });
          }
        }, 800);
        return () => clearTimeout(timer);
      } else {
        setVoiceState("error");
        setStatusMessage(speechError);
      }
    } else if (isTranscribing) {
      setVoiceState("transcribing");
      setStatusMessage("Transcribing audio via STT provider...");
    } else if (isRecording) {
      setVoiceState("recording");
      if (isApproachingLimit) {
        setStatusMessage(
          `Approaching limit (${remainingSeconds}s remaining). Finalizing turn before ${maxRecordingSeconds}s ceiling...`
        );
      } else {
        setStatusMessage(
          continuousMode
            ? `Listening & recording... (${recordingTimeFormatted} / 0:${maxRecordingSeconds}). Speak your response.`
            : `Recording audio... (${recordingTimeFormatted} / 0:${maxRecordingSeconds}). Speak clearly, then click Stop.`
        );
      }
    }
  }, [
    isRecording,
    isTranscribing,
    recordingTimeFormatted,
    speechError,
    continuousMode,
    startListening,
    isApproachingLimit,
    remainingSeconds,
    maxRecordingSeconds,
  ]);

  // Resume listening in Continuous Conversation mode
  const resumeContinuousListening = useCallback(() => {
    if (!isMountedRef.current || isSubmittedRef.current || isStoppedRef.current) return;
    if (continuousModeRef.current && voiceStateRef.current !== "stopped") {
      setVoiceState("listening");
      setStatusMessage("Listening... Speak your next detail or answer.");
      startListening({ autoStopOnSilence: true, silenceDuration: 1800 });
    } else {
      setVoiceState("idle");
      setStatusMessage("Assistant ready. Click 'Start Voice Assistant' or the microphone to speak.");
    }
  }, [startListening]);

  // Handle Speech Extraction Mapping via Conversational AI API
  const processTranscript = useCallback(
    async (spokenText) => {
      if (!spokenText || !spokenText.trim() || !form) return;
      if (isProcessingTurnRef.current || isSubmittedRef.current) return;

      isProcessingTurnRef.current = true;
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
        const clearedKeys = turnRes.cleared_fields || [];
        const reviews = turnRes.needs_review || {};
        setNeedsReviewFields(reviews);

        // Update aiFilledFields: add newly filled, remove cleared or empty
        setAiFilledFields((prev) => {
          const nextSet = new Set(prev);
          matchedKeys.forEach((k) => nextSet.add(k));
          clearedKeys.forEach((k) => nextSet.delete(k));
          (turnRes.missing_fields || []).forEach((k) => nextSet.delete(k));
          return Array.from(nextSet);
        });

        if (clearedKeys.length > 0) {
          setHighlightedFields(clearedKeys);
          setTimeout(() => {
            if (isMountedRef.current) setHighlightedFields([]);
          }, 2500);
        } else if (matchedKeys.length > 0) {
          setHighlightedFields(matchedKeys);
          setTimeout(() => {
            if (isMountedRef.current) setHighlightedFields([]);
          }, 3000);
        }

        setErrors((prev) => {
          const next = { ...prev };
          matchedKeys.forEach((k) => delete next[k]);
          clearedKeys.forEach((k) => delete next[k]);
          Object.assign(next, reviews);
          return next;
        });

        // Autosave draft server-side (debounced) and locally (instant)
        const activeSessionId = turnRes.session_id || sessionId;
        scheduleDraftSave(updated, activeSessionId);

        if (turnRes.is_submitted || turnRes.submission_id) {
          // Form successfully submitted by the conversational agent!
          if (draftSaveTimeoutRef.current) {
            clearTimeout(draftSaveTimeoutRef.current);
          }
          isSubmittedRef.current = true;
          isStoppedRef.current = true;
          ttsService.stop();
          cancelListening();
          storageService.deleteDraft(formId, user?.id);
          setVoiceState("confirmation");
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
            if (isMountedRef.current) {
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
            }
          }, 1800);
          return;
        }

        const assistantReply = turnRes.assistant_response || "Information updated.";
        const clearedCount = clearedKeys.length;
        const metaText = clearedCount > 0
          ? `Cleared ${clearedCount} field(s)`
          : matchedKeys.length > 0
          ? `Updated ${matchedKeys.length} field(s)`
          : "Guidance";

        setConversation((prev) => [
          ...prev,
          {
            role: "assistant",
            text: assistantReply,
            meta: metaText,
          },
        ]);

        if (turnRes.is_completed) {
          setVoiceState("confirmation");
          toast("All required fields are completed! Speak 'confirm' or click to submit.", "success");
        } else {
          // If form is not complete, ensure voice state does not stay stuck in confirmation
          if (voiceStateRef.current === "confirmation") {
            setVoiceState("idle");
          }
        }

        // Assistant Speaking & Continuous Audio Resumption
        if (ttsEnabled) {
          if (!turnRes.is_completed) {
            setVoiceState("speaking");
          }
          setStatusMessage("Assistant speaking response...");
          ttsService.speak(assistantReply, {
            onStart: () => {
              if (isMountedRef.current && !isStoppedRef.current) {
                if (!turnRes.is_completed) setVoiceState("speaking");
              }
            },
            onEnd: () => {
              if (isMountedRef.current && !isStoppedRef.current) {
                resumeContinuousListening();
              }
            },
            onError: () => {
              if (isMountedRef.current && !isStoppedRef.current) {
                resumeContinuousListening();
              }
            },
          });
        } else {
          if (!turnRes.is_completed) {
            setVoiceState("speaking");
          }
          setStatusMessage("Assistant response displayed.");
          setTimeout(() => {
            if (isMountedRef.current && !isStoppedRef.current) {
              resumeContinuousListening();
            }
          }, 1200);
        }
      } catch (err) {
        setVoiceState("error");
        setStatusMessage(`AI processing error: ${err.message}`);
        toast(`Voice mapping error: ${err.message}`, "error");
      } finally {
        isProcessingTurnRef.current = false;
        resetTranscript();
        setSimulatedText("");
      }
    },
    [form, formId, sessionId, values, resetTranscript, ttsEnabled, resumeContinuousListening, cancelListening, toast, setView, user?.id]
  );

  // Automatically trigger processing when transcription completes
  useEffect(() => {
    if (!isListening && !isTranscribing && transcript && transcript.trim()) {
      processTranscript(transcript);
    }
  }, [isListening, isTranscribing, transcript, processTranscript]);

  // Voice Interaction Control Handlers for Continuous ChatGPT-like Voice Mode
  const handleStartSession = useCallback(() => {
    if (voiceStateRef.current === "processing" || voiceStateRef.current === "initializing") return;
    if (!isSupported) {
      toast("Audio recording is not supported in this browser environment. Please use manual input below.", "error");
      return;
    }

    isStoppedRef.current = false;
    continuousModeRef.current = true;
    if (!continuousMode) setContinuousMode(true);
    setVoiceState("initializing");
    setStatusMessage("Initializing voice session...");

    // Find the first unfilled required field (or first unfilled field) to guide the user naturally
    const fieldsList = form?.schema_json?.fields || [];
    const firstMissing = fieldsList.find(
      (f) => f.required && (!values[f.name] || String(values[f.name]).trim() === "")
    ) || fieldsList.find(
      (f) => !values[f.name] || String(values[f.name]).trim() === ""
    );

    const greetingText = firstMissing
      ? `Hello! I am ready to help you fill out the ${form?.title || "form"}. What is your ${firstMissing.label || firstMissing.name}?`
      : `Hello! I am ready to help you fill out the ${form?.title || "form"}. You can start speaking your details.`;

    setConversation((prev) => [
      ...prev,
      {
        role: "assistant",
        text: greetingText,
        meta: "Voice Session Started",
      },
    ]);

    if (ttsEnabled) {
      setVoiceState("speaking");
      setStatusMessage("Assistant speaking greeting...");
      ttsService.speak(greetingText, {
        onStart: () => {
          if (isMountedRef.current && !isStoppedRef.current) {
            setVoiceState("speaking");
          }
        },
        onEnd: () => {
          if (isMountedRef.current && !isStoppedRef.current) {
            setVoiceState("listening");
            setStatusMessage("Listening... Speak your response.");
            startListening({ autoStopOnSilence: true, silenceDuration: 1800 });
          }
        },
        onError: () => {
          if (isMountedRef.current && !isStoppedRef.current) {
            setVoiceState("listening");
            setStatusMessage("Listening... Speak your response.");
            startListening({ autoStopOnSilence: true, silenceDuration: 1800 });
          }
        },
      });
    } else {
      setVoiceState("listening");
      setStatusMessage("Listening... Speak your response.");
      startListening({ autoStopOnSilence: true, silenceDuration: 1800 });
    }
  }, [form, values, isSupported, toast, ttsEnabled, startListening]);

  const handleStopSession = useCallback(() => {
    isStoppedRef.current = true;
    ttsService.stop();
    cancelListening();
    setVoiceState("stopped");
    setStatusMessage("Voice session stopped. Click 'Start Voice Assistant' to resume.");
  }, [cancelListening]);

  const handleToggleListening = useCallback(() => {
    if (voiceStateRef.current === "processing" || voiceStateRef.current === "initializing") return;

    if (voiceStateRef.current === "speaking") {
      // User interruption: immediately interrupt assistant speech and begin listening
      ttsService.stop();
      isStoppedRef.current = false;
      setVoiceState("listening");
      setStatusMessage("Interrupted. Listening to you...");
      startListening({ autoStopOnSilence: true, silenceDuration: 1800 });
    } else if (voiceStateRef.current === "listening" || voiceStateRef.current === "recording" || isRecording || isListening) {
      // User signals they are done speaking early
      stopListening();
    } else if (voiceStateRef.current === "confirmation") {
      // In confirmation state, click mic to speak confirmation
      isStoppedRef.current = false;
      setVoiceState("listening");
      setStatusMessage("Listening for confirmation ('confirm' or 'yes')...");
      startListening({ autoStopOnSilence: true, silenceDuration: 1800 });
    } else {
      // Idle, stopped, or error: Start session
      handleStartSession();
    }
  }, [handleStartSession, isListening, isRecording, startListening, stopListening]);

  const toggleContinuousMode = () => {
    const next = !continuousMode;
    setContinuousMode(next);
    storageService.saveSettings({ continuousMode: next });
    toast(
      next
        ? "Continuous Conversation mode enabled: Assistant will automatically listen after speaking."
        : "Continuous Conversation mode disabled: Manual click required per turn.",
      "info"
    );
  };

  // Independent PDF Export Handler (Requirement 8)
  const handleExportPdf = async () => {
    setExportingPdf(true);
    try {
      toast("Generating completed form PDF document...", "info");
      await api.exportFormPdf(formId, values, `${form?.title || "Form"}_completed.pdf`);
      toast("PDF document exported successfully.", "success");
    } catch (err) {
      toast(`PDF export failed: ${err.message}`, "error");
    } finally {
      setExportingPdf(false);
    }
  };

  // PDF Extraction & Auto-Fill Handler
  const handlePdfExtractionSuccess = useCallback(
    (result) => {
      const extracted = result.extracted_fields || {};
      const nextValues = { ...values };

      // Requirement 6: Do not overwrite manually corrected values when extraction is repeated
      const newlyPopulatedKeys = [];
      Object.entries(extracted).forEach(([k, v]) => {
        if (!manuallyEditedFields.includes(k)) {
          nextValues[k] = v;
          newlyPopulatedKeys.push(k);
        }
      });

      setValues(nextValues);
      setPdfFilledFields((prev) => Array.from(new Set([...prev, ...newlyPopulatedKeys])));
      setHighlightedFields(newlyPopulatedKeys);
      setTimeout(() => {
        if (isMountedRef.current) setHighlightedFields([]);
      }, 3500);

      const reviews = result.needs_review || {};
      setNeedsReviewFields(reviews);
      const missing = result.missing_required_fields || [];
      setMissingFields(missing);

      setErrors((prev) => {
        const next = { ...prev };
        newlyPopulatedKeys.forEach((k) => delete next[k]);
        Object.assign(next, reviews);
        return next;
      });

      // Schedule draft save
      scheduleDraftSave(nextValues, sessionId);

      // Conversational Follow-Up Integration (Requirement 5)
      const matchedCount = newlyPopulatedKeys.length;
      const missingCount = missing.length;
      let assistantMsg = "";
      if (missingCount > 0) {
        const missingLabels = missing
          .map((name) => form?.schema_json?.fields?.find((f) => f.name === name)?.label || name)
          .join(", ");
        assistantMsg = `I have extracted your personal details from the PDF. ${matchedCount} field${matchedCount === 1 ? '' : 's'} were populated. ${missingCount} required field${missingCount === 1 ? '' : 's'} still need information: ${missingLabels}. Would you like to speak or enter them now?`;
      } else {
        assistantMsg = `I have extracted your personal details from the PDF and all required fields are complete! Please review the populated values and submit when ready.`;
      }

      setConversation((prev) => [
        ...prev,
        {
          role: "assistant",
          text: assistantMsg,
          meta: "PDF Auto-Fill",
        },
      ]);

      if (ttsEnabled) {
        ttsService.speak(assistantMsg);
      }

      toast(
        `PDF extraction complete: ${matchedCount} field(s) populated.`,
        "success"
      );
    },
    [values, manuallyEditedFields, scheduleDraftSave, sessionId, form, ttsEnabled, toast]
  );

  // Draft Save Handler
  const handleSaveDraft = async () => {
    if (draftSaveTimeoutRef.current) {
      clearTimeout(draftSaveTimeoutRef.current);
    }
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
    if (draftSaveTimeoutRef.current) {
      clearTimeout(draftSaveTimeoutRef.current);
    }
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
        <div className="flex flex-wrap items-center gap-2">
          {/* Continuous Conversation Toggle */}
          <button
            type="button"
            onClick={toggleContinuousMode}
            className={`px-3 py-1.5 rounded-lg border text-xs font-medium flex items-center space-x-1.5 transition-colors cursor-pointer ${
              continuousMode
                ? "bg-emerald-50 border-emerald-300 text-emerald-800"
                : "border-[#E5E5E5] text-neutral-600 hover:bg-neutral-50"
            }`}
            title="Toggle Continuous Conversation Mode (hands-free conversational turns)"
          >
            <Radio className={`w-3.5 h-3.5 ${continuousMode ? "text-emerald-600 animate-pulse" : "text-neutral-400"}`} />
            <span>{continuousMode ? "Continuous: ON" : "Continuous: OFF"}</span>
          </button>

          {/* TTS Speech Synthesis Toggle */}
          <button
            type="button"
            onClick={() => {
              const next = !ttsEnabled;
              setTtsEnabled(next);
              storageService.saveSettings({ voicePlayback: next });
              toast(next ? "Voice audio playback enabled." : "Voice audio playback muted.", "info");
            }}
            className={`px-3 py-1.5 rounded-lg border text-xs flex items-center space-x-1.5 transition-colors cursor-pointer ${
              ttsEnabled
                ? "bg-neutral-900 text-white border-neutral-900"
                : "border-[#E5E5E5] text-neutral-600 hover:bg-neutral-50"
            }`}
            title="Toggle Assistant Speech Synthesis"
          >
            {ttsEnabled ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
            <span>{ttsEnabled ? "Audio On" : "Muted"}</span>
          </button>

          {/* PDF Auto-Fill Button */}
          <button
            type="button"
            onClick={() => setPdfUploadModalOpen(true)}
            className="px-3 py-1.5 border border-neutral-900 bg-neutral-900 hover:bg-black text-white rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition-colors cursor-pointer shadow-xs"
            title="Upload personal information PDF (resume, ID, application) to auto-fill form"
          >
            <Upload className="w-3.5 h-3.5 text-neutral-200" />
            <span>Auto-Fill from PDF</span>
          </button>

          {/* Export PDF Button (Independent of Submission) */}
          <button
            type="button"
            onClick={handleExportPdf}
            disabled={exportingPdf}
            className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
            title="Export completed PDF independently of submission"
          >
            {exportingPdf ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-neutral-700" />
            ) : (
              <Download className="w-3.5 h-3.5" />
            )}
            <span>Export PDF</span>
          </button>

          <button
            type="button"
            onClick={handleSaveDraft}
            className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors flex items-center space-x-1.5 cursor-pointer"
          >
            <Save className="w-3.5 h-3.5" />
            <span>Save Draft</span>
          </button>

          {progressPercent === 100 ? (
            <button
              type="button"
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
              type="button"
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
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded-full border font-semibold flex items-center space-x-1 ${
                      isApproachingLimit
                        ? "bg-amber-100 text-amber-900 border-amber-300 animate-pulse"
                        : "bg-red-100 text-red-700 border-red-200 animate-pulse"
                    }`}
                  >
                    <span
                      className={`w-1.5 h-1.5 rounded-full animate-ping mr-1 ${
                        isApproachingLimit ? "bg-amber-600" : "bg-red-600"
                      }`}
                    />
                    {isApproachingLimit
                      ? `REC ${recordingTimeFormatted} / 0:${maxRecordingSeconds} (${remainingSeconds}s left)`
                      : `REC ${recordingTimeFormatted} / 0:${maxRecordingSeconds}`}
                  </span>
                )}
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded-full uppercase font-medium ${
                    voiceState === "listening"
                      ? "bg-red-50 text-red-700 border border-red-200 animate-pulse"
                      : voiceState === "recording"
                      ? "bg-red-100 text-red-800 border border-red-300 animate-pulse"
                      : voiceState === "transcribing" || voiceState === "initializing"
                      ? "bg-amber-50 text-amber-700 border border-amber-200 animate-pulse"
                      : voiceState === "processing"
                      ? "bg-amber-100 text-amber-800 border border-amber-300 animate-pulse"
                      : voiceState === "speaking"
                      ? "bg-blue-50 text-blue-700 border border-blue-200 animate-pulse"
                      : voiceState === "confirmation"
                      ? "bg-emerald-50 text-emerald-700 border border-emerald-300 animate-pulse"
                      : voiceState === "error"
                      ? "bg-rose-50 text-rose-700 border border-rose-200"
                      : "bg-neutral-100 text-neutral-600 border border-neutral-200"
                  }`}
                >
                  {voiceState}
                </span>
              </div>
            </div>

            {/* Continuous Conversation Active Banner */}
            {continuousMode && (
              <div className="bg-emerald-50/70 border border-emerald-200/80 rounded-xl px-3 py-1.5 flex items-center justify-between text-[11px] text-emerald-800">
                <div className="flex items-center space-x-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
                  <span className="font-semibold">Continuous Voice Active</span>
                </div>
                <span className="text-[10px] text-emerald-600 font-mono">ChatGPT Voice Mode</span>
              </div>
            )}

            {/* Circular Microphone Button */}
            <div className="py-2 flex justify-center">
              <MicrophoneButton
                state={voiceState}
                onClick={handleToggleListening}
                disabled={voiceState === "transcribing" || voiceState === "processing"}
                size="lg"
              />
            </div>

            {/* Audio Waveform */}
            <div>
              <AudioWaveform isListening={isListening || isRecording} count={24} height="h-8" />
            </div>

            {/* Turn Duration & Countdown Indicator */}
            {isRecording && (
              <div className="space-y-1.5 px-2 text-left bg-neutral-50 border border-neutral-200 rounded-xl p-2.5">
                <div className="flex items-center justify-between text-[11px] font-mono">
                  <span
                    className={
                      isApproachingLimit
                        ? "text-amber-800 font-semibold flex items-center gap-1.5"
                        : "text-neutral-600"
                    }
                  >
                    {isApproachingLimit && (
                      <span className="inline-block w-2 h-2 rounded-full bg-amber-500 animate-ping" />
                    )}
                    {isApproachingLimit
                      ? `Approaching limit: ${remainingSeconds}s left (wrapping up turn)`
                      : `Turn Duration: ${recordingTimeFormatted} / 0:${maxRecordingSeconds}`}
                  </span>
                  <span className="text-[10px] text-neutral-400 font-mono">
                    Limit: {maxRecordingSeconds}s
                  </span>
                </div>
                <div className="w-full bg-neutral-200 h-1.5 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-300 ${
                      isApproachingLimit ? "bg-amber-500" : "bg-neutral-900"
                    }`}
                    style={{
                      width: `${Math.min(100, (recordingSeconds / maxRecordingSeconds) * 100)}%`,
                    }}
                  />
                </div>
              </div>
            )}

            {/* Status Message */}
            <div className="bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl p-3 text-xs text-neutral-700 space-y-1">
              <p className="font-medium">{statusMessage}</p>
              {transcriptionMeta?.model && (
                <p className="text-[10px] text-neutral-400 font-mono">
                  {(transcriptionMeta.provider ? transcriptionMeta.provider.toUpperCase() : "STT")}: {transcriptionMeta.model}
                  {transcriptionMeta.duration ? ` • ${transcriptionMeta.duration.toFixed(1)}s audio` : ""}
                </p>
              )}
              {transcriptionMeta?.fallback_used && (
                <div className="text-[10px] text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2 py-1 mt-1 font-mono text-left">
                  <span className="font-semibold">Notice:</span> {transcriptionMeta.fallback_reason || "Transcribed via fallback STT provider."}
                </div>
              )}
            </div>

            {/* Action Buttons: Multi-State Controls */}
            <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
              {voiceState === "processing" || voiceState === "transcribing" || voiceState === "initializing" ? (
                <>
                  <button
                    type="button"
                    disabled
                    className="px-4 py-1.5 bg-neutral-100 text-neutral-500 rounded-lg text-xs font-medium border border-neutral-200 flex items-center space-x-1.5 cursor-not-allowed"
                  >
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>{voiceState === "transcribing" ? "Transcribing Audio..." : voiceState === "initializing" ? "Starting Voice..." : "Processing AI..."}</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleStopSession}
                    className="px-3 py-1.5 border border-[#E5E5E5] hover:bg-neutral-50 text-neutral-600 rounded-lg text-xs transition-colors cursor-pointer flex items-center space-x-1"
                  >
                    <Square className="w-3 h-3 fill-current" />
                    <span>Stop</span>
                  </button>
                </>
              ) : voiceState === "listening" || voiceState === "recording" ? (
                <>
                  <button
                    type="button"
                    onClick={stopListening}
                    className="px-4 py-1.5 bg-neutral-900 text-white rounded-lg text-xs font-medium hover:bg-neutral-800 transition-colors cursor-pointer flex items-center space-x-1.5 shadow-xs"
                  >
                    <Square className="w-3 h-3 fill-current" />
                    <span>Done Speaking</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleStopSession}
                    className="px-3 py-1.5 border border-red-200 bg-red-50 hover:bg-red-100 text-red-700 rounded-lg text-xs transition-colors cursor-pointer flex items-center space-x-1"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>Stop</span>
                  </button>
                </>
              ) : voiceState === "speaking" ? (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      ttsService.stop();
                      if (continuousModeRef.current) resumeContinuousListening();
                      else {
                        setVoiceState("idle");
                        setStatusMessage("Assistant ready.");
                      }
                    }}
                    className="px-4 py-1.5 bg-neutral-900 hover:bg-neutral-800 text-white rounded-lg text-xs font-medium transition-colors cursor-pointer flex items-center space-x-1.5 shadow-xs"
                  >
                    <FastForward className="w-3.5 h-3.5" />
                    <span>Interrupt / Speak</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleStopSession}
                    className="px-3 py-1.5 border border-[#E5E5E5] hover:bg-neutral-50 text-neutral-600 rounded-lg text-xs transition-colors cursor-pointer flex items-center space-x-1"
                  >
                    <Square className="w-3 h-3 fill-current" />
                    <span>Stop</span>
                  </button>
                </>
              ) : voiceState === "confirmation" ? (
                <>
                  <button
                    type="button"
                    onClick={() => processTranscript("confirm submission")}
                    className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-medium transition-colors cursor-pointer flex items-center space-x-1.5 shadow-xs"
                  >
                    <Send className="w-3.5 h-3.5" />
                    <span>Confirm & Submit</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleToggleListening}
                    className="px-3 py-1.5 border border-neutral-300 hover:bg-neutral-50 text-neutral-700 rounded-lg text-xs font-medium transition-colors cursor-pointer flex items-center space-x-1"
                  >
                    <Mic className="w-3.5 h-3.5" />
                    <span>Speak Answer</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleStopSession}
                    className="px-3 py-1.5 border border-[#E5E5E5] hover:bg-neutral-50 text-neutral-600 rounded-lg text-xs transition-colors cursor-pointer flex items-center space-x-1"
                  >
                    <Square className="w-3 h-3 fill-current" />
                    <span>Stop</span>
                  </button>
                </>
              ) : voiceState === "error" ? (
                <>
                  <button
                    type="button"
                    onClick={handleStartSession}
                    className="px-4 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-medium transition-colors cursor-pointer flex items-center space-x-1.5 shadow-xs"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>Retry Voice</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleStopSession}
                    className="px-3 py-1.5 border border-[#E5E5E5] hover:bg-neutral-50 text-neutral-600 rounded-lg text-xs transition-colors cursor-pointer flex items-center space-x-1"
                  >
                    <Square className="w-3 h-3 fill-current" />
                    <span>Reset to Idle</span>
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={handleStartSession}
                  className="px-4 py-1.5 bg-[#111111] text-white rounded-lg text-xs font-medium hover:bg-neutral-800 transition-colors cursor-pointer flex items-center space-x-1.5 shadow-xs"
                >
                  <Mic className="w-3.5 h-3.5" />
                  <span>Start Voice Assistant</span>
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
                  setVoiceState("idle");
                  setStatusMessage("Conversation reset. Assistant ready. Click 'Start Voice Assistant' to begin.");
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
                  type="button"
                  onClick={() => setPdfUploadModalOpen(true)}
                  className="inline-flex items-center space-x-1.5 px-2.5 py-1 text-xs border border-neutral-900 bg-neutral-900 text-white hover:bg-black rounded-lg transition-colors cursor-pointer shadow-2xs"
                  title="Upload personal information PDF to auto-fill form"
                >
                  <Upload className="w-3 h-3 text-neutral-200" />
                  <span>Auto-Fill from PDF</span>
                </button>

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
              pdfFilledFields={pdfFilledFields}
              needsReviewFields={needsReviewFields}
              manuallyEditedFields={manuallyEditedFields}
              missingFields={missingFields}
              onFieldManualEdit={(fieldName) => {
                setManuallyEditedFields((prev) => Array.from(new Set([...prev, fieldName])));
              }}
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
                  setPdfFilledFields([]);
                  setNeedsReviewFields({});
                  setManuallyEditedFields([]);
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
                    pdfFilledFields,
                    needsReviewFields,
                    manuallyEditedFields,
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

      {/* PDF Upload & Extraction Modal */}
      <PdfUploadModal
        isOpen={pdfUploadModalOpen}
        onClose={() => setPdfUploadModalOpen(false)}
        formId={formId}
        formTitle={form?.title}
        onExtractionSuccess={handlePdfExtractionSuccess}
      />
    </div>
  );
}
