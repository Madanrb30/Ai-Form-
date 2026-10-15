import React, { useRef, useEffect } from "react";
import { Sparkles, User, Terminal, ArrowRight, CornerDownLeft } from "lucide-react";

export default function VoiceTranscriptPanel({
  messages = [],
  interimTranscript = "",
  currentStatus = "idle",
  statusMessage = "",
  onSimulateVoice,
  simulatedText,
  setSimulatedText,
  disabled = false,
  samplePrompts = [],
}) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, interimTranscript]);

  const handleSimulateSubmit = (e) => {
    e.preventDefault();
    if (!simulatedText.trim() || disabled) return;
    onSimulateVoice(simulatedText.trim());
  };

  return (
    <div className="flex flex-col h-full bg-[#FFFFFF] border border-[#E5E5E5] rounded-xl overflow-hidden">
      {/* Panel Header */}
      <div className="px-4 py-3 bg-[#F7F7F7] border-b border-[#E5E5E5] flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Sparkles className="w-4 h-4 text-neutral-800" />
          <span className="text-xs font-semibold text-neutral-900 tracking-tight">
            Voice Conversation
          </span>
        </div>
        <span className="text-[10px] font-mono text-neutral-500 bg-white border border-neutral-200 px-2 py-0.5 rounded">
          {messages.length} exchanges
        </span>
      </div>

      {/* Messages Feed */}
      <div
        ref={scrollRef}
        className="flex-1 p-4 overflow-y-auto space-y-3 min-h-[220px] max-h-[360px] text-xs"
      >
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex items-start space-x-2.5 ${
              msg.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            {msg.role === "assistant" && (
              <div className="w-6 h-6 rounded-full bg-neutral-900 text-white flex items-center justify-center shrink-0 text-[10px] font-bold">
                AI
              </div>
            )}
            <div
              className={`max-w-[85%] px-3.5 py-2.5 rounded-xl text-left leading-relaxed break-words ${
                msg.role === "user"
                  ? "bg-[#111111] text-white rounded-br-xs"
                  : "bg-[#F7F7F7] text-neutral-900 border border-[#E5E5E5] rounded-bl-xs"
              }`}
            >
              <p>{msg.text}</p>
              {msg.meta && (
                <span className="block mt-1 text-[10px] text-neutral-400 font-mono">
                  {msg.meta}
                </span>
              )}
            </div>
            {msg.role === "user" && (
              <div className="w-6 h-6 rounded-full bg-neutral-200 text-neutral-800 flex items-center justify-center shrink-0 text-[10px] font-semibold">
                <User className="w-3.5 h-3.5" />
              </div>
            )}
          </div>
        ))}

        {/* Live Interim Transcript Bubble */}
        {interimTranscript && (
          <div className="flex items-start space-x-2.5 justify-end">
            <div className="max-w-[85%] px-3.5 py-2.5 rounded-xl bg-neutral-100 text-neutral-500 italic border border-dashed border-neutral-300">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-neutral-400 animate-ping mr-1.5" />
              {interimTranscript}
            </div>
          </div>
        )}
      </div>

      {/* Status Bar */}
      {statusMessage && (
        <div className="px-4 py-1.5 bg-[#F7F7F7] border-t border-[#E5E5E5] text-[11px] text-neutral-600 flex items-center justify-between">
          <span className="flex items-center space-x-1.5 truncate">
            <span className="w-1.5 h-1.5 rounded-full bg-neutral-900 shrink-0" />
            <span className="truncate">{statusMessage}</span>
          </span>
          <span className="font-mono text-[10px] text-neutral-400 uppercase shrink-0 ml-2">
            {currentStatus}
          </span>
        </div>
      )}

      {/* Quick speech sample chips */}
      {samplePrompts.length > 0 && (
        <div className="px-4 py-2 border-t border-[#E5E5E5] bg-white flex flex-wrap gap-1.5 items-center">
          <span className="text-[10px] font-mono text-neutral-400 mr-1">Quick Test:</span>
          {samplePrompts.slice(0, 2).map((prompt, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onSimulateVoice(prompt)}
              className="text-[11px] bg-neutral-100 hover:bg-neutral-200 text-neutral-700 px-2 py-0.5 rounded border border-neutral-200 transition-colors truncate max-w-[200px]"
            >
              &ldquo;{prompt}&rdquo;
            </button>
          ))}
        </div>
      )}

      {/* Manual Input Fallback */}
      <form
        onSubmit={handleSimulateSubmit}
        className="p-3 bg-white border-t border-[#E5E5E5] flex items-center space-x-2"
      >
        <div className="relative flex-1">
          <Terminal className="w-3.5 h-3.5 text-neutral-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={simulatedText}
            onChange={(e) => setSimulatedText(e.target.value)}
            disabled={disabled}
            placeholder="Type speech command or fallback text..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-[#F7F7F7] border border-[#E5E5E5] rounded-lg focus:bg-white focus:outline-none focus:border-neutral-900 transition-all disabled:opacity-50"
          />
        </div>
        <button
          type="submit"
          disabled={disabled || !simulatedText.trim()}
          className="px-3 py-1.5 bg-[#111111] text-white text-xs font-medium rounded-lg hover:bg-neutral-800 disabled:bg-neutral-200 disabled:text-neutral-400 transition-colors flex items-center space-x-1 shrink-0 cursor-pointer"
        >
          <span>Send</span>
          <CornerDownLeft className="w-3 h-3" />
        </button>
      </form>
    </div>
  );
}
