import { ArrowsOut, Pause, Play, SpeakerHigh, SpeakerSlash } from "@phosphor-icons/react";
import { useEffect, useState, type PointerEvent, type RefObject } from "react";

import { formatClock } from "../lib/format";
import { t } from "../i18n/t";

/** Minimal controls over a <video>: scrubber, clock, mute and fullscreen. */
export function VideoControls({ videoRef, muted, onToggleMute }: { videoRef: RefObject<HTMLVideoElement | null>; muted: boolean; onToggleMute: () => void }) {
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [buffered, setBuffered] = useState(0);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const sync = () => {
      setPlaying(!video.paused && !video.ended);
      setTime(video.currentTime);
      setDuration(Number.isFinite(video.duration) ? video.duration : 0);
      try {
        setBuffered(video.buffered.length ? video.buffered.end(video.buffered.length - 1) : 0);
      } catch {
        setBuffered(0);
      }
    };
    sync();
    const events = ["play", "pause", "ended", "timeupdate", "durationchange", "loadedmetadata", "progress"];
    events.forEach((name) => video.addEventListener(name, sync));
    return () => events.forEach((name) => video.removeEventListener(name, sync));
  }, [videoRef]);

  function toggle() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) void video.play().catch(() => undefined);
    else video.pause();
  }

  function seekFrom(event: PointerEvent<HTMLDivElement>) {
    const video = videoRef.current;
    if (!video || !duration) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    video.currentTime = ratio * duration;
    setTime(video.currentTime);
  }

  function fullscreen() {
    const video = videoRef.current;
    const stage = video?.closest(".player-stage") ?? video;
    if (!stage) return;
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
    else void stage.requestFullscreen?.().catch(() => undefined);
  }

  const played = duration ? (time / duration) * 100 : 0;
  const loaded = duration ? (buffered / duration) * 100 : 0;
  return (
    <div className="vc" onClick={(event) => event.stopPropagation()}>
      <div
        className="vc-track"
        role="slider"
        aria-label={t("播放进度")}
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(time)}
        aria-valuetext={`${formatClock(time)} / ${formatClock(duration)}`}
        tabIndex={0}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          seekFrom(event);
        }}
        onPointerMove={(event) => event.buttons === 1 && seekFrom(event)}
        onKeyDown={(event) => {
          const video = videoRef.current;
          if (!video) return;
          if (event.key === "ArrowRight") video.currentTime = Math.min(duration, video.currentTime + 5);
          if (event.key === "ArrowLeft") video.currentTime = Math.max(0, video.currentTime - 5);
        }}
      >
        <span className="vc-buffered" style={{ width: `${loaded}%` }} />
        <span className="vc-played" style={{ width: `${played}%` }} />
        <span className="vc-knob" style={{ left: `${played}%` }} />
      </div>
      <div className="vc-row">
        <button type="button" className="icon-btn icon-btn-sm" aria-label={playing ? t("暂停") : t("播放")} onClick={toggle}>
          {playing ? <Pause size={18} weight="fill" /> : <Play size={18} weight="fill" />}
        </button>
        <span className="vc-clock num">
          {formatClock(time)} <span className="vc-sep">/</span> {formatClock(duration)}
        </span>
        <span className="toolbar-spacer" />
        <button type="button" className="icon-btn icon-btn-sm" aria-label={muted ? t("取消静音") : t("静音")} onClick={onToggleMute}>
          {muted ? <SpeakerSlash size={18} /> : <SpeakerHigh size={18} />}
        </button>
        <button type="button" className="icon-btn icon-btn-sm" aria-label={t("全屏")} onClick={fullscreen}>
          <ArrowsOut size={18} />
        </button>
      </div>
    </div>
  );
}
