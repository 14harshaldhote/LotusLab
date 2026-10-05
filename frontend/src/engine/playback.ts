/**
 * Deterministic playback clock.
 *
 * Simulation time is a pure function of wall-clock time since the last anchor:
 *   sim(now) = anchorSim + (now - anchorWall) * speed
 * Frame rate, dropped frames or tab throttling change how often we *look*, never
 * where the simulation *is*. Pausing, seeking or changing speed re-anchors.
 */
export class PlaybackClock {
  private anchorWall = 0;
  private anchorSim: number;
  private _playing = false;

  constructor(
    start: number,
    private readonly tMin: number,
    private readonly tMax: number,
    private _speed = 3600, // simulated seconds per real second
  ) {
    this.anchorSim = start;
  }

  get playing(): boolean {
    return this._playing;
  }

  get speed(): number {
    return this._speed;
  }

  at(nowMs: number): number {
    if (!this._playing) return this.anchorSim;
    const t = this.anchorSim + ((nowMs - this.anchorWall) / 1000) * this._speed;
    return Math.min(Math.max(t, this.tMin), this.tMax);
  }

  ended(nowMs: number): boolean {
    return this.at(nowMs) >= this.tMax;
  }

  play(nowMs: number): void {
    if (this._playing) return;
    if (this.anchorSim >= this.tMax) this.anchorSim = this.tMin; // replay from start
    this.anchorWall = nowMs;
    this._playing = true;
  }

  pause(nowMs: number): void {
    this.anchorSim = this.at(nowMs);
    this._playing = false;
  }

  seek(t: number, nowMs: number): void {
    this.anchorSim = Math.min(Math.max(t, this.tMin), this.tMax);
    this.anchorWall = nowMs;
  }

  setSpeed(speed: number, nowMs: number): void {
    this.anchorSim = this.at(nowMs);
    this.anchorWall = nowMs;
    this._speed = speed;
  }
}
