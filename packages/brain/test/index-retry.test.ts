import { describe, it, expect, beforeAll, afterAll, beforeEach } from "vitest";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createBrainDb, type BrainDbHandle } from "../src/db/client.js";
import { indexFile } from "../src/indexer/watcher.js";
import { countChunksForNote, writeChunks } from "../src/indexer/writer.js";
import { getNoteByPath, upsertNote } from "../src/db/queries.js";
import type { Embedder } from "../src/indexer/embedder.js";

const DATABASE_URL = process.env.BRAIN_DATABASE_URL;
if (!DATABASE_URL) throw new Error("BRAIN_DATABASE_URL must be set");

const here = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.join(here, "fixtures/test-vault");
const NOTE = "test-retry/retry.md";

const workingEmbedder: Embedder = {
  async embedBatch(inputs) {
    return inputs.map(() => Array(1024).fill(0.01));
  },
};
const failingEmbedder: Embedder = {
  async embedBatch() {
    throw new Error("lm studio down");
  },
};

let handle: BrainDbHandle;

describe("indexFile after a failed attempt", () => {
  beforeAll(() => {
    handle = createBrainDb(DATABASE_URL);
  });
  beforeEach(async () => {
    await handle.sql`DELETE FROM brain.notes WHERE path LIKE 'test-retry/%'`;
  });
  afterAll(async () => {
    await handle.sql`DELETE FROM brain.notes WHERE path LIKE 'test-retry/%'`;
    await handle.close();
  });

  it("indexes the note on the next run instead of reporting it unchanged", async () => {
    await expect(indexFile(handle, failingEmbedder, vaultRoot, NOTE)).rejects.toThrow();

    const result = await indexFile(handle, workingEmbedder, vaultRoot, NOTE);
    expect(result).toBe("indexed");
    const note = await getNoteByPath(handle.db, NOTE);
    expect(await countChunksForNote(handle.sql, note!.id)).toBeGreaterThan(0);
  });

  it("serialises concurrent chunk writes for the same note", async () => {
    const noteId = await upsertNote(handle.db, {
      path: "test-retry/concurrent.md",
      folder: "test-retry",
      title: "C",
      frontmatter: {},
      mtime: new Date(),
      sizeBytes: 1,
      checksum: "c",
    });
    const chunks = [0, 1, 2].map((i) => ({
      chunkIndex: i,
      headingPath: ["C"],
      content: `chunk ${i}`,
      tokenCount: 2,
      embedding: Array(1024).fill(0.01),
    }));

    await Promise.all([
      writeChunks(handle.sql, noteId, chunks),
      writeChunks(handle.sql, noteId, chunks),
      writeChunks(handle.sql, noteId, chunks),
    ]);
    expect(await countChunksForNote(handle.sql, noteId)).toBe(3);
  });
});
