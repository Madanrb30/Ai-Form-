import React from "react";
import { Mic, MicOff, Square, Loader2, Sparkles, CheckCircle2, AlertTriangle } from "lucide-react";

export default function MicrophoneButton({
  state = "idle", // 'idle' | 'requesting' | 'listening' | 'transcribing' | 'processing' | 'filling' | 'waiting' | 'error' | 'completed'
  onClick,
  disabled = false,
  size = "lg", // 'md' | 'lg'
}) {
  const isListening = state === "listening";
  const isProcessing = ["transcribing", "processing", "filling"].includes(state);
  const isError = state === "error";
  const isCompleted = state === "completed";

  const sizeClasses =
    size === "lg"
      ? "w-20 h-20 text-2xl"
      : "w-14 h-14 text-xl";

  const iconSize = size === "lg" ? "w-8 h-8" : "w-6 h-6";

  // Color & shadow styles per state
  let buttonStyle = "bg-[#111111] text-white hover:bg-neutral-800 border-neutral-700 shadow-md";
  if (isListening) {
    buttonStyle = "bg-neutral-900 text-white border-neutral-900 shadow-xl ring-4 ring-neutral-400/40";
  } else if (isProcessing) {
    buttonStyle = "bg-neutral-900 text-white border-neutral-800 shadow-md";
  } else if (isError) {
    buttonStyle = "bg-red-600 text-white hover:bg-red-700 border-red-500 shadow-md";
  } else if (isCompleted) {
    buttonStyle = "bg-emerald-600 text-white hover:bg-emerald-700 border-emerald-500 shadow-md";
  }

  return (
    <div className="relative inline-flex items-center justify-center">
      {/* Outer pulsing ring when listening */}
      {isListening && (
        <>
          <span className="absolute -inset-3 rounded-full bg-neutral-900/10 animate-ping opacity-75 pointer-events-none" />
          <span className="absolute -inset-1.5 rounded-full bg-neutral-900/20 animate-pulse pointer-events-none" />
        </>
      )}

      {/* Processing spinner ring */}
      {isProcessing && (
        <span className="absolute -inset-1 rounded-full border-2 border-dashed border-neutral-900 animate-spin pointer-events-none" />
      )}

      <button
        type="button"
        disabled={disabled}
        onClick={onClick}
        aria-label={isListening ? "Stop listening" : "Start speaking"}
        className={`relative rounded-full flex items-center justify-center transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed select-none ${sizeClasses} ${buttonStyle}`}
      >
        {isListening ? (
          <Square className={`${iconSize} fill-current`} />
        ) : isProcessing ? (
          <Loader2 className={`${iconSize} animate-spin`} />
        ) : isCompleted ? (
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
