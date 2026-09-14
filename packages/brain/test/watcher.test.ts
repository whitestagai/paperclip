import { describe, it, expect } from "vitest";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { indexFile } from "../src/indexer/watcher.js";
import type { BrainDbHandle } from "../src/db/client.js";
import type { Embedder } from "../src/indexer/embedder.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.join(here, "fixtures/test-vault");

/** Throws if the indexer gets far enough to touch the database. */
const DB_TOUCHED = "db-touched";
const dbStub = new Proxy({} as BrainDbHandle, {
  get() {
    throw new Error(DB_TOUCHED);
  },
});

function embedderSpy(): Embedder & { calls: number } {
  const spy = {
    calls: 0,
    async embedBatch(inputs: string[]) {
      spy.calls++;
      return inputs.map(() => [0]);
    },
  };
  return spy;
}

/** Passing the exclusion check means execution reaches the database stub. */
async function expectNotSkipped(relPath: string) {
  const embed = embedderSpy();
  await expect(indexFile(dbStub, embed, vaultRoot, relPath)).rejects.toThrow(DB_TOUCHED);
}

async function expectSkippedWithoutEmbedding(relPath: string) {
  const embed = embedderSpy();
  const result = await indexFile(dbStub, embed, vaultRoot, relPath);
  expect(result).toBe("skipped");
  expect(embed.calls).toBe(0);
}

describe("indexFile path exclusions", () => {
  it("skips the link detector's shadow reports", async () => {
    await expectSkippedWithoutEmbedding("Analysen/Link-Erkennung-Shadow/2026-09-13.md");
  });

  it("skips the link detector's daily reports", async () => {
    await expectSkippedWithoutEmbedding("Analysen/Link-Erkennung/2026-09-13.md");
  });

  it("skips the LLM usage reports", async () => {
    await expectSkippedWithoutEmbedding("Analysen/LLM-Nutzung/2026-09-13.md");
  });

  it("indexes hand-written notes that sit next to the reports", async () => {
    await expectNotSkipped("Analysen/Meta-Tag Analyse.md");
  });

  it("indexes ordinary vault notes", async () => {
    await expectNotSkipped("AI/sample.md");
  });
});
