// FastAPI /api/chat (Server-Sent Events) 클라이언트
import { postSSE } from "./sse";

export type Provider = "claude" | "gpt";
export type SearchMode = "빠르게" | "심층 검색";

export type ToolEvent = { name: string; label: string; input: Record<string, unknown> };
export type AnswerEvent = { text: string; provider: Provider; search_mode: SearchMode };

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  provider?: Provider;
  searchMode?: SearchMode;
  tools?: ToolEvent[];
};

export const PROVIDER_LABELS: Record<Provider, string> = {
  claude: "Claude Sonnet 5",
  gpt: "GPT-5.6 Terra",
};

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

type Handlers = {
  onTool: (e: ToolEvent) => void;
  onAnswer: (e: AnswerEvent) => void;
};

export async function streamChat(
  messages: ChatMessage[],
  provider: Provider,
  searchMode: SearchMode,
  handlers: Handlers,
  signal?: AbortSignal,
): Promise<void> {
  await postSSE(
    `${API_URL}/api/chat`,
    { messages: messages.map(({ role, content }) => ({ role, content })), provider, search_mode: searchMode },
    (event, payload) => {
      if (event === "tool") handlers.onTool(payload as ToolEvent);
      else if (event === "answer") handlers.onAnswer(payload as AnswerEvent);
    },
    signal,
  );
}
