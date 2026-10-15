import React from "react";
import { Mic, Square, Loader2, Volume2, AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";

export default function MicrophoneButton({
  state = "idle", // 'idle' | 'initializing' | 'listening' | 'recording' | 'transcribing' | 'processing' | 'speaking' | 'confirmation' | 'error' | 'stopped'
  onClick,
  disabled = false,
  size = "lg", // 'md' | 'lg'
}) {
  const isListening = state === "listening";
  const isRecording = state === "recording";
  const isProcessing = ["initializing", "transcribing", "processing"].includes(state);
  const isSpeaking = state === "speaking";
  const isConfirmation = state === "confirmation";
  const isError = state === "error";

  const sizeClasses =
    size === "lg"
      ? "w-20 h-20 text-2xl"
      : "w-14 h-14 text-xl";

  const iconSize = size === "lg" ? "w-8 h-8" : "w-6 h-6";

  // Black-and-white aesthetic with crisp status borders
  let buttonStyle = "bg-neutral-900 text-white hover:bg-neutral-800 border-neutral-700 shadow-md";
  if (isRecording) {
    buttonStyle = "bg-black text-white border-neutral-900 shadow-xl ring-4 ring-neutral-400/50";
  } else if (isListening) {
    buttonStyle = "bg-neutral-900 text-white border-neutral-700 shadow-lg ring-2 ring-neutral-500/30";
  } else if (isProcessing) {
    buttonStyle = "bg-neutral-900 text-white border-neutral-800 shadow-md";
  } else if (isSpeaking) {
    buttonStyle = "bg-black text-white border-neutral-600 shadow-lg ring-4 ring-neutral-300/40";
  } else if (isConfirmation) {
    buttonStyle = "bg-black text-white border-neutral-500 shadow-xl ring-4 ring-neutral-400/60";
  } else if (isError) {
    buttonStyle = "bg-neutral-900 text-neutral-300 border-neutral-700 shadow-md";
  }

  return (
    <div className="relative inline-flex items-center justify-center">
      {/* Outer pulsing ring when recording voice activity */}
      {isRecording && (
        <>
          <span className="absolute -inset-3 rounded-full bg-neutral-900/15 animate-ping opacity-75 pointer-events-none" />
          <span className="absolute -inset-1.5 rounded-full bg-neutral-900/25 animate-pulse pointer-events-none" />
        </>
      )}

      {/* Gentle listening indicator */}
      {isListening && (
        <span className="absolute -inset-1.5 rounded-full border border-neutral-400/40 animate-pulse pointer-events-none" />
      )}

      {/* Speaking wave effect */}
      {isSpeaking && (
        <span className="absolute -inset-2 rounded-full border-2 border-neutral-400/40 animate-pulse pointer-events-none" />
      )}

      {/* Confirmation highlight ring */}
      {isConfirmation && (
        <span className="absolute -inset-2.5 rounded-full border-2 border-dashed border-neutral-600 animate-spin pointer-events-none" />
      )}

      {/* Processing spinner ring */}
      {isProcessing && (
        <span className="absolute -inset-1.5 rounded-full border-2 border-dashed border-neutral-700 animate-spin pointer-events-none" />
      )}

      <button
        type="button"
        disabled={disabled}
        onClick={onClick}
        aria-label={
          isRecording || isListening
            ? "Stop listening"
            : isSpeaking
            ? "Interrupt assistant"
            : isConfirmation
            ? "Confirm or speak answer"
            : isProcessing
            ? "Processing"
            : "Start voice assistant"
        }
        className={`relative rounded-full flex items-center justify-center transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed select-none focus:outline-none focus:ring-4 focus:ring-neutral-400/50 ${sizeClasses} ${buttonStyle}`}
      >
        {isRecording ? (
          <Square className={`${iconSize} fill-current`} />
        ) : isListening ? (
          <Mic className={`${iconSize} animate-pulse`} />
        ) : isProcessing ? (
          <Loader2 className={`${iconSize} animate-spin`} />
        ) : isSpeaking ? (
          <Volume2 className={`${iconSize} animate-pulse`} />
        ) : isConfirmation ? (
          <CheckCircle2 className={iconSize} />
        ) : isError ? (
          <AlertTriangle className={iconSize} />
        ) : (
          <Mic className={iconSize} />
        )}
      </button>
    </div>
  );
}
