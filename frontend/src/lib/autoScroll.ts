import { type RefObject, useCallback, useLayoutEffect, useRef } from 'react'

const NEAR_BOTTOM_PX = 80

interface ScrollPosition {
  scrollTop: number
  scrollHeight: number
  clientHeight: number
}

/** Whether the view is at (or close to) the bottom, so new content should keep it there. */
export function isNearBottom(
  { scrollTop, scrollHeight, clientHeight }: ScrollPosition,
  threshold = NEAR_BOTTOM_PX,
): boolean {
  return scrollHeight - scrollTop - clientHeight <= threshold
}

/** Keeps a scroll container pinned to the bottom as `content` changes, unless the user has
 * scrolled up to read. `stickToBottom()` re-pins it, for example when a new question is sent. */
export function useAutoScroll(ref: RefObject<HTMLElement | null>, content: unknown) {
  const stuck = useRef(true)

  const onScroll = useCallback(() => {
    if (ref.current) stuck.current = isNearBottom(ref.current)
  }, [ref])

  const stickToBottom = useCallback(() => {
    stuck.current = true
  }, [])

  useLayoutEffect(() => {
    const element = ref.current
    if (element && stuck.current) element.scrollTop = element.scrollHeight
  }, [ref, content])

  return { onScroll, stickToBottom }
}
