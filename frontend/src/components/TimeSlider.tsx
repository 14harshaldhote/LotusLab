import { localParts, type Timeline } from "../engine/timeline";

interface Props {
  timeline: Timeline;
  time: number;
  utcOffsetS: number;
  playing: boolean;
  speed: number;
  onSeek: (t: number) => void;
  onTogglePlay: () => void;
  onSpeed: (speed: number) => void;
}

const SPEEDS: Array<[number, string]> = [
  [600, "10 min/s"],
  [3600, "1 h/s"],
  [6 * 3600, "6 h/s"],
  [86400, "1 day/s"],
];

export function TimeSlider({ timeline, time, utcOffsetS, playing, speed, onSeek, onTogglePlay, onSpeed }: Props) {
  const p = localParts(time, utcOffsetS);
  const dayIndex = Math.floor((time - timeline.t0) / 86400);
  const jump = (target: number | null) => target != null && onSeek(target);
  return (
    <div className="time-slider">
      <div className="clock" aria-live="polite">
        <span className="clock-time">{p.time}</span>
        <span className="clock-date">
          {p.weekday} {p.date} · day {dayIndex}
        </span>
      </div>
      <input
        type="range"
        min={timeline.t0}
        max={timeline.tEnd}
        step={60}
        value={timeline.clamp(time)}
        onChange={(e) => onSeek(Number(e.currentTarget.value))}
        onKeyDown={(e) => {
          // Shift+arrows move a whole day, PageUp/PageDown six hours
          if (e.shiftKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
            e.preventDefault();
            onSeek(time + (e.key === "ArrowRight" ? 86400 : -86400));
          } else if (e.key === "PageUp" || e.key === "PageDown") {
            e.preventDefault();
            onSeek(time + (e.key === "PageUp" ? 6 : -6) * 3600);
          }
        }}
        aria-label="Simulation time"
      />
      <div className="transport">
        <button type="button" className="primary" onClick={onTogglePlay}>
          {playing ? "Pause" : "Play"}
        </button>
        <select value={speed} onChange={(e) => onSpeed(Number(e.currentTarget.value))} aria-label="Playback speed">
          {SPEEDS.map(([v, label]) => (
            <option key={v} value={v}>
              {label}
            </option>
          ))}
        </select>
        <button type="button" onClick={() => jump(timeline.nextEvent(time, "sunrise"))}>
          Next sunrise
        </button>
        <button type="button" onClick={() => jump(timeline.nextEvent(time, "sunset"))}>
          Next sunset
        </button>
        <button type="button" onClick={() => jump(timeline.nextRain(time))} disabled={timeline.nextRain(time) == null}>
          Next rain
        </button>
        <button type="button" onClick={() => onSeek(timeline.t0)}>
          Start
        </button>
        <button type="button" onClick={() => onSeek(timeline.tEnd)}>
          End
        </button>
      </div>
    </div>
  );
}
