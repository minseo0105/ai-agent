// FastAPI /api/chat (Server-Sent Events) 클라이언트

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

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

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
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages: messages.map(({ role, content }) => ({ role, content })),
      provider,
      search_mode: searchMode,
    }),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`서버 응답 오류 (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);

      let event = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;

      const payload = JSON.parse(data);
      if (event === "tool") handlers.onTool(payload as ToolEvent);
      else if (event === "answer") handlers.onAnswer(payload as AnswerEvent);
    }
  }
}
