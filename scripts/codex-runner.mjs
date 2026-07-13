import readline from "node:readline";
import { Codex } from "@openai/codex-sdk";

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
  try {
    const request = JSON.parse(line);
    const codex = new Codex();
    const options = request.workingDirectory
      ? { workingDirectory: request.workingDirectory }
      : undefined;
    const thread = request.threadId
      ? codex.resumeThread(request.threadId, options)
      : codex.startThread(options);
    const result = await thread.run(request.prompt);
    process.stdout.write(
      JSON.stringify({ ok: true, finalResponse: result.finalResponse, threadId: thread.id }) + "\n",
    );
  } catch (error) {
    process.stdout.write(JSON.stringify({ ok: false, error: String(error?.stack || error) }) + "\n");
    process.exitCode = 1;
  }
}
