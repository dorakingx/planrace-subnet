import {
  ArrowUpRight,
  Check,
  CircleDot,
  Clock3,
  Code2,
  DatabaseZap,
  Download,
  FileCheck2,
  GitBranch,
  LockKeyhole,
  ShieldCheck,
  Terminal,
  X,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import manifest from '@/evidence/localnet-v1-epoch-8.json';

const RAW_MANIFEST_URL = '/evidence/localnet-v1-epoch-8.json';
const REPOSITORY_URL = 'https://github.com/dorakingx/planrace-subnet';
const TECHNICAL_DOCS_URL = `${REPOSITORY_URL}/blob/main/PROTOCOL.md`;

const shortHash = (value: string, visible = 10) =>
  `${value.slice(0, visible)}…${value.slice(-6)}`;

const weightByUid = new Map(
  manifest.weight_plan.uids.map((uid, index) => [
    uid,
    manifest.weight_plan.weights[index],
  ]),
);
const correctnessPassed = manifest.scores.filter(
  (score) => score.correct,
).length;
const correctnessFailed = manifest.scores.length - correctnessPassed;
const baselineRelative = manifest.scores.find(
  (score) => score.baseline_relative_speedup !== null,
)?.baseline_relative_speedup;
const latestExtrinsic = manifest.extrinsics.at(0);

const headlineMetrics = [
  [String(manifest.validator_hotkeys.length), 'validator identity'],
  [String(manifest.miner_hotkeys.length), 'miner identities'],
  [
    String(manifest.authentication.authenticated_requests),
    'authenticated requests',
  ],
  [String(manifest.weight_plan.uids.length), 'local-chain weight recipient'],
];

const pipeline = [
  [
    '01',
    'Commit',
    'The validator binds a task to reveal material. Protocol v1 secrecy limits are disclosed below.',
  ],
  [
    '02',
    'Compete',
    'Miners return executable optimization artifacts within a bounded request.',
  ],
  [
    '03',
    'Verify',
    'Validators check exact result equality on unrevealed generated test data before timing.',
  ],
  [
    '04',
    'Reward',
    'Only artifacts that pass the equality gate can receive local-chain weight.',
  ],
];

export default function Home() {
  return (
    <main className="min-h-screen overflow-hidden bg-background text-foreground">
      <a className="skip-link" href="#evidence">
        Skip to verified evidence
      </a>
      <div
        className="signal-grid fixed inset-0 z-0 opacity-40"
        aria-hidden="true"
      />

      <nav
        aria-label="Primary navigation"
        className="relative z-10 border-b border-white/10 bg-background/80 backdrop-blur-xl"
      >
        <div className="mx-auto flex min-h-16 max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-3 lg:px-8">
          <a
            className="flex items-center gap-3"
            href="#top"
            aria-label="PlanRace home"
          >
            <span className="grid size-8 place-items-center rounded-sm bg-primary text-primary-foreground">
              <DatabaseZap className="size-4" aria-hidden="true" />
            </span>
            <span className="font-mono text-sm font-semibold tracking-[0.18em]">
              PLANRACE
            </span>
          </a>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Badge className="border-primary/40 bg-primary/10 text-primary">
              <CircleDot className="size-3 animate-pulse" aria-hidden="true" />
              LOCALNET EVIDENCE
            </Badge>
            <Badge className="border-amber-300/35 bg-amber-300/10 text-amber-200">
              TESTNET PENDING
            </Badge>
            <a
              className="ml-1 hidden items-center gap-1.5 text-sm text-muted-foreground transition hover:text-foreground sm:flex"
              href={REPOSITORY_URL}
              rel="noreferrer"
              target="_blank"
            >
              GitHub <ArrowUpRight className="size-4" aria-hidden="true" />
            </a>
          </div>
        </div>
      </nav>

      <section
        id="top"
        className="relative z-10 mx-auto max-w-7xl px-5 pt-14 pb-16 lg:px-8 lg:pt-20"
      >
        <div className="grid items-end gap-10 lg:grid-cols-[1.05fr_.95fr]">
          <div>
            <p className="mb-5 font-mono text-xs uppercase tracking-[0.24em] text-primary">
              Bittensor · verified optimization market
            </p>
            <h1 className="max-w-3xl text-balance text-5xl leading-[.95] font-semibold tracking-[-0.055em] sm:text-7xl">
              Faster queries.
              <br />
              Truth first.
            </h1>
            <p className="mt-7 max-w-xl text-pretty text-base leading-7 text-muted-foreground sm:text-lg">
              PlanRace turns query optimization into a competitive digital
              commodity. Validators verify exact result equality across
              unrevealed test databases before awarding weight.
            </p>
            <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">
              The browser below is deliberately scoped to a historical localnet
              v1 run. It does not claim testnet activity or universal SQL
              semantic equivalence.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a className="cta-primary" href="#evidence">
                Inspect the evidence
              </a>
              <a
                className="cta-secondary"
                href={`${REPOSITORY_URL}#working-proof`}
                rel="noreferrer"
                target="_blank"
              >
                Run it locally <Code2 className="size-4" aria-hidden="true" />
              </a>
            </div>
          </div>

          <Card className="terminal-card border-0 bg-card/90 shadow-2xl shadow-black/30">
            <CardHeader className="flex items-center justify-between border-b border-white/10 px-5 py-4">
              <div className="flex gap-1.5" aria-hidden="true">
                <i className="size-2 rounded-full bg-red-400/70" />
                <i className="size-2 rounded-full bg-amber-300/70" />
                <i className="size-2 rounded-full bg-primary/80" />
              </div>
              <span className="font-mono text-[11px] text-muted-foreground">
                epoch {manifest.epoch} · netuid {manifest.netuid}
              </span>
            </CardHeader>
            <CardContent className="space-y-4 px-5 py-5 font-mono text-xs sm:text-sm">
              <p>
                <span className="text-primary">$</span> planrace evidence verify
                manifest.json
              </p>
              <p className="text-muted-foreground">
                ↳ validator signature{' '}
                <span className="text-primary">VERIFIED</span>
              </p>
              <p className="text-muted-foreground">
                ↳ authenticated requests{' '}
                <span className="text-foreground">
                  {manifest.authentication.authenticated_requests}
                </span>
              </p>
              <p className="text-muted-foreground">
                ↳ signed responses{' '}
                <span className="text-amber-200">
                  {manifest.authentication.signed_responses === 0
                    ? 'NOT EVIDENCED'
                    : manifest.authentication.signed_responses}
                </span>
              </p>
              <div className="space-y-2 border-y border-white/10 py-4">
                <p className="flex justify-between gap-3">
                  <span>exact equality</span>
                  <span className="text-primary">PASS {correctnessPassed}</span>
                </p>
                <p className="flex justify-between gap-3">
                  <span>result mismatch</span>
                  <span className="text-red-400">FAIL {correctnessFailed}</span>
                </p>
              </div>
              <p className="text-muted-foreground">
                local-chain weight{' '}
                <span className="text-foreground">
                  [{manifest.weight_plan.uids.join(', ')}]
                </span>
              </p>
              <p className="text-primary">
                ✓ signed payload{' '}
                {shortHash(manifest.validator_signature.signed_payload_sha256)}
              </p>
            </CardContent>
          </Card>
        </div>

        <div className="mt-14 grid grid-cols-2 border-y border-white/10 sm:grid-cols-4">
          {headlineMetrics.map(([value, label]) => (
            <div
              className="border-white/10 px-4 py-6 not-last:border-r"
              key={label}
            >
              <p className="font-mono text-2xl font-semibold text-primary">
                {value}
              </p>
              <p className="mt-1 text-xs uppercase tracking-[0.12em] text-muted-foreground">
                {label}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section
        id="evidence"
        className="relative z-10 scroll-mt-4 border-y border-white/10 bg-black/15 py-16"
      >
        <div className="mx-auto max-w-7xl px-5 lg:px-8">
          <div className="mb-8 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
            <div>
              <p className="section-kicker">Verifiable evidence browser</p>
              <h2 className="section-title">Latest signed localnet run.</h2>
            </div>
            <p className="max-w-lg text-sm leading-6 text-muted-foreground">
              Every value below is read from a manifest whose sr25519 signature
              is verified before the production build. Editing a signed field
              makes the build fail.
            </p>
          </div>

          <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ['Run', manifest.run_id],
              ['Protocol', manifest.protocol_version],
              ['Git commit', shortHash(manifest.git_commit)],
              ['Observed', manifest.timestamps.observed_at],
            ].map(([label, value]) => (
              <dl className="evidence-field" key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </dl>
            ))}
          </div>

          <div className="grid gap-5 xl:grid-cols-[1.4fr_.6fr]">
            <div className="overflow-x-auto rounded-xl border border-white/10 bg-card/70">
              <table className="w-full min-w-[780px] text-left">
                <caption className="sr-only">
                  Miner correctness, performance, score, and weight evidence
                </caption>
                <thead>
                  <tr className="border-b border-white/10 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    <th className="px-4 py-3 font-medium" scope="col">
                      Miner
                    </th>
                    <th className="px-4 py-3 font-medium" scope="col">
                      Exact result
                    </th>
                    <th className="px-4 py-3 font-medium" scope="col">
                      Warm / setup
                    </th>
                    <th className="px-4 py-3 font-medium" scope="col">
                      Plan cost
                    </th>
                    <th className="px-4 py-3 font-medium" scope="col">
                      Score
                    </th>
                    <th className="px-4 py-3 font-medium" scope="col">
                      Weight
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {manifest.scores.map((score) => {
                    const weight = weightByUid.get(score.uid) ?? 0;
                    return (
                      <tr
                        className="border-b border-white/10 last:border-0"
                        key={score.uid}
                      >
                        <th className="px-4 py-5 font-normal" scope="row">
                          <p className="font-medium">{score.profile}</p>
                          <p className="mt-1 font-mono text-xs text-muted-foreground">
                            UID {score.uid} · {shortHash(score.miner_hotkey, 7)}
                          </p>
                        </th>
                        <td className="px-4 py-5">
                          <span
                            className={`inline-flex items-center gap-2 font-mono text-xs ${
                              score.correct ? 'text-primary' : 'text-red-400'
                            }`}
                          >
                            {score.correct ? (
                              <Check className="size-4" aria-hidden="true" />
                            ) : (
                              <X className="size-4" aria-hidden="true" />
                            )}
                            {score.correct ? 'MATCH' : score.failure_code}
                          </span>
                        </td>
                        <td className="px-4 py-5 font-mono text-xs">
                          {score.median_warm_ms === null
                            ? '—'
                            : `${score.median_warm_ms.toFixed(3)} / ${score.setup_ms?.toFixed(3)} ms`}
                        </td>
                        <td className="px-4 py-5 font-mono text-xs">
                          {score.plan_cost ?? '—'}
                        </td>
                        <td className="px-4 py-5 font-mono text-lg">
                          {score.score.toFixed(3)}
                        </td>
                        <td className="px-4 py-5 font-mono text-lg text-primary">
                          {(weight * 100).toFixed(0)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <Card className="bg-card/70">
              <CardHeader className="border-b border-white/10 px-5 py-4">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Performance context
                </p>
              </CardHeader>
              <CardContent className="space-y-4 px-5 py-5">
                <div>
                  <p className="text-sm text-muted-foreground">
                    Baseline-relative speedup
                  </p>
                  <p className="mt-1 font-mono text-lg text-amber-200">
                    {baselineRelative === undefined
                      ? 'NOT RECORDED'
                      : `${baselineRelative}×`}
                  </p>
                </div>
                <p className="text-sm leading-6 text-muted-foreground">
                  This historical v1 run recorded warm latency, setup time, plan
                  cost, and an absolute score. It did not preserve a same-worker
                  baseline measurement, so no relative speedup is invented.
                </p>
              </CardContent>
            </Card>
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-2">
            <Card className="bg-card/70">
              <CardHeader className="border-b border-white/10 px-5 py-4">
                <p className="flex items-center gap-2 font-medium">
                  <LockKeyhole
                    className="size-4 text-primary"
                    aria-hidden="true"
                  />
                  Commitment & reveal
                </p>
              </CardHeader>
              <CardContent className="space-y-4 px-5 py-5 text-sm">
                <div>
                  <p className="field-label">Task commitment</p>
                  <code className="hash-value">{manifest.task_commitment}</code>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <p className="field-label">Reveal verification</p>
                    <p className="mt-1 font-mono text-primary">
                      {manifest.task_reveal.verified ? 'VERIFIED' : 'FAILED'}
                    </p>
                  </div>
                  <div>
                    <p className="field-label">Task ID</p>
                    <p className="mt-1 break-all font-mono text-xs">
                      {manifest.task_reveal.task_id}
                    </p>
                  </div>
                </div>
                <div>
                  <p className="field-label">Reveal digest</p>
                  <code className="hash-value">
                    {manifest.task_reveal.reveal_digest}
                  </code>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-card/70">
              <CardHeader className="border-b border-white/10 px-5 py-4">
                <p className="flex items-center gap-2 font-medium">
                  <GitBranch
                    className="size-4 text-primary"
                    aria-hidden="true"
                  />
                  Local-chain finalization
                </p>
              </CardHeader>
              <CardContent className="space-y-4 px-5 py-5 text-sm">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <p className="field-label">Extrinsic</p>
                    <p className="mt-1 font-mono">
                      {latestExtrinsic?.extrinsic_id ?? 'Not recorded'}
                    </p>
                  </div>
                  <div>
                    <p className="field-label">Readback</p>
                    <p className="mt-1 font-mono">
                      block {manifest.readback.last_update} · validator UID{' '}
                      {manifest.readback.validator_uid}
                    </p>
                  </div>
                </div>
                <div>
                  <p className="field-label">Block hash</p>
                  <code className="hash-value">
                    {latestExtrinsic
                      ? `0x${latestExtrinsic.block_hash}`
                      : 'Not recorded'}
                  </code>
                </div>
                <div>
                  <p className="field-label">Metagraph weight readback</p>
                  <p className="mt-1 font-mono text-xs">
                    {manifest.readback.raw_weights
                      .map(([uid, weight]) => `UID ${uid} → ${weight}`)
                      .join(' · ')}
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-[1.2fr_.8fr]">
            <Card className="bg-card/70">
              <CardHeader className="border-b border-white/10 px-5 py-4">
                <p className="flex items-center gap-2 font-medium">
                  <FileCheck2
                    className="size-4 text-primary"
                    aria-hidden="true"
                  />
                  Verify it yourself
                </p>
              </CardHeader>
              <CardContent className="space-y-5 px-5 py-5">
                <div>
                  <p className="field-label">Signed payload SHA-256</p>
                  <code className="hash-value">
                    {manifest.validator_signature.signed_payload_sha256}
                  </code>
                </div>
                <div>
                  <p className="field-label">Validator signer</p>
                  <code className="hash-value">
                    {manifest.validator_signature.signer_hotkey}
                  </code>
                </div>
                <div>
                  <p className="field-label">Verification command</p>
                  <pre className="mt-2 overflow-x-auto rounded-md border border-white/10 bg-black/30 p-3 font-mono text-xs">
                    <code>
                      planrace evidence verify localnet-v1-epoch-8.json
                    </code>
                  </pre>
                </div>
                <div className="flex flex-wrap gap-3">
                  <a
                    className="cta-primary gap-2"
                    href={RAW_MANIFEST_URL}
                    download
                  >
                    <Download className="size-4" aria-hidden="true" />
                    Raw manifest
                  </a>
                  <a
                    className="cta-secondary"
                    href={TECHNICAL_DOCS_URL}
                    rel="noreferrer"
                    target="_blank"
                  >
                    Technical docs
                    <ArrowUpRight className="size-4" aria-hidden="true" />
                  </a>
                </div>
              </CardContent>
            </Card>

            <Card className="border-amber-300/20 bg-amber-300/[0.04]">
              <CardHeader className="border-b border-amber-300/15 px-5 py-4">
                <p className="font-medium text-amber-100">TESTNET PENDING</p>
              </CardHeader>
              <CardContent className="space-y-3 px-5 py-5 text-sm leading-6 text-muted-foreground">
                <p>
                  No testnet run, validator/miner interaction, weight extrinsic,
                  or metagraph readback is published yet.
                </p>
                <p>
                  This panel changes to TESTNET VERIFIED only after a separate
                  signed testnet manifest passes the same verifier.
                </p>
              </CardContent>
            </Card>
          </div>

          <Card className="mt-5 bg-card/70">
            <CardHeader className="border-b border-white/10 px-5 py-4">
              <p className="font-medium">Known limitations</p>
            </CardHeader>
            <CardContent className="px-5 py-5">
              <ul className="grid gap-x-8 gap-y-3 text-sm leading-6 text-muted-foreground md:grid-cols-2">
                {manifest.known_limitations.map((limitation) => (
                  <li className="flex gap-3" key={limitation}>
                    <span
                      className="mt-2 size-1.5 shrink-0 rounded-full bg-amber-300"
                      aria-hidden="true"
                    />
                    <span>{limitation}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="relative z-10 mx-auto max-w-7xl px-5 py-20 lg:px-8">
        <div className="grid gap-10 lg:grid-cols-[.7fr_1.3fr]">
          <div>
            <p className="section-kicker">Mechanism</p>
            <h2 className="section-title">Verification before reward.</h2>
            <p className="mt-5 max-w-md leading-7 text-muted-foreground">
              Independent miners can use heuristics, solvers, or learned
              optimizers. The protocol rewards only artifacts that reproduce the
              known result on validator-held fixtures.
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
              <ShieldCheck className="size-4 text-primary" aria-hidden="true" />
              exact-result gate
            </span>
            <span className="flex items-center gap-2">
              <Clock3 className="size-4 text-primary" aria-hidden="true" />
              measured
            </span>
            <span className="flex items-center gap-2">
              <Terminal className="size-4 text-primary" aria-hidden="true" />
              independently verifiable
            </span>
          </div>
          <p>
            <a
              className="underline-offset-4 hover:text-foreground hover:underline"
              href={REPOSITORY_URL}
            >
              PlanRace
            </a>{' '}
            · Apache-2.0 · localnet evidence
          </p>
        </div>
      </footer>
    </main>
  );
}
