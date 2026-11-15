/** Playback speeds the player cycles through, in the order Douyin users expect. */
export const SPEEDS = [1, 1.25, 1.5, 2, 0.75] as const;
const KEY = "douzangjia.speed.v1";

/** The speed the owner last picked; survives reloads, falls back to normal speed. */
export function readSpeed(): number {
  try {
    const value = Number(window.localStorage.getItem(KEY));
    return (SPEEDS as readonly number[]).includes(value) ? value : 1;
  } catch {
    return 1;
  }
}

export function writeSpeed(speed: number): void {
  try {
    if (speed === 1) window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, String(speed));
  } catch {
    // Private mode or blocked storage: the choice just lasts for this video.
  }
}

export function nextSpeed(speed: number): number {
  const index = (SPEEDS as readonly number[]).indexOf(speed);
  return SPEEDS[(index + 1) % SPEEDS.length];
}

export function speedLabel(speed: number): string {
  return `${speed}×`;
}
