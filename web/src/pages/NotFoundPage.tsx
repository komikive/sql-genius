import { Link } from 'react-router-dom'

import FadeContent from '@/components/FadeContent'
import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <FadeContent duration={400}>
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
        <div className="text-[11px] font-medium tracking-[0.18em] text-[var(--muted-foreground)] uppercase">
          404
        </div>
        <h1 className="text-xl font-semibold tracking-[-0.03em] text-[var(--foreground)]">
          页面不存在
        </h1>
        <p className="max-w-[42ch] text-[13px] leading-6 text-[var(--foreground-soft)]">
          你访问的页面不在当前产品导航里。可以回到总览或直接进入工作台。
        </p>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to="/overview">返回总览</Link>
          </Button>
          <Button asChild size="sm">
            <Link to="/workbench">前往工作台</Link>
          </Button>
        </div>
      </div>
    </FadeContent>
  )
}
