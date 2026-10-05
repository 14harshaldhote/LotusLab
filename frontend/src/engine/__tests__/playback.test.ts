import { describe, expect, it } from "vitest";

import { PlaybackClock } from "../playback";

describe("PlaybackClock", () => {
  it("derives time from the wall clock, independent of frame rate", () => {
    const run = (frameMs: number) => {
      const c = new PlaybackClock(0, 0, 1e9, 3600);
      c.play(0);
      let t = 0;
      for (let now = 0; now <= 10_000; now += frameMs) t = c.at(now);
      return [t, c.at(10_000)];
    };
    const [, at60fps] = run(16.67);
    const [, at7fps] = run(142);
    expect(at60fps).toBe(36_000);
    expect(at7fps).toBe(36_000);
  });

  it("pause, seek and speed change re-anchor without jumps", () => {
    const c = new PlaybackClock(100, 0, 1e6, 10);
    c.play(0);
    expect(c.at(1000)).toBe(110);
    c.pause(1000);
    expect(c.at(5000)).toBe(110);
    c.seek(500, 5000);
    c.play(5000);
    c.setSpeed(100, 6000);
    expect(c.at(6000)).toBe(510);
    expect(c.at(7000)).toBe(610);
  });

  it("clamps at the end and restarts on play", () => {
    const c = new PlaybackClock(0, 0, 100, 1000);
    c.play(0);
    expect(c.at(1000)).toBe(100);
    expect(c.ended(1000)).toBe(true);
    c.pause(1000);
    c.play(2000);
    expect(c.at(2000)).toBe(0);
  });
});
