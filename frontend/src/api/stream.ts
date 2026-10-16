/** SSE streaming helper — consumes token stream from backend, calls onToken per chunk.
 *  Accepts an optional AbortSignal for cancellation. */

import config from "../config";
import { getAccessToken } from "./client";

export async function streamAI(
  endpoint: string,
  body: Record<string, any>,
  onToken: (token: string) => void,
  onDone: () => void,
  onError: (err: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const base = config.apiBaseUrl || "";
  const url = `${base}/api/v1${endpoint}`;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const accessToken = getAccessToken();
  if (accessToken && accessToken !== "guest") {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(body),
      signal,
    });

    if (!resp.ok) {
      onError(`请求失败 (${resp.status})`);
      return;
    }

    const reader = resp.body?.getReader();
    if (!reader) {
      onError("浏览器不支持流式读取");
      return;
    }

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;
        const data = trimmed.slice(6);
        if (data === "[DONE]") {
          onDone();
          return;
        }
        try {
          const parsed = JSON.parse(data);
          if (parsed.token) {
            onToken(parsed.token);
          }
        } catch {
          // skip unparseable chunks
        }
      }
    }

    onDone();
  } catch (err: any) {
    if (err.name === "AbortError") {
      // Request was intentionally cancelled — don't report as error
      return;
    }
    onError(err.message || "网络错误");
  }
}
