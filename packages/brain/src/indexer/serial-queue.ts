/**
 * Runs jobs strictly one after another. The watcher fires one event per file;
 * a bulk import (e.g. 30,000 mails from a PST archive) otherwise starts that
 * many embedding requests at once, LM Studio times out and every one fails.
 */
export interface SerialQueue {
  push<T>(job: () => Promise<T>): Promise<T>;
  /** Jobs waiting or running. */
  size(): number;
}

export function createSerialQueue(): SerialQueue {
  let tail: Promise<unknown> = Promise.resolve();
  let count = 0;
  return {
    push<T>(job: () => Promise<T>): Promise<T> {
      count++;
      const run = tail.then(job).finally(() => {
        count--;
      });
      // A failed job must not stop the jobs queued behind it.
      tail = run.catch(() => undefined);
      return run;
    },
    size: () => count,
  };
}
