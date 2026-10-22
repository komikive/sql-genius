import { type MouseEvent, useCallback, useState } from 'react'
import {
  ArrowRight,
  Brain,
  Circuitry,
  Database,
  Sparkle,
  StackSimple,
} from '@phosphor-icons/react'
import { motion, useReducedMotion } from 'motion/react'
import { Link } from 'react-router-dom'

import FadeContent from '@/components/FadeContent'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

type PointerState = {
  x: number
  y: number
}

const navLinks = [
  { to: '/overview', label: '总览' },
  { to: '/workbench', label: '工作台' },
  { to: '/admin/datasources', label: '数据源' },
  { to: '/admin/skills', label: '技能' },
] as const

const routeLinks = [
  { to: '/admin/datasources', label: '数据源', icon: Database },
  { to: '/admin/skills', label: '技能', icon: Brain },
  { to: '/admin/memory', label: '记忆', icon: StackSimple },
  { to: '/admin/qa', label: '问答案例', icon: Sparkle },
] as const

const heroStats = [
  { label: 'Agent 工具', value: '7', caption: 'Schema / SQL / Memory / Skills' },
  { label: '已连接数据源', value: '3', caption: '零售、医疗、制造' },
  { label: '安全策略', value: 'SELECT', caption: '只读 SQL 执行护栏' },
] as const

const agentTrace = [
  { label: '召回记忆', value: '科室慢性病与异常检验口径', tone: 'blue' },
  { label: '激活技能', value: '临床就诊与诊断洞察', tone: 'indigo' },
  { label: '生成查询', value: '按科室和服务线统计慢病比例', tone: 'green' },
] as const

function SurfacePortal({
  to,
  label,
  icon: Icon,
}: {
  to: string
  label: string
  icon: typeof Database
}) {
  return (
    <Link
      to={to}
      className="group inline-flex cursor-pointer items-center gap-2 rounded-full border border-[var(--line)] bg-white/72 px-3 py-2 text-[12px] font-medium text-[var(--foreground-soft)] shadow-[0_8px_20px_rgba(17,24,39,0.04),inset_0_1px_0_rgba(255,255,255,0.58)] backdrop-blur-xl transition-[border-color,color,background-color,box-shadow] duration-200 ease-out hover:border-[var(--line-strong)] hover:bg-white/90 hover:text-[var(--foreground)] hover:shadow-[0_12px_28px_rgba(17,24,39,0.07),inset_0_1px_0_rgba(255,255,255,0.68)]"
    >
      <Icon className="size-3.5" />
      {label}
      <ArrowRight className="size-3 opacity-55 transition-transform duration-250 group-hover:translate-x-0.5" />
    </Link>
  )
}

