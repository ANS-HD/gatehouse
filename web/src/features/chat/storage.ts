import { z } from "zod";

const messageSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  model: z.string().optional(),
  error: z.string().optional(),
  stopped: z.boolean().optional(),
  limited: z.boolean().optional(),
  totalTokens: z.number().optional(),
});
const chatSchema = z.object({
  keyId: z.string().optional(),
  maxOutputTokens: z.number().int().min(16).max(8192).default(2048),
  messages: z.array(messageSchema).max(201),
});

export type ChatMessage = z.infer<typeof messageSchema>;
export type SavedChat = z.infer<typeof chatSchema>;

export function readChat(userId: string): SavedChat {
  try {
    const saved = sessionStorage.getItem(`gatehouse_chat_${userId}`);
    if (saved) return chatSchema.parse(JSON.parse(saved));
  } catch { /* A corrupt or unavailable browser store should not block chatting. */ }
  return { messages: [], maxOutputTokens: 2048 };
}

export function saveChat(userId: string, chat: SavedChat) {
  try { sessionStorage.setItem(`gatehouse_chat_${userId}`, JSON.stringify(chat)); }
  catch { /* Chatting remains available if browser storage is full or disabled. */ }
}
