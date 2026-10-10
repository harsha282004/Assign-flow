import { useEffect, useRef, useState } from 'react'

/** One playback cycle lasts this long. A shorter (or equal) clip simply loops by itself. */
export const LOOP_SECONDS = 4
export const LOGIN_VIDEO_SRC = '/videos/student-login-background.mp4'

type FrameCallbackVideo = HTMLVideoElement & {
  requestVideoFrameCallback?: (cb: () => void) => number
  cancelVideoFrameCallback?: (handle: number) => void
}

/**
 * Background video of a login page (student by default; the teacher page passes its own clip, class prefix and no cycle).
 *
 * - The <video> stays mounted for the life of the page and its source is never reloaded; a loop is a seek to 0.
 * - Cycle rule (`cycleSeconds`, default LOOP_SECONDS; `null` = plain continuous looping): a clip of that length or
 *   less uses the native `loop`. A longer clip is restarted when playback reaches the cycle length, detected per video frame (requestVideoFrameCallback) with `timeupdate` as the fallback.
 *   One check function, one set of listeners, and a guard so a seek is never requested twice while one is pending.
 * - `ended` (a clip that really finishes) restarts the same way; play() promises are always handled.
 * - The gradient behind the video is the fallback: if the video errors or autoplay is refused the page stays
 *   fully usable, nothing reloads, no broken-media icon is shown. The video fades in on its first played frame, so
 *   there is never a black rectangle while it loads.
 * - Hover does nothing to playback. With reduced motion the video is not started (the first frame is shown).
 */
interface Props {
  src?: string
  /** CSS class prefix: `sl` (student, default) or `tl` (teacher). */
  classPrefix?: string
  /** Restart a longer clip every N seconds; `null` keeps the native continuous loop. */
  cycleSeconds?: number | null
}

export default function LoginVideo({
  src = LOGIN_VIDEO_SRC,
  classPrefix = 'sl',
  cycleSeconds = LOOP_SECONDS,
}: Props) {
  const ref = useRef<HTMLVideoElement>(null)
  const [state, setState] = useState<'loading' | 'playing' | 'failed'>('loading')
  // Reduced motion: the clip is not played at all (no autoplay, no loop); its first frame is shown still.
  const [reduceMotion] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )

  useEffect(() => {
    const video = ref.current as FrameCallbackVideo | null
    if (!video) return
    let disposed = false
    let seeking = false
    let frameHandle = 0

    const play = () => {
      if (disposed || reduceMotion || !video.paused) return
      // Autoplay can be refused by the browser; the gradient fallback stays visible and nothing else happens.
      video.play().catch(() => {})
    }

    const restart = () => {
      if (seeking) return // a seek is already pending: never stack seeks
      seeking = true
      video.currentTime = 0
    }

    const check = () => {
      if (disposed) return
      // Only a clip longer than one cycle needs the manual restart; a shorter one loops natively.
      if (
        cycleSeconds !== null &&
        video.duration > cycleSeconds + 0.05 &&
        video.currentTime >= cycleSeconds
      )
        restart()
    }

    const scheduleFrameCheck = () => {
      if (disposed || !video.requestVideoFrameCallback) return
      frameHandle = video.requestVideoFrameCallback(() => {
        check()
        scheduleFrameCheck()
      })
    }

    const onSeeked = () => {
      seeking = false
      play()
    }
    const onEnded = () => {
      restart()
      play()
    }
    const onPlaying = () => {
      setState('playing')
      if (frameHandle === 0) scheduleFrameCheck()
    }
    const onError = () => setState('failed')
    const onCanPlay = () => play()
    const onLoadedData = () => reduceMotion && setState('playing') // show the still first frame

    video.addEventListener('canplay', onCanPlay)
    video.addEventListener('loadeddata', onLoadedData)
    video.addEventListener('playing', onPlaying)
    video.addEventListener('timeupdate', check)
    video.addEventListener('seeked', onSeeked)
    video.addEventListener('ended', onEnded)
    video.addEventListener('error', onError)
    // The source <video> error does not bubble from <source>; listen on it as well.
    const source = video.querySelector('source')
    source?.addEventListener('error', onError)
    if (video.readyState >= 3) play()

    return () => {
      disposed = true
      video.removeEventListener('canplay', onCanPlay)
      video.removeEventListener('loadeddata', onLoadedData)
      video.removeEventListener('playing', onPlaying)
      video.removeEventListener('timeupdate', check)
      video.removeEventListener('seeked', onSeeked)
      video.removeEventListener('ended', onEnded)
      video.removeEventListener('error', onError)
      source?.removeEventListener('error', onError)
      if (frameHandle && video.cancelVideoFrameCallback) video.cancelVideoFrameCallback(frameHandle)
      video.pause()
    }
  }, [reduceMotion, cycleSeconds])

  return (
    <div className={`${classPrefix}-video ${classPrefix}-video-${state}`} aria-hidden="true">
      <video
        ref={ref}
        className={`${classPrefix}-video-el`}
        autoPlay={!reduceMotion}
        muted
        loop={!reduceMotion}
        playsInline
        preload="auto"
        disablePictureInPicture
        tabIndex={-1}
      >
        <source src={src} type="video/mp4" />
      </video>
      <div className={`${classPrefix}-video-tint`} />
    </div>
  )
}
