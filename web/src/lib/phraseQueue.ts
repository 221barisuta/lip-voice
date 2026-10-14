import type { Phrase } from "../types/phrase";

/** 全フレーズをシャッフルして順に出す。一巡したら再シャッフル（境界で同じ語が続かないようにする）。 */
export class PhraseQueue {
  private queue: Phrase[] = [];
  private last: string | null = null;
  constructor(private phrases: Phrase[]) {}

  next(): Phrase {
    if (!this.queue.length) {
      this.queue = shuffle(this.phrases);
      if (this.queue.length > 1 && this.queue[0].id === this.last) {
        this.queue.push(this.queue.shift()!);
      }
    }
    const p = this.queue.shift()!;
    this.last = p.id;
    return p;
  }
}

function shuffle<T>(a: T[]): T[] {
  const r = [...a];
  for (let i = r.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [r[i], r[j]] = [r[j], r[i]];
  }
  return r;
}
