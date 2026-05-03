import { cn } from "@/lib/utils";

export type ChatRole = "user" | "orion" | "system";

export interface ToolChip {
  name: string;
  success: boolean;
}

export interface ChatMessageData {
  id: string;
  role: ChatRole;
  text: string;
  tools?: ToolChip[];
  isError?: boolean;
}

interface ChatMessageProps {
  msg: ChatMessageData;
}

export function ChatMessage({ msg }: ChatMessageProps) {
  if (msg.role === "system") {
    return (
      <div
        className={cn(
          "msg-in flex items-center gap-3 py-1",
          "font-mono text-[9px] tracking-[2px] uppercase",
          msg.isError ? "text-red" : "text-text-dim",
        )}
      >
        <span className="flex-1 h-px bg-border" />
        <span>{msg.text}</span>
        <span className="flex-1 h-px bg-border" />
      </div>
    );
  }

  const isUser = msg.role === "user";

  return (
    <div className={cn("msg-in flex gap-3.5", isUser && "flex-row-reverse")}>
      <Avatar isUser={isUser} />
      <div
        className={cn(
          "flex flex-col gap-1.5 max-w-[72%]",
          isUser ? "items-end" : "items-start",
        )}
      >
        <div
          className={cn(
            "font-orbitron text-[8px] tracking-[2.5px] uppercase",
            isUser ? "text-violet/60" : "text-cyan/45",
          )}
        >
          {isUser ? "VOUS" : "ORION"}
        </div>
        <div
          className={cn(
            "px-4 py-3 text-[13.5px] leading-snug whitespace-pre-wrap break-words",
            "backdrop-blur-panel",
            isUser
              ? "bg-violet/[0.07] border border-violet/20 border-r-[1.5px] border-r-violet text-text/90 text-right"
              : "bg-[rgba(5,12,28,0.7)] border border-border border-l-[1.5px] border-l-cyan text-text",
          )}
        >
          {msg.text || (
            <span className="text-text-dim italic">…</span>
          )}
          {msg.tools && msg.tools.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {msg.tools.map((t, i) => (
                <ToolBadge key={i} tool={t} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Avatar({ isUser }: { isUser: boolean }) {
  if (isUser) {
    return (
      <div className="w-[30px] h-[30px] rounded-sm flex items-center justify-center
                      mt-1 shrink-0 font-orbitron text-[9px] font-bold
                      bg-violet/10 border border-violet/30 text-violet">
        VOUS
      </div>
    );
  }
  return (
    <div className="w-[30px] h-[30px] rounded-sm shrink-0 mt-1
                    bg-cyan-dim border border-cyan/20
                    bg-[url('/assets/orion-mark.svg')] bg-no-repeat bg-center"
         style={{ backgroundSize: "22px 22px" }}
         aria-hidden="true" />
  );
}

function ToolBadge({ tool }: { tool: ToolChip }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm",
        "font-mono text-[9px] tracking-wide uppercase",
        tool.success
          ? "bg-green/[0.05] border border-green/25 text-green"
          : "bg-red/[0.05] border border-red/25 text-red",
      )}
    >
      <span
        className={cn(
          "w-1 h-1 rounded-full",
          tool.success ? "bg-green" : "bg-red",
        )}
      />
      {tool.name}
    </span>
  );
}