export function LandingPage() {
  const reduceMotion = useReducedMotion()
  const [pointer, setPointer] = useState<PointerState>({ x: 54, y: 28 })

  const handleMove = useCallback((event: MouseEvent<HTMLElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    setPointer({
      x: ((event.clientX - rect.left) / rect.width) * 100,
      y: ((event.clientY - rect.top) / rect.height) * 100,
    })
  }, [])

  const spotlightPosition = reduceMotion
    ? { left: '58%', top: '24%' }
    : { left: `${pointer.x}%`, top: `${pointer.y}%` }

  return (
    <div
      className="relative min-h-[100dvh] overflow-hidden"
      onMouseMove={handleMove}
      onMouseLeave={() => setPointer({ x: 54, y: 28 })}
    >
      <div className="absolute inset-0 bg-[linear-gradient(180deg,#fbfaf6_0%,#f6f1e8_46%,#eee7da_100%)]" />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.10]"
        style={{
          backgroundImage:
            'linear-gradient(to right, rgba(20,24,33,0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(20,24,33,0.04) 1px, transparent 1px)',
          backgroundSize: '84px 84px',
          maskImage:
            'linear-gradient(180deg, rgba(0,0,0,0.20), rgba(0,0,0,0.07) 42%, transparent 86%)',
        }}
      />
      <motion.div
        aria-hidden
        className="pointer-events-none absolute h-[34rem] w-[34rem] rounded-full bg-[radial-gradient(circle,rgba(255,255,255,0.92)_0%,rgba(255,255,255,0.55)_20%,rgba(88,124,230,0.13)_46%,transparent_74%)] blur-[76px]"
        animate={spotlightPosition}
        transition={{
          type: reduceMotion ? 'tween' : 'spring',
          duration: reduceMotion ? 0.2 : undefined,
          stiffness: 70,
          damping: 18,
          mass: 0.9,
          ease: 'easeOut',
        }}
        style={{ translateX: '-50%', translateY: '-50%' }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'linear-gradient(180deg, rgba(255,255,255,0.56), transparent 28%), radial-gradient(circle at 15% 18%, rgba(255,255,255,0.72), transparent 20%), radial-gradient(circle at 80% 10%, rgba(36,88,211,0.07), transparent 18%), radial-gradient(circle at 76% 82%, rgba(101,168,255,0.08), transparent 20%)',
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-[52%] h-[24rem] w-[70rem] -translate-x-1/2 rounded-full bg-[radial-gradient(ellipse,rgba(20,24,33,0.08),transparent_68%)] blur-3xl"
      />

      <header className="relative z-10">
        <div className="mx-auto flex max-w-[1180px] items-center justify-between px-5 py-5 sm:px-6 lg:px-8">
          <Link
            to="/"
            className="inline-flex cursor-pointer items-center gap-3 rounded-full border border-white/70 bg-white/72 px-3.5 py-2 shadow-[0_14px_34px_rgba(17,24,39,0.06),inset_0_1px_0_rgba(255,255,255,0.72)] backdrop-blur-xl transition-opacity duration-200 hover:opacity-90"
          >
            <span className="flex size-8 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--primary)_10%,white)] text-[var(--primary)] shadow-[0_10px_24px_rgba(36,88,211,0.12)]">
              <Circuitry className="size-[18px]" weight="duotone" />
            </span>
            <span className="hidden whitespace-nowrap text-[13px] font-semibold tracking-[-0.02em] text-[var(--foreground)] sm:inline">
              SQL Genius
            </span>
          </Link>

          <div className="flex items-center gap-3">
            <nav className="hidden items-center gap-1 rounded-full border border-white/70 bg-white/70 p-1.5 shadow-[0_14px_30px_rgba(17,24,39,0.04),inset_0_1px_0_rgba(255,255,255,0.62)] backdrop-blur-xl lg:flex">
              {navLinks.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className="cursor-pointer rounded-full px-3 py-1.5 text-[12px] font-medium text-[var(--foreground-soft)] transition-colors duration-200 hover:bg-[color-mix(in_srgb,var(--foreground)_5%,transparent)] hover:text-[var(--foreground)]"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <Button asChild size="sm" className="h-10 cursor-pointer px-4 text-[12px] shadow-[0_16px_34px_rgba(36,88,211,0.22)]">
              <Link to="/workbench">
                打开系统
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="relative z-10 mx-auto flex min-h-[calc(100dvh-84px)] max-w-[1120px] items-start px-5 pb-14 pt-8 sm:px-6 sm:pt-12 lg:px-8 lg:pb-16 xl:items-center xl:pt-8">
        <section className="grid w-full gap-5 xl:grid-cols-[minmax(0,1.04fr)_minmax(360px,0.96fr)] xl:items-stretch">
          <FadeContent duration={480}>
            <section className="relative flex h-full min-h-[29rem] overflow-hidden rounded-[2.25rem] border border-white/72 bg-[linear-gradient(180deg,rgba(255,255,255,0.82),rgba(255,255,255,0.52))] p-7 shadow-[0_30px_82px_rgba(17,24,39,0.09),inset_0_1px_0_rgba(255,255,255,0.72)] backdrop-blur-2xl sm:p-9 lg:p-10">
              <div
                aria-hidden
                className="pointer-events-none absolute inset-px rounded-[calc(2.2rem-1px)]"
                style={{
                  background: reduceMotion
                    ? 'radial-gradient(circle at 56% 22%, rgba(255,255,255,0.42), transparent 42%)'
                    : `radial-gradient(circle at ${pointer.x}% ${pointer.y}%, rgba(255,255,255,0.48), transparent 34%)`,
                }}
              />
              <div
                aria-hidden
                className="absolute -bottom-28 -right-24 size-72 rounded-full bg-[radial-gradient(circle,rgba(36,88,211,0.12),transparent_64%)] blur-2xl"
              />
              <div className="relative z-10 flex h-full flex-col justify-between">
                <div>
                  <div className="inline-flex items-center gap-2 rounded-full border border-[var(--line)] bg-white/74 px-3 py-1.5 text-[11px] font-medium text-[var(--foreground-soft)] shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]">
                    <Sparkle className="size-3.5 text-[var(--primary)]" weight="duotone" />
                    面向企业数据理解的 Text-to-SQL Agent
                  </div>
                  <div className="mt-7 max-w-[40rem]">
                    <h1 className="text-[2.05rem] font-semibold leading-[1.05] tracking-[-0.058em] text-[var(--foreground)] sm:text-[2.45rem] lg:text-[2.8rem]">
                      统一连接、
                      <br />
                      理解并查询企业数据
                    </h1>
                    <p className="mt-5 max-w-[35rem] text-[14px] leading-7 text-[var(--foreground-soft)] sm:text-[15px] sm:leading-8">
                      SQL Genius 将数据源接入、结构理解、Agent 查询和知识沉淀收拢成一条连续工作流，让复杂数据库以更自然、可解释的方式被使用。
                    </p>
                  </div>

                  <div className="mt-8 flex flex-wrap items-center gap-3">
                    <Button asChild size="lg" className="h-12 cursor-pointer px-6 text-sm shadow-[0_20px_44px_rgba(36,88,211,0.24)]">
                      <Link to="/workbench">
                        进入工作台
                        <ArrowRight className="size-4" />
                      </Link>
                    </Button>
                    <Button asChild variant="outline" size="lg" className="h-12 cursor-pointer border-white/80 bg-white/66 px-6 text-sm backdrop-blur-xl">
                      <Link to="/overview">浏览系统</Link>
                    </Button>
                  </div>
                </div>

                <div className="mt-8 grid gap-3 sm:grid-cols-3">
                  {heroStats.map((item) => (
                    <div
                      key={item.label}
                      className="rounded-[1.35rem] border border-[var(--line)] bg-white/60 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.58)] backdrop-blur-xl"
                    >
                      <div className="text-[11px] font-medium text-[var(--muted-foreground)]">{item.label}</div>
                      <div className="mt-1 text-[22px] font-semibold tracking-[-0.04em] text-[var(--foreground)]">{item.value}</div>
                      <div className="mt-1 text-[10px] leading-4 text-[var(--muted-foreground)]">{item.caption}</div>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          </FadeContent>

          <FadeContent delay={90} duration={500}>
            <section className="relative flex h-full min-h-[29rem] overflow-hidden rounded-[2.25rem] border border-white/72 bg-[linear-gradient(180deg,rgba(255,255,255,0.78),rgba(255,255,255,0.48))] p-5 shadow-[0_30px_82px_rgba(17,24,39,0.09),inset_0_1px_0_rgba(255,255,255,0.70)] backdrop-blur-2xl sm:p-6">
              <div
                aria-hidden
                className="pointer-events-none absolute inset-px rounded-[calc(2.35rem-1px)]"
                style={{
                  background: reduceMotion
                    ? 'radial-gradient(circle at 68% 18%, rgba(92,124,220,0.12), transparent 42%)'
                    : `radial-gradient(circle at ${Math.min(pointer.x + 8, 88)}% ${Math.max(pointer.y - 8, 10)}%, rgba(92,124,220,0.13), transparent 34%)`,
                }}
              />
              <div
                aria-hidden
                className="absolute -right-16 -top-20 size-56 rounded-full bg-[radial-gradient(circle,rgba(36,88,211,0.12),transparent_68%)] blur-2xl"
              />

              <div className="relative z-10 flex h-full w-full flex-col">
                <div className="flex items-center justify-between gap-3 px-1">
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
                      Agent Run Preview
                    </div>
                    <div className="mt-1 text-[20px] font-semibold tracking-[-0.045em] text-[var(--foreground)]">
                      一次问题，贯穿理解、查询与学习
                    </div>
                  </div>
                  <Badge className="h-6 px-2 text-[10px]">Live Trace</Badge>
                </div>

                <div className="mt-5 rounded-[1.65rem] border border-[var(--line)] bg-[rgba(20,24,33,0.92)] p-4 text-white shadow-[0_20px_48px_rgba(17,24,39,0.14),inset_0_1px_0_rgba(255,255,255,0.12)]">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="size-2.5 rounded-full bg-[#ff6b5f]" />
                      <span className="size-2.5 rounded-full bg-[#f7c948]" />
                      <span className="size-2.5 rounded-full bg-[#57d18b]" />
                    </div>
                    <div className="rounded-full bg-white/10 px-2.5 py-1 text-[10px] text-white/68">
                      healthcare_claims.sql
                    </div>
                  </div>
                  <div className="mt-4 space-y-2 font-mono text-[11px] leading-5 text-white/78">
                    <div><span className="text-[#8db3ff]">WITH</span> chronic_encounters <span className="text-white/45">AS</span> (...)</div>
                    <div><span className="text-[#8db3ff]">SELECT</span> department_name, service_line, chronic_percentage</div>
                    <div><span className="text-[#8db3ff]">FROM</span> clinical_department_summary</div>
                    <div><span className="text-[#8db3ff]">ORDER BY</span> chronic_percentage <span className="text-[#9ee6b8]">DESC</span>;</div>
                  </div>
                </div>

                <div className="mt-4 space-y-2.5">
                  {agentTrace.map((item, index) => (
                    <FadeContent key={item.label} delay={140 + index * 70} duration={360}>
                      <div className="flex items-start gap-3 rounded-[1.35rem] border border-[var(--line)] bg-white/68 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.62)] backdrop-blur-xl">
                        <span
                          className={
                            item.tone === 'green'
                              ? 'mt-1 size-2.5 rounded-full bg-emerald-500 shadow-[0_0_0_4px_rgba(16,185,129,0.12)]'
                              : item.tone === 'indigo'
                                ? 'mt-1 size-2.5 rounded-full bg-indigo-500 shadow-[0_0_0_4px_rgba(99,102,241,0.12)]'
                                : 'mt-1 size-2.5 rounded-full bg-blue-500 shadow-[0_0_0_4px_rgba(59,130,246,0.12)]'
                          }
                        />
                        <div className="min-w-0">
                          <div className="text-[12px] font-semibold tracking-[-0.02em] text-[var(--foreground)]">{item.label}</div>
                          <div className="mt-0.5 truncate text-[11px] text-[var(--foreground-soft)]">{item.value}</div>
                        </div>
                      </div>
                    </FadeContent>
                  ))}
                </div>

                <div className="mt-auto rounded-[1.45rem] border border-[var(--line)] bg-white/60 px-4 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.58)] backdrop-blur-xl">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                        快速入口
                      </div>
                      <div className="mt-1 text-[12px] text-[var(--foreground-soft)]">
                        从查询工作台到数据资产治理，保持同一条工作流。
                      </div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {routeLinks.map((item) => (
                      <SurfacePortal
                        key={item.to}
                        to={item.to}
                        label={item.label}
                        icon={item.icon}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </section>
          </FadeContent>
        </section>
      </main>
    </div>
  )
}
