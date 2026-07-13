import { spawn } from "node:child_process";
import readline from "node:readline";

class AppServerClient {
  constructor(executable) {
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Set();
    this.exitListeners = new Set();
    this.stderr = "";
    this.proc = spawn(executable, ["app-server", "--stdio"], {
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });
    this.proc.stderr.setEncoding("utf8");
    this.proc.stderr.on("data", (chunk) => {
      this.stderr = (this.stderr + chunk).slice(-8000);
    });
    this.lines = readline.createInterface({ input: this.proc.stdout, crlfDelay: Infinity });
    this.lines.on("line", (line) => this.handleLine(line));
    this.proc.on("error", (error) => this.fail(error));
    this.proc.on("exit", (code, signal) => {
      const error = new Error(
        `Codex app-server stopped before completing (code=${code}, signal=${signal}): ${this.stderr}`,
      );
      this.failAll(error);
      for (const listener of this.exitListeners) listener(error);
    });
  }

  write(message) {
    this.proc.stdin.write(`${JSON.stringify(message)}\n`);
  }

  request(method, params) {
    const id = this.nextId++;
    const response = new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
    this.write({ method, id, params });
    return response;
  }

  notify(method) {
    this.write({ method });
  }

  onNotification(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onExit(listener) {
    this.exitListeners.add(listener);
    return () => this.exitListeners.delete(listener);
  }

  handleLine(line) {
    let message;
    try {
      message = JSON.parse(line);
    } catch (error) {
      this.fail(new Error(`Invalid app-server JSON: ${line}`, { cause: error }));
      return;
    }
    if (message.id !== undefined && !message.method) {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      if (message.error) pending.reject(new Error(message.error.message || JSON.stringify(message.error)));
      else pending.resolve(message.result);
      return;
    }
    if (message.id !== undefined && message.method) {
      this.write({
        id: message.id,
        error: {
          code: -32601,
          message: `Interactive app-server request is unavailable in the Gmail bridge: ${message.method}`,
        },
      });
      return;
    }
    for (const listener of this.listeners) listener(message);
  }

  failAll(error) {
    for (const { reject } of this.pending.values()) reject(error);
    this.pending.clear();
  }

  fail(error) {
    this.failAll(error);
    for (const listener of this.exitListeners) listener(error);
    if (this.proc.exitCode === null) this.proc.kill();
  }

  async close() {
    this.proc.stdin.end();
    await new Promise((resolve) => {
      if (this.proc.exitCode !== null) resolve();
      else {
        const timer = setTimeout(() => {
          this.proc.kill();
          resolve();
        }, 2000);
        this.proc.once("exit", () => {
          clearTimeout(timer);
          resolve();
        });
      }
    });
  }
}

async function run(request) {
  const client = new AppServerClient(request.codexExecutable || "codex");
  try {
    await client.request("initialize", {
      clientInfo: { name: "gmail-codex-bridge", title: "Gmail Codex Bridge", version: "0.1.0" },
      capabilities: null,
    });
    client.notify("initialized");

    let threadId = request.threadId;
    if (threadId) {
      await client.request("thread/resume", {
        threadId,
        cwd: request.workingDirectory || null,
        excludeTurns: true,
      });
    } else {
      const started = await client.request("thread/start", {
        cwd: request.workingDirectory || null,
        approvalPolicy: "never",
        threadSource: "gmail-codex-bridge",
      });
      threadId = started.thread.id;
      const title = String(request.title || "Conversation Gmail").trim().slice(0, 120);
      await client.request("thread/name/set", { threadId, name: title || "Conversation Gmail" });
    }

    let latestAgentMessage = "";
    let finalResponse = "";
    let resolveCompleted;
    let rejectCompleted;
    const completed = new Promise((resolve, reject) => {
      resolveCompleted = resolve;
      rejectCompleted = reject;
    });
    const removeListener = client.onNotification((message) => {
      if (message.method === "item/completed" && message.params?.threadId === threadId) {
        const item = message.params.item;
        if (item?.type === "agentMessage") {
          latestAgentMessage = item.text;
          if (item.phase === "final_answer") finalResponse = item.text;
        }
      }
      if (message.method === "turn/completed" && message.params?.threadId === threadId) {
        const turn = message.params.turn;
        if (turn.status === "completed") resolveCompleted();
        else rejectCompleted(new Error(turn.error?.message || `Codex turn ended as ${turn.status}`));
      }
      if (message.method === "error") {
        rejectCompleted(
          new Error(message.params?.error?.message || message.params?.message || "Codex error"),
        );
      }
    });
    const removeExitListener = client.onExit(rejectCompleted);

    try {
      await client.request("turn/start", {
        threadId,
        input: [{ type: "text", text: request.prompt, text_elements: [] }],
        cwd: request.workingDirectory || null,
      });
      await completed;
    } finally {
      removeListener();
      removeExitListener();
    }
    const response = finalResponse || latestAgentMessage;
    if (!response) throw new Error("Codex app-server completed without an agent response");
    return { ok: true, finalResponse: response, threadId };
  } finally {
    await client.close();
  }
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of input) {
  try {
    const result = await run(JSON.parse(line));
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({ ok: false, error: String(error?.stack || error) })}\n`);
    process.exitCode = 1;
  }
}
