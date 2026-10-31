import { describe, it, expect } from "vitest";
import { createSerialQueue } from "../src/indexer/serial-queue.js";

const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe("serial queue", () => {
  it("runs at most one job at a time", async () => {
    const queue = createSerialQueue();
    let running = 0;
    let peak = 0;
    const job = async () => {
      running++;
      peak = Math.max(peak, running);
      await pause(5);
      running--;
    };
    await Promise.all(Array.from({ length: 20 }, () => queue.push(job)));
    expect(peak).toBe(1);
  });

  it("keeps going after a job throws", async () => {
    const queue = createSerialQueue();
    const done: number[] = [];
    const failing = queue.push(async () => {
      throw new Error("embedding aborted");
    });
    const next = queue.push(async () => {
      done.push(2);
    });
    await expect(failing).rejects.toThrow("embedding aborted");
    await next;
    expect(done).toEqual([2]);
  });

  it("reports how many jobs are waiting", async () => {
    const queue = createSerialQueue();
    const first = queue.push(() => pause(10));
    queue.push(() => pause(1));
    expect(queue.size()).toBe(2);
    await first;
  });
});
