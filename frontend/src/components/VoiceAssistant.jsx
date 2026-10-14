import React, { useState, useEffect, useCallback } from "react";
import { useVoiceRecognition } from "../hooks/useVoiceRecognition";

export default function VoiceAssistant({ formId, schema, values, setValues, setErrors }) {
  const {
    isSupported,
    isListening,
    transcript,
    setTranscript,
    interimTranscript,
    error: voiceError,
    startListening,
    stopListening,
    resetTranscript,
  } = useVoiceRecognition();

  const [simulatedText, setSimulatedText] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [mappingResult, setMappingResult] = useState(null);
  const [mappingError, setMappingError] = useState(null);
  const [appliedCount, setAppliedCount] = useState(0);

  // Send transcript to backend voice mapping endpoint
  const analyzeTranscript = useCallback(async (textToProcess) => {
    const text = textToProcess || transcript;
    if (!text || !text.trim()) return;

    setAnalyzing(true);
    setMappingError(null);
    try {
      const res = await fetch(
        `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api"}/forms/${formId}/voice-map`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ transcript: text }),
        }
      ).then((r) => r.json());

      if (res && res.mapped_fields) {
        setMappingResult(res.mapped_fields);
      } else {
        setMappingResult({});
      }
    } catch (err) {
      setMappingError(`Could not map voice input: ${err.message}`);
    } finally {
      setAnalyzing(false);
    }
  }, [transcript, formId]);

  // When listening stops and we have a transcript, analyze automatically
  useEffect(() => {
    if (!isListening && transcript && transcript.trim()) {
      analyzeTranscript(transcript);
    }
  }, [isListening, transcript, analyzeTranscript]);

  // Apply proposed changes into form state
  const handleApplyAll = () => {
    if (!mappingResult) return;
    setValues((prev) => ({
      ...prev,
      ...mappingResult,
    }));
    // Clear any previous validation errors for mapped fields
    if (setErrors) {
      setErrors((prev) => {
        const next = { ...prev };
        Object.keys(mappingResult).forEach((k) => delete next[k]);
        return next;
      });
    }
    setAppliedCount(Object.keys(mappingResult).length);
    setMappingResult(null);
    resetTranscript();
    setSimulatedText("");
  };

  const handleApplySingle = (fieldKey, value) => {
    setValues((prev) => ({
      ...prev,
      [fieldKey]: value,
    }));
    if (setErrors) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[fieldKey];
        return next;
      });
    }
    setMappingResult((prev) => {
      const next = { ...prev };
      delete next[fieldKey];
      return Object.keys(next).length > 0 ? next : null;
    });
  };

  // Sample prompt helper based on schema
  const generateSpokenSample = () => {
    if (!schema?.fields) return "";
    const samples = schema.fields.slice(0, 3).map((f) => {
      if (f.name.includes("name")) return `my name is Alex`;
      if (f.name.includes("email")) return `email alex@test.com`;
      if (f.name.includes("phone")) return `phone 555-0199`;
      if (f.name.includes("department")) return `department ${f.options?.[0] || "AI"}`;
      return `${f.label.toLowerCase()} is sample`;
    });
    return samples.join(" and ");
  };

  return (
    <div className="bg-white border border-zinc-200 p-5 text-left transition-all">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-zinc-100">
        <div className="flex items-center space-x-3">
          <div
            className={`w-3 h-3 rounded-full ${
              isListening ? "bg-red-500 animate-ping" : "bg-zinc-400"
            }`}
          />
          <div>
            <h3 className="font-semibold text-sm text-black tracking-tight flex items-center gap-2">
              Voice Assistant
              {isListening && (
                <span className="text-[10px] font-mono bg-red-100 text-red-700 px-1.5 py-0.5 rounded">
                  LISTENING
                </span>
              )}
            </h3>
            <p className="text-xs text-zinc-500">
              Speak naturally to fill form fields (e.g. &ldquo;My name is Madan and email is madan@test.com&rdquo;)
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-2">
          {isSupported ? (
            !isListening ? (
              <button
                type="button"
                onClick={startListening}
                className="px-4 py-1.5 bg-black text-white text-xs font-medium hover:bg-zinc-800 transition-colors flex items-center gap-1.5"
              >
                <span>🎙️</span> Start Speaking
              </button>
            ) : (
              <button
                type="button"
                onClick={stopListening}
                className="px-4 py-1.5 bg-red-600 text-white text-xs font-medium hover:bg-red-700 transition-colors flex items-center gap-1.5"
              >
                <span>⏹️</span> Stop & Map
              </button>
            )
          ) : (
            <span className="text-xs font-mono text-zinc-400 border border-zinc-200 px-2 py-1 bg-zinc-50">
              Web Speech API not detected in this browser
            </span>
          )}

          {(transcript || mappingResult) && (
            <button
              type="button"
              onClick={() => {
                resetTranscript();
                setMappingResult(null);
                setSimulatedText("");
              }}
              className="text-xs text-zinc-500 hover:text-black px-2 py-1"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Voice Recognition Error */}
      {voiceError && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 text-xs text-red-700">
          {voiceError}
        </div>
      )}

      {/* Live Transcript Display */}
      {(transcript || interimTranscript) && (
        <div className="mt-3 p-3 bg-zinc-50 border border-zinc-200 text-xs font-mono">
          <span className="text-zinc-400 block text-[10px] uppercase tracking-wider mb-1">
            Recognized Speech:
          </span>
          <span className="text-black">{transcript}</span>
          {interimTranscript && (
            <span className="text-zinc-400 italic"> {interimTranscript}</span>
          )}
        </div>
      )}

      {/* Testing & Fallback Input (useful for headless / unsupported environments) */}
      <div className="mt-4 pt-3 border-t border-zinc-100 flex flex-col sm:flex-row gap-2 items-stretch sm:items-center">
        <input
          type="text"
          value={simulatedText}
          onChange={(e) => setSimulatedText(e.target.value)}
          placeholder={`Or test voice text: "${generateSpokenSample()}"`}
          className="flex-1 px-3 py-1.5 text-xs border border-zinc-300 focus:outline-none focus:border-black"
        />
        <button
          type="button"
          disabled={analyzing || !simulatedText.trim()}
          onClick={() => {
            setTranscript(simulatedText);
            analyzeTranscript(simulatedText);
          }}
          className="px-3 py-1.5 bg-zinc-900 text-white text-xs hover:bg-black disabled:bg-zinc-200 disabled:text-zinc-400 transition-colors shrink-0"
        >
          {analyzing ? "Mapping..." : "Map Spoken Text"}
        </button>
      </div>

      {/* Mapping Error */}
      {mappingError && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 text-xs text-red-700">
          {mappingError}
        </div>
      )}

      {/* Proposed Field Changes Card */}
      {mappingResult && Object.keys(mappingResult).length > 0 && (
        <div className="mt-4 p-4 border border-zinc-900 bg-zinc-50">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-200">
            <div>
              <span className="text-xs font-semibold text-black uppercase tracking-wider">
                Proposed Field Updates ({Object.keys(mappingResult).length})
              </span>
              <p className="text-[11px] text-zinc-500">
                Review recognized field values before applying:
              </p>
            </div>
            <button
              type="button"
              onClick={handleApplyAll}
              className="px-3 py-1.5 bg-black text-white text-xs font-medium hover:bg-zinc-800 transition-colors"
            >
              Apply All to Form
            </button>
          </div>

          <div className="mt-3 space-y-2">
            {Object.entries(mappingResult).map(([fieldKey, propVal]) => {
              const fieldDef = schema?.fields?.find((f) => f.name === fieldKey);
              const label = fieldDef?.label || fieldKey;
              const currentVal = values[fieldKey];

              return (
                <div
                  key={fieldKey}
                  className="flex items-center justify-between bg-white p-2.5 border border-zinc-200 text-xs"
                >
                  <div className="flex-1 pr-3">
                    <span className="font-semibold text-zinc-800">{label}:</span>
                    <span className="ml-2 font-mono text-emerald-700 font-medium">
                      &quot;{String(propVal)}&quot;
                    </span>
                    {currentVal && currentVal !== propVal && (
                      <span className="ml-2 text-zinc-400 line-through">
                        &quot;{String(currentVal)}&quot;
                      </span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleApplySingle(fieldKey, propVal)}
                    className="text-xs text-black underline hover:no-underline font-medium px-2"
                  >
                    Apply
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* No fields matched notice */}
      {mappingResult && Object.keys(mappingResult).length === 0 && (
        <div className="mt-3 p-3 bg-amber-50 border border-amber-200 text-xs text-amber-800">
          No form fields could be recognized from that phrase. Try saying: &ldquo;My {schema?.fields?.[0]?.label || "field"} is ...&rdquo;
        </div>
      )}

      {/* Applied notice */}
      {appliedCount > 0 && !mappingResult && (
        <div className="mt-3 text-xs text-emerald-700 font-medium flex items-center gap-1">
          <span>✓</span> Successfully populated {appliedCount} form {appliedCount === 1 ? "field" : "fields"} from voice!
        </div>
      )}
    </div>
  );
}
