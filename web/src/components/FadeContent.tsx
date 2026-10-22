import {
  type HTMLAttributes,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from 'react'

type FadeContentProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode
  threshold?: number
  blur?: boolean
  duration?: number
  delay?: number
  initialOpacity?: number
  onComplete?: () => void
}

export default function FadeContent({
  children,
  threshold = 0.18,
  blur = false,
  duration = 720,
  delay = 0,
  initialOpacity = 0,
  onComplete,
  className = '',
  ...props
}: FadeContentProps) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return

        window.setTimeout(() => {
          setVisible(true)
          onComplete?.()
        }, delay)
        observer.disconnect()
      },
      { threshold },
    )

    observer.observe(node)
    return () => observer.disconnect()
  }, [delay, onComplete, threshold])

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: visible ? 1 : initialOpacity,
        transform: visible ? 'translate3d(0,0,0)' : 'translate3d(0,18px,0)',
        filter: blur && !visible ? 'blur(8px)' : 'blur(0px)',
        transition: `opacity ${duration}ms cubic-bezier(0.16,1,0.3,1), transform ${duration}ms cubic-bezier(0.16,1,0.3,1), filter ${duration}ms cubic-bezier(0.16,1,0.3,1)`,
        willChange: 'transform, opacity, filter',
      }}
      {...props}
    >
      {children}
    </div>
  )
}
