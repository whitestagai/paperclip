import type postgres from "postgres";
import type { ChunkWithEmbedding } from "../shared/types.js";

type Sql = ReturnType<typeof postgres>;

function vectorLiteral(values: number[]): string {
  return `[${values.join(",")}]`;
}

export async function writeChunks(
  sql: Sql,
  noteId: string,
  chunks: Array<Omit<ChunkWithEmbedding, "noteId">>,
): Promise<void> {
  await sql.begin(async (tx) => {
    // The watcher and the hourly rescan can write the same note at once;
    // locking the note row makes the second writer wait instead of hitting
    // brain_chunks_note_chunk_unique.
    await tx.unsafe(`SELECT 1 FROM brain.notes WHERE id = $1 FOR UPDATE`, [noteId]);
    await tx.unsafe(`DELETE FROM brain.chunks WHERE note_id = $1`, [noteId]);
    for (const c of chunks) {
      await tx.unsafe(
        `INSERT INTO brain.chunks
           (note_id, chunk_index, heading_path, content, token_count, embedding, embedded_at)
         VALUES ($1, $2, $3, $4, $5, $6::vector, now())`,
        [noteId, c.chunkIndex, c.headingPath, c.content, c.tokenCount, vectorLiteral(c.embedding)],
      );
    }
  });
}

export async function countChunksForNote(sql: Sql, noteId: string): Promise<number> {
  const rows = await sql<Array<{ count: string }>>`
    SELECT count(*)::text AS count FROM brain.chunks WHERE note_id = ${noteId}
  `;
  return Number(rows[0]?.count ?? 0);
}
