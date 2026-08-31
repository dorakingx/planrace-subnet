import {
  ArrowUpRight,
  Check,
  CircleDot,
  Clock3,
  Code2,
  DatabaseZap,
  GitBranch,
  ShieldCheck,
  X,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader } from '@/components/ui/card';

const miners = [
  {
    rank: '01',
    name: 'Bob / indexed',
    uid: 'UID 1',
    result: 'EXACT MATCH',
    score: '9.084',
    weight: '100%',
    status: 'accepted',
  },
  {
    rank: '02',
    name: 'Charlie / widen-filter',
    uid: 'UID 2',
    result: 'RESULT MISMATCH',
    score: '0.000',
    weight: '0%',
    status: 'rejected',
  },
];

const pipeline = [
  ['01', 'Commit', 'Validator commits an unpredictable workload seed.'],
  ['02', 'Compete', 'Miners return executable SQL and bounded index plans.'],
  ['03', 'Verify', 'Hidden rows prove exact equivalence before timing begins.'],
  ['04', 'Reward', 'Only correct artifacts compete for Bittensor weight.'],
];

export default function Home() {
  return (
    <main className="min-h-screen overflow-hidden bg-background text-foreground">
      <div className="signal-grid fixed inset-0 z-0 opacity-40" />
      <nav className="relative z-10 border-b border-white/10 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 lg:px-8">
          <a
            className="flex items-center gap-3"
            href="#top"
            aria-label="PlanRace home"
          >
            <span className="grid size-8 place-items-center rounded-sm bg-primary text-primary-foreground">
              <DatabaseZap className="size-4" />
            </span>
            <span className="font-mono text-sm font-semibold tracking-[0.18em]">
              PLANRACE
            </span>
          </a>
          <div className="flex items-center gap-3">
            <Badge
              className="border-primary/30 bg-primary/10 text-primary"
              variant="outline"
            >
              <CircleDot className="animate-pulse" /> localnet verified
            </Badge>
            <a
              className="hidden items-center gap-1.5 text-sm text-muted-foreground transition hover:text-foreground sm:flex"
              href="https://github.com/dorakingx/planrace-subnet"
              rel="noreferrer"
              target="_blank"
            >
              GitHub <ArrowUpRight className="size-4" />
            </a>
          </div>
        </div>
      </nav>

      <section
        id="top"
        className="relative z-10 mx-auto max-w-7xl px-5 pb-16 pt-14 lg:px-8 lg:pt-20"
      >
        <div className="grid items-end gap-10 lg:grid-cols-[1.05fr_.95fr]">
          <div>
            <p className="mb-5 font-mono text-xs uppercase tracking-[0.24em] text-primary">
              Bittensor · verified optimization market
            </p>
            <h1 className="max-w-3xl text-balance text-5xl font-semibold leading-[.95] tracking-[-0.055em] sm:text-7xl">
              Faster queries.
              <br />
              Truth first.
            </h1>
            <p className="mt-7 max-w-xl text-pretty text-base leading-7 text-muted-foreground sm:text-lg">
              PlanRace turns SQL optimization into a competitive digital
              commodity. Miners race to produce faster plans; validators prove
              identical results on hidden data before a single point is awarded.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a className="cta-primary" href="#evidence">
                Inspect the evidence
              </a>
              <a
                className="cta-secondary"
                href="https://github.com/dorakingx/planrace-subnet#working-proof"
                rel="noreferrer"
                target="_blank"
              >
                Run it locally <Code2 className="size-4" />
              </a>
            </div>
          </div>

          <Card className="terminal-card gap-0 border-0 bg-card/90 py-0 shadow-2xl shadow-black/30">
            <CardHeader className="flex-row items-center justify-between border-b border-white/10 px-5 py-4">
              <div className="flex gap-1.5" aria-hidden="true">
                <i className="size-2 rounded-full bg-red-400/70" />
                <i className="size-2 rounded-full bg-amber-300/70" />
                <i className="size-2 rounded-full bg-primary/80" />
              </div>
              <span className="font-mono text-[11px] text-muted-foreground">
                epoch 8 · netuid 2
              </span>
            </CardHeader>
            <CardContent className="space-y-4 px-5 py-5 font-mono text-xs sm:text-sm">
              <p>
                <span className="text-primary">$</span> validator.dispatch
                --miners 2
              </p>
              <p className="text-muted-foreground">
                ↳ receiver-bound signatures verified{' '}
                <span className="text-foreground">2/2</span>
              </p>
              <p className="text-muted-foreground">
                ↳ hidden workload revealed{' '}
                <span className="text-foreground">orders-v1-e8</span>
              </p>
              <div className="space-y-2 border-y border-white/10 py-4">
                <p className="flex justify-between gap-3">
                  <span>UID 1 · indexed</span>
                  <span className="text-primary">PASS 9.084</span>
                </p>
                <p className="flex justify-between gap-3">
                  <span>UID 2 · gaming</span>
                  <span className="text-red-400">FAIL 0.000</span>
                </p>
              </div>
              <p className="text-muted-foreground">
                weight plan <span className="text-foreground">[1 → 1.0]</span>
              </p>
              <p className="text-primary">✓ finalized in block 1870</p>
            </CardContent>
          </Card>
        </div>

        <div className="mt-14 grid grid-cols-2 border-y border-white/10 sm:grid-cols-4">
          {[
            ['35', 'tests passing'],
            ['86.09%', 'code coverage'],
            ['2 / 2', 'signed responses'],
            ['1', 'on-chain weight'],
          ].map(([value, label]) => (
            <div
              className="border-white/10 px-4 py-6 not-last:border-r"
              key={label}
            >
              <p className="font-mono text-2xl font-semibold text-primary">
                {value}
              </p>
              <p className="mt-1 text-xs uppercase tracking-[0.14em] text-muted-foreground">
                {label}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section
        id="evidence"
        className="relative z-10 border-y border-white/10 bg-black/15 py-16"
      >
        <div className="mx-auto max-w-7xl px-5 lg:px-8">
          <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
            <div>
              <p className="section-kicker">Observed localnet result</p>
              <h2 className="section-title">
                Correctness decides who gets paid.
              </h2>
            </div>
            <p className="max-w-md text-sm leading-6 text-muted-foreground">
              Same task, two strategies. Speed cannot rescue a wrong answer: the
              exact-result gate runs first.
            </p>
          </div>
          <div className="overflow-hidden rounded-xl border border-white/10 bg-card/70">
            <div className="grid grid-cols-[44px_1fr_80px] gap-3 border-b border-white/10 px-4 py-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground sm:grid-cols-[60px_1.4fr_1fr_100px_100px]">
              <span>Rank</span>
              <span>Miner</span>
              <span className="hidden sm:block">Verification</span>
              <span>Score</span>
              <span className="hidden sm:block">Weight</span>
            </div>
            {miners.map((miner) => (
              <div
                className="grid grid-cols-[44px_1fr_80px] items-center gap-3 border-b border-white/10 px-4 py-5 last:border-0 sm:grid-cols-[60px_1.4fr_1fr_100px_100px]"
                key={miner.uid}
              >
                <span className="font-mono text-muted-foreground">
                  {miner.rank}
                </span>
                <div>
                  <p className="font-medium">{miner.name}</p>
                  <p className="font-mono text-xs text-muted-foreground">
                    {miner.uid}
                  </p>
                </div>
                <span
                  className={`hidden items-center gap-2 font-mono text-xs sm:flex ${miner.status === 'accepted' ? 'text-primary' : 'text-red-400'}`}
                >
                  {miner.status === 'accepted' ? (
                    <Check className="size-4" />
                  ) : (
                    <X className="size-4" />
                  )}
                  {miner.result}
                </span>
                <span className="font-mono text-lg">{miner.score}</span>
                <span
                  className={`hidden font-mono text-lg sm:block ${miner.status === 'accepted' ? 'text-primary' : 'text-muted-foreground'}`}
                >
                  {miner.weight}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-x-7 gap-y-2 font-mono text-[11px] text-muted-foreground">
            <span>extrinsic 1870-0002</span>
            <span>raw weight 65535</span>
            <span>fee 0 local TAO</span>
          </div>
        </div>
      </section>

      <section className="relative z-10 mx-auto max-w-7xl px-5 py-20 lg:px-8">
        <div className="grid gap-10 lg:grid-cols-[.7fr_1.3fr]">
          <div>
            <p className="section-kicker">Mechanism</p>
            <h2 className="section-title">
              Verification is cheaper than invention.
            </h2>
            <p className="mt-5 max-w-md leading-7 text-muted-foreground">
              Every epoch creates fresh demand. Independent miners can use
              heuristics, solvers, or learned optimizers; the protocol only
              rewards replayable improvements.
            </p>
          </div>
          <div className="grid gap-px overflow-hidden rounded-xl border border-white/10 bg-white/10 sm:grid-cols-2">
            {pipeline.map(([number, title, copy]) => (
              <div className="bg-background/95 p-6" key={number}>
                <span className="font-mono text-xs text-primary">{number}</span>
                <h3 className="mt-7 text-xl font-medium">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  {copy}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="relative z-10 border-t border-white/10">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 px-5 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between lg:px-8">
          <div className="flex flex-wrap items-center gap-5">
            <span className="flex items-center gap-2">
              <ShieldCheck className="size-4 text-primary" /> exact-first
            </span>
            <span className="flex items-center gap-2">
              <Clock3 className="size-4 text-primary" /> measured
            </span>
            <span className="flex items-center gap-2">
              <GitBranch className="size-4 text-primary" /> open source
            </span>
          </div>
          <p>PlanRace · Apache-2.0 · owned by dorakingx</p>
        </div>
      </footer>
    </main>
  );
}
