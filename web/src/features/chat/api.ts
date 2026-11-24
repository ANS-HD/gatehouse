import { ApiError } from "../../lib/api-client";
import { session } from "../../lib/session";

export type ChatTurn = { role: "user" | "assistant"; content: string };
export type ChatResult = { inputTokens: number; outputTokens: number; totalTokens: number; limited: boolean };

type Json = Record<string, unknown>;
const object = (value: unknown): Json => value && typeof value === "object" && !Array.isArray(value) ? value as Json : {};
const number = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : 0;

function errorMessage(value: unknown): string {
  const data = object(value);
  if (typeof data.detail === "string") return data.detail;
  const error = object(data.error);
  if (typeof error.message === "string") return error.message;
  return "模型请求失败，请稍后重试";
}

export async function sendChat(
  keyId: string,
  messages: ChatTurn[],
  maxOutputTokens: number,
  signal: AbortSignal,
  onText: (text: string) => void,
): Promise<ChatResult> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      Authorization: `Bearer ${session.get() ?? ""}`,
    },
    body: JSON.stringify({ key_id: keyId, messages, max_output_tokens: maxOutputTokens, stream: true }),
    signal,
  });
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    throw new ApiError(errorMessage(data), response.status);
  }
  const result: ChatResult = { inputTokens: 0, outputTokens: 0, totalTokens: 0, limited: false };
  const updateUsage = (value: unknown) => {
    const usage = object(value);
    result.inputTokens = Math.max(result.inputTokens, number(usage.prompt_tokens ?? usage.input_tokens));
    result.outputTokens = Math.max(result.outputTokens, number(usage.completion_tokens ?? usage.output_tokens));
    result.totalTokens = Math.max(result.totalTokens, number(usage.total_tokens), result.inputTokens + result.outputTokens);
  };
  if (response.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    const data = object(await response.json());
    if (data.error) throw new Error(errorMessage(data));
    const choice = object(Array.isArray(data.choices) ? data.choices[0] : null);
    const content = object(choice.message).content;
    if (typeof content === "string") onText(content);
    else if (Array.isArray(data.content)) {
      for (const block of data.content) {
        const text = object(block).text;
        if (typeof text === "string") onText(text);
      }
    }
    updateUsage(data.usage);
    result.limited = choice.finish_reason === "length" || data.stop_reason === "max_tokens";
    return result;
  }
  if (!response.body) throw new Error("浏览器未收到模型回复，请重试");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let dataLines: string[] = [];
  let complete = false;
  const event = () => {
    const raw = dataLines.join("\n").trim();
    dataLines = [];
    if (!raw) return;
    if (raw === "[DONE]") { complete = true; return; }
    let data: Json;
    try { data = object(JSON.parse(raw)); }
    catch { throw new Error("模型返回了无法解析的数据，请重试"); }
    if (data.error || data.type === "error") throw new Error(errorMessage(data));
    const choice = object(Array.isArray(data.choices) ? data.choices[0] : null);
    const delta = object(choice.delta);
    const content = delta.content ?? delta.refusal;
    if (typeof content === "string") onText(content);
    if (data.type === "content_block_delta") {
      const part = object(data.delta);
      if (part.type === "text_delta" && typeof part.text === "string") onText(part.text);
    }
    if (data.type === "content_block_start") {
      const block = object(data.content_block);
      if (block.type === "text" && typeof block.text === "string") onText(block.text);
    }
    updateUsage(data.usage);
    updateUsage(object(data.message).usage);
    const stop = object(data.delta).stop_reason;
    if (choice.finish_reason || data.type === "message_stop") complete = true;
    if (choice.finish_reason === "length" || stop === "max_tokens") result.limited = true;
  };
  const line = (value: string) => {
    const clean = value.replace(/\r$/, "");
    if (!clean) event();
    else if (clean.startsWith("data:")) dataLines.push(clean.slice(5).replace(/^ /, ""));
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      let newline: number;
      while ((newline = buffer.indexOf("\n")) !== -1) {
        line(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);
      }
      if (done) break;
    }
    if (buffer) line(buffer);
    event();
    if (!complete) throw new Error("连接提前结束，回复可能不完整，请重试");
    return result;
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
