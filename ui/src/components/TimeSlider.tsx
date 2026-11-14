import { Pause, Play } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import type { PublicEvent } from "@/lib/data";
import { snapToWeek } from "@/lib/series";

export const PLAY_INTERVAL_MS = 400;

interface TimeSliderProps {
  weeks: string[];
  index: number;
  onIndexChange: (index: number) => void;
  playing: boolean;
  onPlayingChange: (playing: boolean) => void;
  events: PublicEvent[];
}

export function TimeSlider({ weeks, index, onIndexChange, playing, onPlayingChange, events }: TimeSliderProps) {
  const last = weeks.length - 1;

  useEffect(() => {
    if (!playing) return undefined;
    if (index >= last) {
      onPlayingChange(false);
      return undefined;
    }
    const timer = window.setTimeout(() => onIndexChange(index + 1), PLAY_INTERVAL_MS);
    return () => window.clearTimeout(timer);
  }, [playing, index, last, onIndexChange, onPlayingChange]);

  const togglePlay = () => {
    if (!playing && index >= last) onIndexChange(0);
    onPlayingChange(!playing);
  };

  const markers = events
    .map((event) => ({ event, position: weeks.indexOf(snapToWeek(weeks, event.date) ?? "") }))
    .filter((marker) => marker.position >= 0);

  return (
    <div className="flex items-center gap-4">
      <Button variant="outline" size="icon" onClick={togglePlay} aria-label={playing ? "Pause" : "Play"}>
        {playing ? <Pause /> : <Play />}
      </Button>
      <div className="relative flex-1 pt-3">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-2" aria-hidden>
          {markers.map(({ event, position }) => (
            <span
              key={event.date}
              title={`${event.date}: ${event.label}`}
              className="absolute top-0 h-2 w-px bg-muted-foreground"
              style={{ left: `${last > 0 ? (position / last) * 100 : 0}%` }}
            />
          ))}
        </div>
        <Slider
          min={0}
          max={Math.max(last, 0)}
          step={1}
          value={[index]}
          onValueChange={([value]) => value !== undefined && onIndexChange(value)}
          thumbLabel="Week"
          aria-valuetext={weeks[index]}
        />
      </div>
      <output className="w-28 text-right font-mono text-sm tabular-nums" aria-live="polite">
        {weeks[index] ?? "no weeks"}
      </output>
    </div>
  );
}
