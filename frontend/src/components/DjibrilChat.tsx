import { useState, useRef, useEffect } from "react";
import type { ChatMessage, ChatResponse } from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

const SHORTCUTS = [
  { emoji: "📊", label: "Situation actuelle", message: "Quelle est la situation géopolitique actuelle ?" },
  { emoji: "📈", label: "Dernier signal", message: "Explique-moi le dernier signal" },
  { emoji: "🎯", label: "Performance", message: "Analyse ta performance récente" },
] as const;

interface DjibrilChatProps {
  isOpen: boolean;
  onClose: () => void;
  agentBrief?: string;
}

export default function DjibrilChat({ isOpen, onClose, agentBrief }: DjibrilChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  // Welcome message with brief
  useEffect(() => {
    if (isOpen && messages.length === 0) {
      const welcome = agentBrief
        ? `Bonjour. ${agentBrief}`
        : "Bonjour, je suis DJIBRIL. Posez-moi une question sur la situation géopolitique pétrolière ou sur mes signaux. — DJIBRIL";
      setMessages([{ role: "assistant", content: welcome, timestamp: new Date().toISOString() }]);
    }
  }, [isOpen, agentBrief, messages.length]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;

    const userMsg: ChatMessage = { role: "user", content: text.trim(), timestamp: new Date().toISOString() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (API_KEY) headers["X-API-Key"] = API_KEY;

      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({ message: text.trim(), include_signal_context: true }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: ChatResponse = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response, timestamp: data.timestamp },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "DJIBRIL est temporairement indisponible. Vérifiez la connexion au backend.",
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage(input);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-end p-4 sm:p-6 pointer-events-none">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/40 pointer-events-auto" onClick={onClose} />

      {/* Chat panel */}
      <div className="relative w-full max-w-md h-[600px] bg-dj-surface border border-dj-border rounded-xl shadow-2xl flex flex-col pointer-events-auto overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-dj-border bg-dj-bg/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-dj-blue/20 border border-dj-blue/30 flex items-center justify-center">
              <span className="text-dj-blue font-bold text-sm">D</span>
            </div>
            <div>
              <span className="text-sm font-bold text-dj-text-bright tracking-wide">DJIBRIL</span>
              <span className="block text-[10px] text-dj-text-muted">Agent IA géopolitique</span>
            </div>
          </div>
          <button onClick={onClose} className="text-dj-text-muted hover:text-dj-text-bright text-xl leading-none px-1 cursor-pointer">
            ✕
          </button>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              {msg.role === "assistant" && (
                <div className="w-6 h-6 rounded-full bg-dj-blue/20 border border-dj-blue/30 flex items-center justify-center mr-2 mt-1 shrink-0">
                  <span className="text-dj-blue text-[10px] font-bold">D</span>
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-[13px] leading-relaxed ${
                  msg.role === "user"
                    ? "bg-dj-accent/15 text-dj-text-bright border border-dj-accent/20"
                    : "bg-dj-bg border border-dj-border text-dj-text"
                }`}
              >
                {msg.content.split("\n").map((line, j) => (
                  <p key={j} className={j > 0 ? "mt-1.5" : ""}>{line}</p>
                ))}
              </div>
            </div>
          ))}

          {/* Typing indicator */}
          {isLoading && (
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full bg-dj-blue/20 border border-dj-blue/30 flex items-center justify-center shrink-0">
                <span className="text-dj-blue text-[10px] font-bold">D</span>
              </div>
              <div className="bg-dj-bg border border-dj-border rounded-lg px-3 py-2.5 flex items-center gap-1">
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-dot" />
              </div>
            </div>
          )}
        </div>

        {/* Shortcuts */}
        <div className="flex gap-1.5 px-4 py-2 border-t border-dj-border">
          {SHORTCUTS.map((sc) => (
            <button
              key={sc.label}
              onClick={() => void sendMessage(sc.message)}
              disabled={isLoading}
              className="text-[10px] font-medium px-2 py-1 rounded border border-dj-border text-dj-text-muted hover:border-dj-accent hover:text-dj-accent transition-colors cursor-pointer disabled:opacity-40"
            >
              {sc.emoji} {sc.label}
            </button>
          ))}
        </div>

        {/* Input */}
        <div className="flex gap-2 px-4 py-3 border-t border-dj-border bg-dj-bg/50">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Interrogez DJIBRIL..."
            disabled={isLoading}
            className="flex-1 bg-dj-bg border border-dj-border rounded-lg px-3 py-2 text-sm text-dj-text placeholder:text-dj-text-muted/50 outline-none focus:border-dj-accent/50 disabled:opacity-50"
          />
          <button
            onClick={() => void sendMessage(input)}
            disabled={isLoading || !input.trim()}
            className="bg-dj-accent/20 text-dj-accent border border-dj-accent/30 rounded-lg px-3 py-2 text-sm font-bold hover:bg-dj-accent/30 transition-colors cursor-pointer disabled:opacity-40"
          >
            ➤
          </button>
        </div>
      </div>
    </div>
  );
}
