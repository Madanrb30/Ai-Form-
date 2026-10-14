import React from "react";

export default function AudioWaveform({ isListening = false, count = 16, height = "h-8" }) {
  // Generate bar heights
  const bars = Array.from({ length: count }, (_, i) => i);

  return (
    <div className={`flex items-center justify-center space-x-1 ${height} px-4 py-1`}>
      {bars.map((idx) => {
        // Vary heights and animation classes
        const animClass = `animate-wave-${(idx % 5) + 1}`;
        return (
          <div
            key={idx}
            className={`w-1 rounded-full transition-all duration-200 ${
              isListening
                ? `bg-neutral-900 ${animClass}`
                : "bg-neutral-200 h-2"
            }`}
            style={{
              height: isListening ? `${Math.max(25, ((idx * 17) % 80) + 20)}%` : "4px",
              animationDelay: `${idx * 0.08}s`,
            }}
          />
        );
      })}
    </div>
  );
}
