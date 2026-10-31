import type { BrainDbHandle } from "../db/client.js";
import { parseNote } from "./parser.js";
import { chunkMarkdown } from "./chunker.js";
import type { Embedder } from "./embedder.js";
import { upsertNote, getNoteByPath, deleteNote, setNoteChecksum } from "../db/queries.js";
import { writeChunks } from "./writer.js";

const CHUNK_OPTS = { maxTokens: 800, overlapTokens: 100 };
/** Never equals a sha256 hex digest, so a half-written note is always retried. */
const PENDING_CHECKSUM = "pending";
/**
 * Folders whose contents are never indexed, matched on whole path segments.
 * The "Analysen" entries hold machine-generated reports that are rewritten
 * continuously; indexing them re-embeds the entire file on every write. Notes
 * written by hand elsewhere in "Analysen" stay indexed.
 */
const EXCLUDED_FOLDERS = new Set([
  "attachments",
  ".obsidian",
  ".trash",
  "Analysen/Link-Erkennung",
  "Analysen/Link-Erkennung-Shadow",
  "Analysen/LLM-Nutzung",
]);

function isExcluded(normalized: string): boolean {
  const segments = normalized.split("/");
  for (let i = 1; i < segments.length; i++) {
    if (EXCLUDED_FOLDERS.has(segments.slice(0, i).join("/"))) return true;
  }
  return false;
}
const MAX_FILE_SIZE = 2 * 1024 * 1024;

export type IndexResult = "indexed" | "skipped" | "unchanged" | "empty";

export async function indexFile(
  handle: BrainDbHandle,
  embed: Embedder,
  vaultRoot: string,
  relPath: string,
): Promise<IndexResult> {
  const normalized = relPath.split(/[\\/]/).filter((s) => s.length > 0).join("/");
  if (isExcluded(normalized)) return "skipped";
  if (!normalized.endsWith(".md")) return "skipped";

  const parsed = await parseNote(vaultRoot, normalized);
  if (parsed.sizeBytes > MAX_FILE_SIZE) return "skipped";

  const existing = await getNoteByPath(handle.db, parsed.path);
  if (existing && existing.checksum === parsed.checksum) return "unchanged";

  const chunks = chunkMarkdown(parsed.body, CHUNK_OPTS);
  const embeddings =
    chunks.length > 0 ? await embed.embedBatch(chunks.map((c) => c.content)) : [];

  // The checksum is stored only once the chunks are written. Storing it up
  // front made every failed write look "unchanged" to the next rescan, so the
  // note was never retried.
  const noteId = await upsertNote(handle.db, {
    path: parsed.path,
    folder: parsed.folder,
    title: parsed.title,
    frontmatter: parsed.frontmatter,
    mtime: parsed.mtime,
    sizeBytes: parsed.sizeBytes,
    checksum: PENDING_CHECKSUM,
  });
  await writeChunks(
    handle.sql,
    noteId,
    chunks.map((c, i) => ({ ...c, embedding: embeddings[i]! })),
  );
  await setNoteChecksum(handle.db, noteId, parsed.checksum);
  return chunks.length === 0 ? "empty" : "indexed";
}

export async function removeFile(handle: BrainDbHandle, relPath: string): Promise<void> {
  const normalized = relPath.split(/[\\/]/).filter((s) => s.length > 0).join("/");
  await deleteNote(handle.db, normalized);
}
