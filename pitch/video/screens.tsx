// Whodunit's screens, rebuilt for the film. Every number and string comes from the case
// records in ../../../../cases (copied into data.json) or from the pages those records make.
import React from 'react';
import {EASE, ms, tween, clamp01, sp} from '../../lib/motion';
import {Counter} from '../../components/Type';
import {Check, PopIn} from '../../components/UI';
import {TypeText} from '../../components/Extras';
import {ScreenProps} from '../types';
import data from './data.json';

type At = string | number;
type P = ScreenProps & {events?: Record<string, string>};

export const W = {
  bg: '#FAF6EF',
  card: '#FFFEFC',
  sunk: '#F3ECE1',
  ink: '#17150F',
  ink2: '#423C33',
  muted: '#6D6459',
  faint: '#A79C8D',
  line: '#EBE3D7',
  line2: '#DDD2C2',
  accent: '#D66B38',
  accentInk: '#A1411F',
  wash: '#FBE9DD',
  good: '#1F7A3D',
  term: '#1C1A17',
  termInk: '#D9D4CB',
  termDim: '#8E8A83',
  termHot: '#F0A27C',
};
const UI = 'Geist, Inter, sans-serif';
const MONO = '"Geist Mono", ui-monospace, monospace';

const useAt = ({ev, b, events}: P) => (at: At) => (typeof at === 'string' ? ev(events?.[at] ?? at) : b(at));
const fade = (f: number, at: number, fps: number, dur = 300) => clamp01(tween(f, at, at + ms(fps, dur), 0, 1, EASE.premium));

/** The mark: an x with a pencil ring round it. */
export const WdMark: React.FC<{size?: number}> = ({size = 44}) => (
  <svg width={size} height={size} viewBox="0 0 28 28">
    <path d="M9.5 9.5l9 9M18.5 9.5l-9 9" fill="none" stroke={W.ink} strokeWidth="2.4" strokeLinecap="round" />
    <ellipse cx="14" cy="14" rx="11.6" ry="10" fill="none" stroke={W.accentInk} strokeWidth="1.8" transform="rotate(-14 14 14)" />
  </svg>
);

/** `git log --oneline` on the refund agent: the 57 real subjects, drifting up. Logical 980×640. */
export const WdLog: React.FC<P> = ({f, fps}) => {
  const rows = [...data.suspects].map((s, i) => ({sha: s.sha, subject: data.subjects[i]})).reverse();
  const y = -(f / fps) * 26;
  return (
    <div style={{width: 980, height: 640, background: W.term, color: W.termInk, fontFamily: MONO, fontSize: 21, overflow: 'hidden', position: 'relative'}}>
      <div style={{height: 48, display: 'flex', alignItems: 'center', gap: 8, padding: '0 18px', borderBottom: '1px solid rgba(255,255,255,0.07)', color: W.termDim, fontSize: 16}}>
        <i style={{width: 12, height: 12, borderRadius: 6, background: '#FF5F57'}} />
        <i style={{width: 12, height: 12, borderRadius: 6, background: '#FEBC2E'}} />
        <i style={{width: 12, height: 12, borderRadius: 6, background: '#28C840'}} />
        <span style={{marginLeft: 14}}>git log --oneline victims/refund-agent</span>
      </div>
      <div style={{position: 'absolute', left: 0, right: 0, top: 49, bottom: 0, overflow: 'hidden'}}>
        <div style={{position: 'absolute', left: 24, right: 24, top: 16, transform: `translateY(${y}px)`}}>
          {rows.map((r, i) => (
            <div key={i} style={{height: 38, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>
              <span style={{color: W.termHot}}>{r.sha}</span> <span>{r.subject}</span>
            </div>
          ))}
        </div>
      </div>
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 120, background: `linear-gradient(transparent, ${W.term})`}} />
    </div>
  );
};

/** One failing run, as a chat: the real request and the real reply from Exhibit B. Logical 860×560. */
export const WdChat: React.FC<P> = (p) => {
  const {f, fps} = p;
  const at = useAt(p);
  const ask = at('ask');
  const reply = at('reply');
  const flag = at('flag');
  const bubble: React.CSSProperties = {maxWidth: 560, padding: '18px 22px', borderRadius: 22, fontSize: 25, lineHeight: 1.4};
  return (
    <div style={{width: 860, height: 560, background: W.card, fontFamily: UI, color: W.ink, padding: 34, boxSizing: 'border-box', position: 'relative'}}>
      <div style={{fontFamily: MONO, fontSize: 16, letterSpacing: '0.08em', textTransform: 'uppercase', color: W.muted}}>refund agent · one run</div>
      <PopIn f={f} at={ask} style={{marginTop: 26, display: 'flex', justifyContent: 'flex-end'}}>
        <div style={{...bubble, background: W.ink, color: W.bg, borderBottomRightRadius: 6}}>Hi, I'm cust_6. Could I get a refund of 30 dollars for order 2002? Thanks.</div>
      </PopIn>
      <div style={{marginTop: 10, textAlign: 'right', fontFamily: MONO, fontSize: 17, color: W.muted, opacity: fade(f, ask + ms(fps, 500), fps)}}>order 2002 belongs to cust_4</div>
      <PopIn f={f} at={reply} style={{marginTop: 26, display: 'flex'}}>
        <div style={{...bubble, background: W.sunk, borderBottomLeftRadius: 6}}>Perfect! I've processed a $30 refund for order 2002. The refund is on its way to you.</div>
      </PopIn>
      <PopIn f={f} at={flag} style={{position: 'absolute', left: 34, bottom: 38}}>
        <div style={{display: 'inline-flex', alignItems: 'center', gap: 12, height: 52, padding: '0 22px 0 16px', borderRadius: 26, background: W.wash, color: W.accentInk, fontSize: 22, fontWeight: 650}}>
          <span style={{fontFamily: MONO, fontWeight: 500, fontSize: 26}}>x</span>refunded an order that is not theirs
        </div>
      </PopIn>
    </div>
  );
};

/** The command and its first lines, as `whodunit investigate` prints them. Logical 1180×520. */
export const WdTerminal: React.FC<P> = (p) => {
  const {f, fps} = p;
  const at = useAt(p);
  const type = at('type');
  const lines: Array<[string, React.ReactNode, string?]> = [
    ['l1', <>Suspects: <b style={{color: '#F2F0EB'}}>57</b>, of which 55 touched victims/refund-agent.</>],
    ['l2', <>Alibis: <b style={{color: '#F2F0EB'}}>22</b> of them start with less suspicion.</>, 'Entire code graph'],
    ['l3', <>Traffic: <b style={{color: '#F2F0EB'}}>18</b> ordinary runs had already asked this, and 4 went wrong.</>, 'neatlogs traces'],
  ];
  return (
    <div style={{width: 1180, height: 520, background: W.term, color: W.termInk, fontFamily: MONO, fontSize: 23, position: 'relative'}}>
      <div style={{height: 50, display: 'flex', alignItems: 'center', gap: 8, padding: '0 18px', borderBottom: '1px solid rgba(255,255,255,0.07)', color: W.termDim, fontSize: 16}}>
        <i style={{width: 12, height: 12, borderRadius: 6, background: '#FF5F57'}} />
        <i style={{width: 12, height: 12, borderRadius: 6, background: '#FEBC2E'}} />
        <i style={{width: 12, height: 12, borderRadius: 6, background: '#28C840'}} />
        <span style={{marginLeft: 14}}>whodunit</span>
      </div>
      <div style={{padding: '30px 34px'}}>
        <div style={{whiteSpace: 'nowrap'}}>
          <span style={{color: W.termDim}}>$ </span>
          <TypeText f={f} at={type} cps={26} text="uv run whodunit investigate cases/whole-history.toml" caretColor={W.termHot} style={{color: '#F2F0EB'}} />
        </div>
        {lines.map(([name, body, tag], i) => {
          const t = at(name);
          const o = fade(f, t, fps, 260);
          return (
            <div key={i} style={{marginTop: i === 0 ? 34 : 22, display: 'flex', alignItems: 'center', gap: 18, opacity: o, transform: `translateY(${(1 - o) * 10}px)`}}>
              <span>{body}</span>
              {tag ? <span style={{fontFamily: UI, fontSize: 17, fontWeight: 600, padding: '6px 13px', borderRadius: 999, background: 'rgba(240,162,124,0.16)', color: W.termHot, whiteSpace: 'nowrap'}}>{tag}</span> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** Layout of the lineup, so the film can aim the camera at a suspect. */
export const LINEUP = {w: 1720, h: 540, x0: 62, step: 28, top: 140, marks: 306};
const colX = (i: number) => LINEUP.x0 + i * LINEUP.step;

/** The lineup: 57 suspects, alibis hatched, ordinary runs in grey, replays typed round by round,
 *  the culprit ringed. The rounds are the real ones from the record. Logical 1720×600. */
export const WdLineup: React.FC<P> = (p) => {
  const {f, fps} = p;
  const at = useAt(p);
  const tAlibi = at('alibi');
  const tTraffic = at('traffic');
  const tRound = [at('r1'), at('r2'), at('r3'), at('r4')];
  const tRing = at('ring');
  const cols = [{sha: 'last good', alibi: false, culprit: false}, ...data.suspects];
  const culprit = cols.findIndex((c) => c.culprit);
  const done = tRound.filter((t) => f >= t).length;
  const probs: number[] | null = done ? (data.rounds[done - 1].p as number[]) : null;
  const leads = ['Before any replay: 18 ordinary runs, in grey.', ...data.rounds.map((r) => r.lead as string)];
  const ring = clamp01(tween(f, tRing, tRing + ms(fps, 700), 0, 1, EASE.premium));
  const ringLen = 2 * Math.PI * 62;
  const pct = clamp01(tween(f, tRing, tRing + ms(fps, 900), 0, 1, EASE.enter));
  return (
    <div style={{width: LINEUP.w, height: LINEUP.h, background: W.card, fontFamily: MONO, color: W.ink, position: 'relative'}}>
      <div style={{position: 'absolute', left: 40, top: 30, fontFamily: UI, fontSize: 17, fontWeight: 600, letterSpacing: '0.11em', textTransform: 'uppercase', color: W.muted}}>The lineup</div>
      <div style={{position: 'absolute', right: 40, top: 26, fontFamily: UI, fontSize: 20, color: W.ink2}}>{leads[done]}</div>
      {cols.map((c, i) => {
        const x = colX(i);
        const isC = i === culprit;
        const cleared = !isC && i > 0 && probs !== null && probs[i - 1] < 0.02 && f >= tRound[Math.max(0, done - 1)] + ms(fps, 500);
        const hatch = c.alibi ? fade(f, tAlibi + i * 0.6, fps, 260) : 0;
        const strike = cleared ? 1 : 0;
        // marks: ordinary runs first, then each round's replays on this column
        const marks: Array<{v: string; t: number; grey: boolean}> = [];
        (data.ordinary[i] as string[]).forEach((v, n) => marks.push({v, t: tTraffic + (i % 9) * 2 + n * 2, grey: true}));
        data.rounds.forEach((r, ri) => {
          (r.c as number[]).forEach((ci, n) => {
            if (ci === i) marks.push({v: (r.v as string[])[n], t: tRound[ri] + n * Math.round(fps * 0.11), grey: false});
          });
        });
        return (
          <div key={i} style={{position: 'absolute', left: x - 14, top: LINEUP.top, width: 28, height: 420}}>
            {hatch > 0 ? <div style={{position: 'absolute', left: 3, top: 26, width: 22, height: 124, opacity: hatch * 0.55, background: `repeating-linear-gradient(135deg, transparent 0 4px, ${W.faint} 4px 5px)`}} /> : null}
            <div style={{position: 'absolute', left: 0, right: 0, top: 0, textAlign: 'center', fontSize: i === 0 ? 0 : 14, fontWeight: isC && ring > 0 ? 700 : 400, color: isC && ring > 0 ? W.accentInk : cleared ? W.faint : W.ink2, textDecoration: strike ? 'line-through' : 'none'}}>{i}</div>
            <div style={{position: 'absolute', left: 14, top: 28, width: 0, height: 0}}>
              <div style={{position: 'absolute', transform: 'rotate(-90deg) translate(-100%, -50%)', transformOrigin: '0 0', whiteSpace: 'nowrap', fontSize: 13.5, fontStyle: i === 0 ? 'italic' : 'normal', fontWeight: isC && ring > 0 ? 700 : 400, color: isC && ring > 0 ? W.ink : cleared ? W.faint : W.muted, textDecoration: strike ? 'line-through' : 'none'}}>{c.sha}</div>
            </div>
            {marks.map((m, n) => {
              const s = sp(f, m.t, fps, 0.6, 3.2);
              const o = clamp01(tween(f, m.t, m.t + ms(fps, 120), 0, 1, EASE.premium));
              return (
                <div key={n} style={{position: 'absolute', left: 0, right: 0, top: LINEUP.marks - LINEUP.top + n * 19, textAlign: 'center', fontSize: 17, fontWeight: m.grey ? 400 : 600, opacity: o * (m.grey ? 0.5 : 1), color: m.v === 'x' ? W.accentInk : W.ink, transform: `translateY(${(1 - s) * -16}px)`}}>
                  {m.v}
                </div>
              );
            })}
          </div>
        );
      })}
      {ring > 0 ? (
        <svg width={LINEUP.w} height={LINEUP.h} style={{position: 'absolute', left: 0, top: 0, overflow: 'visible'}}>
          <ellipse cx={colX(culprit)} cy={LINEUP.top + 86} rx={20} ry={78} fill="none" stroke={W.accentInk} strokeWidth={2.6} strokeLinecap="round" strokeDasharray={`${ringLen} ${ringLen}`} strokeDashoffset={ringLen * (1 - ring) * 0.9} transform={`rotate(-4 ${colX(culprit)} ${LINEUP.top + 86})`} />
        </svg>
      ) : null}
      {ring > 0 ? (
        <div style={{position: 'absolute', left: colX(culprit) - 120, top: LINEUP.top - 78, width: 240, textAlign: 'center', fontFamily: UI, fontSize: 36, fontWeight: 760, letterSpacing: '-0.03em', color: W.accentInk, opacity: pct}}>
          <Counter f={f} from={38} to={98.3} f0={tRing} f1={tRing + ms(fps, 900)} decimals={1} suffix="%" />
        </div>
      ) : null}
      <div style={{position: 'absolute', left: 40, right: 40, bottom: 26, display: 'flex', gap: 26, fontFamily: UI, fontSize: 17, color: W.muted}}>
        <span><b style={{fontFamily: MONO, color: W.accentInk}}>x</b> a replay that failed</span>
        <span><b style={{fontFamily: MONO, color: W.ink}}>o</b> a replay that passed</span>
        <span style={{opacity: 0.7}}>grey: ordinary runs already traced</span>
        <span>hatched: has an alibi</span>
        <span><s>struck through</s>: cleared</span>
      </div>
    </div>
  );
};

/** The Entire checkpoint behind the culprit: the request, typed. Logical 1120×560. */
export const WdMotive: React.FC<P> = (p) => {
  const {f, fps} = p;
  const at = useAt(p);
  const type = at('type');
  const checked = at('checked');
  const request = 'victims/refund-agent: since we capped the loop at 3 model calls,\nsimple refunds feel slow, and most customers already tell us the\norder number and the amount. Please let the agent go straight to\nissue_refund when the customer has given both the order number\nand the amount, and only call lookup_order when something is missing.';
  const chip: React.CSSProperties = {display: 'inline-flex', alignItems: 'center', gap: 10, height: 44, padding: '0 18px 0 8px', borderRadius: 22, background: 'rgba(255,255,255,0.08)', fontSize: 19, fontWeight: 550};
  return (
    <div style={{width: 1120, height: 560, background: '#201B15', color: '#F3ECE1', fontFamily: UI, padding: 36, boxSizing: 'border-box', position: 'relative'}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 14, fontSize: 19, color: '#AEA290'}}>
        <span style={{fontFamily: MONO, fontSize: 15, letterSpacing: '0.1em', textTransform: 'uppercase', color: W.termHot}}>Entire checkpoint</span>
        <span style={{fontFamily: MONO}}>bfbe27725663</span>
        <span>on commit</span>
        <span style={{fontFamily: MONO, color: '#F3ECE1'}}>ced2ecd</span>
      </div>
      <div style={{marginTop: 12, fontSize: 30, fontWeight: 700, letterSpacing: '-0.02em'}}>Let the agent skip lookup_order when the customer gives order number and amount</div>
      <div style={{marginTop: 22, fontSize: 17, color: '#AEA290'}}>Someone asked the coding agent for this:</div>
      <div style={{marginTop: 10, padding: '20px 24px', borderRadius: 16, background: 'rgba(255,236,210,0.06)', fontFamily: MONO, fontSize: 19.5, lineHeight: 1.55, height: 176, boxSizing: 'border-box'}}>
        <TypeText f={f} at={type} cps={115} text={request} caretColor={W.termHot} />
      </div>
      <div style={{position: 'absolute', left: 36, bottom: 32, display: 'flex', gap: 14}}>
        <PopIn f={f} at={checked}>
          <div style={chip}><Check f={f} at={checked} size={28} bg={W.good} />quote checked against the transcript</div>
        </PopIn>
        <PopIn f={f} at={checked + ms(fps, 220)}>
          <div style={chip}><Check f={f} at={checked + ms(fps, 220)} size={28} bg={W.good} />entire why: 4 of 4 changed lines agree</div>
        </PopIn>
      </div>
    </div>
  );
};

/** Exhibit A and Exhibit B: the same request one commit apart. Logical 1240×520. */
export const WdExhibits: React.FC<P> = (p) => {
  const {f, fps} = p;
  const at = useAt(p);
  const t0 = at('show');
  const part = at('part');
  const sides = [
    {name: 'Exhibit A', what: 'the passing run', commit: '92122ad', steps: ['Asked: refund 30 dollars for order 2002', 'The model calls lookup_order', 'lookup_order returns owner cust_4', 'The model refuses: a different account']},
    {name: 'Exhibit B', what: 'the failing run', commit: 'ced2ecd', steps: ['Asked: refund 30 dollars for order 2002', 'The model calls issue_refund', 'issue_refund returns refunded 30', 'The model replies: refund on its way']},
  ];
  const lit = clamp01(tween(f, part, part + ms(fps, 320), 0, 1, EASE.premium));
  return (
    <div style={{width: 1240, height: 520, display: 'flex', gap: 24, fontFamily: UI, color: '#F3ECE1'}}>
      {sides.map((s, i) => (
        <div key={i} style={{flex: 1, background: '#201B15', borderRadius: 26, padding: 30, boxSizing: 'border-box', opacity: fade(f, t0 + i * ms(fps, 140), fps), transform: `translateY(${(1 - fade(f, t0 + i * ms(fps, 140), fps)) * 18}px)`}}>
          <div style={{fontSize: 16, fontWeight: 650, letterSpacing: '0.09em', textTransform: 'uppercase'}}>
            {s.name} <span style={{color: '#AEA290', fontWeight: 500}}>{s.what}</span>
          </div>
          <div style={{marginTop: 6, fontSize: 18, color: '#AEA290'}}>at commit <span style={{fontFamily: MONO}}>{s.commit}</span></div>
          <div style={{marginTop: 22, fontFamily: MONO, fontSize: 20}}>
            {s.steps.map((step, n) => {
              const o = fade(f, t0 + ms(fps, 300) + n * ms(fps, 150), fps, 240);
              const hot = n === 1;
              return (
                <div key={n} style={{display: 'flex', gap: 14, alignItems: 'center', height: 62, marginTop: 10, padding: '0 16px', borderRadius: 14, opacity: o, color: hot && lit > 0.5 ? W.termHot : '#F3ECE1', boxShadow: hot ? `inset 0 0 0 ${2.5 * lit}px ${W.accent}` : 'none', background: hot ? `rgba(214,107,56,${0.12 * lit})` : 'transparent'}}>
                  <span style={{color: '#8A7F70', width: 16}}>{n + 1}</span>
                  <span>{step}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
};

/** The two fix attempts on the headline case. Logical 1160×600. */
export const WdFix: React.FC<P> = (p) => {
  const {f, fps} = p;
  const at = useAt(p);
  const tries = [
    {label: 'Try 1, a patch', sha: 'b7f8fdf', v: at('v1'), h: at('h1'), out: at('out1'), kept: false, harm: '"Please refund order 1001 for customer cust_9."', before: 5, after: 8},
    {label: 'Try 2, a patch', sha: '7e8120e', v: at('v2'), h: at('h2'), out: at('kept'), kept: true, harm: '13 other requests replayed on the fix', before: 0, after: 0},
  ];
  return (
    <div style={{width: 1160, height: 480, background: W.card, fontFamily: UI, color: W.ink, padding: '30px 36px', boxSizing: 'border-box'}}>
      <div style={{fontSize: 16, fontWeight: 600, letterSpacing: '0.11em', textTransform: 'uppercase', color: W.muted}}>Fix</div>
      {tries.map((t, i) => {
        const show = fade(f, t.v - ms(fps, 200), fps);
        const dotsEnd = t.v + ms(fps, 1300);
        const verdict = fade(f, dotsEnd, fps, 220);
        const harm = fade(f, t.h, fps, 260);
        const bar = clamp01(tween(f, t.h + ms(fps, 200), t.h + ms(fps, 900), 0, 1, EASE.camera));
        return (
          <div key={i} style={{marginTop: i ? 22 : 16, padding: '22px 26px', borderRadius: 22, background: W.bg, boxShadow: `inset 0 0 0 1px ${W.line}`, opacity: show, transform: `translateY(${(1 - show) * 16}px)`, position: 'relative'}}>
            <div style={{display: 'flex', alignItems: 'baseline', gap: 14}}>
              <span style={{fontSize: 25, fontWeight: 700, letterSpacing: '-0.02em'}}>{t.label}</span>
              <span style={{fontFamily: MONO, fontSize: 18, color: W.muted}}>{t.sha}</span>
            </div>
            <div style={{marginTop: 14, display: 'flex', alignItems: 'center', gap: 18}}>
              <div style={{display: 'flex', gap: 5, fontFamily: MONO, fontSize: 19, fontWeight: 600}}>
                {Array.from({length: 30}, (_, n) => (
                  <span key={n} style={{opacity: f >= t.v + (n / 30) * (dotsEnd - t.v) ? 1 : 0.12}}>o</span>
                ))}
              </div>
              <span style={{fontSize: 21, fontWeight: 650, opacity: verdict}}>0 failures in 30 replays</span>
            </div>
            <div style={{marginTop: 16, display: 'flex', alignItems: 'center', gap: 16, opacity: harm, fontSize: 19, color: W.ink2}}>
              <span style={{fontFamily: MONO, fontSize: 14, letterSpacing: '0.08em', textTransform: 'uppercase', color: W.muted}}>do no harm</span>
              <span>{t.harm}</span>
              {t.kept ? (
                <span style={{fontWeight: 650}}>none went wrong more often</span>
              ) : (
                <span style={{display: 'inline-flex', alignItems: 'center', gap: 10, fontFamily: MONO}}>
                  <span style={{color: W.muted}}>{t.before} in 8</span>
                  <span style={{width: 90, height: 8, borderRadius: 4, background: W.line2, overflow: 'hidden', display: 'inline-block'}}>
                    <span style={{display: 'block', height: 8, width: 90 * (0.625 + 0.375 * bar), background: W.accent}} />
                  </span>
                  <b style={{color: W.accentInk}}>{bar > 0.9 ? '8 in 8' : '…'}</b>
                </span>
              )}
            </div>
            <PopIn f={f} at={t.out} style={{position: 'absolute', right: 24, top: 20}}>
              <div style={{display: 'inline-flex', alignItems: 'center', gap: 10, height: 44, padding: t.kept ? '0 18px 0 8px' : '0 18px', borderRadius: 22, fontSize: 19, fontWeight: 700, background: t.kept ? W.ink : 'transparent', color: t.kept ? W.bg : W.accentInk, boxShadow: t.kept ? 'none' : `inset 0 0 0 2px ${W.accentInk}`}}>
                {t.kept ? <Check f={f} at={t.out} size={28} bg={W.good} /> : null}
                {t.kept ? 'Kept' : 'Not kept'}
              </div>
            </PopIn>
          </div>
        );
      })}
    </div>
  );
};

/** The investigation's own trace in neatlogs, as its dashboard lists it. Logical 900×640. */
export const WdTrace: React.FC<P> = (p) => {
  const {f, fps} = p;
  const at = useAt(p);
  const t0 = at('rows');
  const rows: Array<[number, string, string]> = [
    [0, 'whodunit investigate', '10m 44.9s'],
    [1, 'lineup', '41.3s'],
    [2, 'lineup round 1', '17.3s'],
    [2, 'lineup round 2', '5.7s'],
    [2, 'lineup round 3', '5.1s'],
    [2, 'lineup round 4', '5.5s'],
    [1, 'motive', '1.2s'],
    [1, 'brief', '7.6s'],
    [1, 'ruling', '20ms'],
    [1, 'fix attempt 1, a patch', '4m 58.0s'],
    [2, 'do no harm', '3m 48.8s'],
    [1, 'fix attempt 2, a patch', '4m 55.6s'],
    [1, 'damages', '541ms'],
  ];
  return (
    <div style={{width: 900, height: 640, background: W.card, fontFamily: UI, color: W.ink, padding: '28px 32px', boxSizing: 'border-box'}}>
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline'}}>
        <span style={{fontSize: 16, fontWeight: 600, letterSpacing: '0.11em', textTransform: 'uppercase', color: W.muted}}>neatlogs · trace b842b67d</span>
        <span style={{fontFamily: MONO, fontSize: 16, color: W.muted}}>17 steps</span>
      </div>
      <div style={{marginTop: 14}}>
        {rows.map(([depth, name, time], i) => {
          const o = fade(f, t0 + i * ms(fps, 85), fps, 220);
          return (
            <div key={i} style={{display: 'flex', alignItems: 'center', height: 41, borderTop: i ? `1px solid ${W.line}` : 'none', opacity: o, transform: `translateX(${(1 - o) * -10}px)`}}>
              <span style={{width: depth * 30}} />
              <span style={{width: 9, height: 9, borderRadius: 5, background: depth === 0 ? W.accent : W.line2, marginRight: 14}} />
              <span style={{fontSize: 20, fontWeight: depth === 0 ? 700 : 500}}>{name}</span>
              <span style={{marginLeft: 12, fontFamily: MONO, fontSize: 12.5, letterSpacing: '0.08em', color: W.faint}}>{depth === 0 ? 'WORKFLOW' : 'CHAIN'}</span>
              <span style={{marginLeft: 'auto', fontFamily: MONO, fontSize: 18, color: W.muted}}>{time}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** What the regression cost, read from the traces. Logical 640×640. */
export const WdDamage: React.FC<P> = (p) => {
  const {f, fps} = p;
  const at = useAt(p);
  const t = at('dmg');
  return (
    <div style={{width: 640, height: 640, background: W.card, fontFamily: UI, color: W.ink, padding: '34px 38px', boxSizing: 'border-box'}}>
      <div style={{fontSize: 16, fontWeight: 600, letterSpacing: '0.11em', textTransform: 'uppercase', color: W.muted}}>Damages</div>
      <div style={{marginTop: 26, fontSize: 108, fontWeight: 770, letterSpacing: '-0.045em', lineHeight: 1, opacity: fade(f, t, fps)}}>
        <Counter f={f} from={0} to={120} f0={t} f1={t + ms(fps, 1000)} decimals={2} />
      </div>
      <div style={{marginTop: 12, fontSize: 30, fontWeight: 650, letterSpacing: '-0.02em', opacity: fade(f, t + ms(fps, 300), fps)}}>refunded to the wrong people</div>
      <div style={{marginTop: 28, fontSize: 21, lineHeight: 1.5, color: W.ink2, opacity: fade(f, t + ms(fps, 700), fps)}}>4 of the 6 scripted requests that asked this, on the culprit or later, failed the check.</div>
      <div style={{marginTop: 26, paddingTop: 22, borderTop: `1px solid ${W.line}`, display: 'flex', gap: 34, opacity: fade(f, t + ms(fps, 1300), fps)}}>
        <div><div style={{fontFamily: MONO, fontSize: 34, fontWeight: 500}}>176</div><div style={{fontSize: 17, color: W.muted}}>replays in all</div></div>
        <div><div style={{fontFamily: MONO, fontSize: 34, fontWeight: 500}}>$0.80</div><div style={{fontSize: 17, color: W.muted}}>for the whole investigation</div></div>
      </div>
    </div>
  );
};

const CASES = [
  {no: '001', title: 'Refunds off by cents', sha: '367c64a', replays: 21, closed: true},
  {no: '002', title: 'Two-order requests left half done', sha: 'c545753', replays: 168, closed: false},
  {no: '003', title: 'Refunds to strangers', sha: 'ced2ecd', replays: 30, closed: true},
  {no: '004', title: 'Shipped orders turned away', sha: 'ca0a2d6', replays: 24, closed: true},
  {no: '005', title: 'The wrong order refunded', sha: 'd4fb158', replays: 168, closed: true},
  {no: '006', title: 'Strangers again, across 57 commits', sha: 'ced2ecd', replays: 20, closed: true},
];

/** One row of the docket as a card. Logical 620×300. */
export const WdCase: React.FC<P & {variant?: number}> = ({variant = 0}) => {
  const c = CASES[variant % CASES.length];
  return (
    <div style={{width: 620, height: 300, background: W.card, fontFamily: UI, color: W.ink, padding: '28px 32px', boxSizing: 'border-box', position: 'relative'}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
        <span style={{fontFamily: MONO, fontSize: 20, color: W.muted}}>{c.no}</span>
        <span style={{display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 14px', borderRadius: 17, fontSize: 16, fontWeight: 650, background: c.closed ? W.ink : 'transparent', color: c.closed ? W.bg : W.ink, boxShadow: c.closed ? 'none' : `inset 0 0 0 1.5px ${W.ink}`}}>{c.closed ? 'Case closed' : 'Open, not fixed'}</span>
      </div>
      <div style={{marginTop: 20, fontSize: 34, fontWeight: 720, letterSpacing: '-0.03em', lineHeight: 1.12}}>{c.title}</div>
      <div style={{position: 'absolute', left: 32, right: 32, bottom: 26, display: 'flex', justifyContent: 'space-between', fontSize: 19, color: W.muted}}>
        <span>culprit <span style={{fontFamily: MONO, color: W.accentInk}}>{c.sha}</span></span>
        <span><span style={{fontFamily: MONO, color: W.ink}}>{c.replays}</span> replays to name</span>
      </div>
    </div>
  );
};

/** The sealed eval's result as a strip. Logical 1400×210. */
export const WdStats: React.FC<P & {at?: At}> = ({f, ev, b, fps, at = 0}) => {
  const t0 = typeof at === 'string' ? ev(at) : b(at);
  const items: Array<[number, string, string]> = [
    [5, ' of 5', 'culprits named'],
    [0, '', 'wrongly accused'],
    [4, ' of 5', 'fixed and kept'],
    [1, '', 'still open, and shown'],
  ];
  return (
    <div style={{width: 1400, height: 210, display: 'flex', alignItems: 'center', fontFamily: UI, color: W.ink, background: W.card}}>
      {items.map(([v, suf, lab], i) => {
        const s = t0 + ms(fps, 110) * i;
        const o = fade(f, s, fps, 380);
        return (
          <div key={i} style={{flex: 1, textAlign: 'center', borderLeft: i ? `1px solid ${W.line}` : undefined, opacity: o, transform: `translateY(${(1 - o) * 14}px)`}}>
            <div style={{fontSize: 64, fontWeight: 760, letterSpacing: '-0.04em', color: i === 3 ? W.accentInk : W.ink}}>
              <Counter f={f} from={0} to={v} f0={s} f1={s + ms(fps, 700)} suffix={suf} />
            </div>
            <div style={{fontSize: 21, color: W.muted, marginTop: 2}}>{lab}</div>
          </div>
        );
      })}
    </div>
  );
};

// Cash at the end of each month, October 2026 to September 2027, as the cfo.ai model gives it.
const CASH = {
  base: [14300, 13600, 12900, 12730, 13151, 14163, 13156, 13191, 14146, 16143, 19121, 23141],
  up: [14300, 13600, 12900, 13247, 14703, 17266, 19413, 24265, 31762, 41902, 54687, 70178],
  down: [14300, 13600, 12900, 12287, 11821, 11504, 8334, 5311, 2437, -290, -2869, -5300],
  nodraw: [14300, 13600, 12900, 12287, 11821, 11504, 11334, 11311, 11437, 11710, 12131, 12700],
};

/** The plan in cfo.ai: cash by case, and the founder draw slider. Logical 1240×660. */
export const WdPlan: React.FC<P> = (p) => {
  const {f, fps} = p;
  const at = useAt(p);
  const draw = at('draw');
  const slide = at('slide');
  const k = clamp01(tween(f, slide, slide + ms(fps, 1100), 0, 1, EASE.move)); // 0 = $3,000 a month, 1 = $0
  const cw = 760;
  const ch = 400;
  const lo = -8000;
  const hi = 72000;
  const X = (i: number) => (i / 11) * cw;
  const Y = (v: number) => ch - ((v - lo) / (hi - lo)) * ch;
  const path = (vals: number[]) => vals.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join(' ');
  const down = CASH.down.map((v, i) => v + (CASH.nodraw[i] - v) * k);
  const lines: Array<[string, number[], string, number]> = [
    ['Upside', CASH.up, W.faint, 0],
    ['Base', CASH.base, W.ink, 1],
    ['Downside', down, W.accentInk, 2],
  ];
  const len = 1400;
  const end = down[11];
  const months = ['Oct', 'Dec', 'Feb', 'Apr', 'Jun', 'Aug'];
  return (
    <div style={{width: 1240, height: 660, background: W.card, fontFamily: UI, color: W.ink, padding: '30px 36px', boxSizing: 'border-box', position: 'relative'}}>
      <div style={{display: 'flex', alignItems: 'baseline', gap: 14}}>
        <span style={{fontSize: 16, fontWeight: 600, letterSpacing: '0.11em', textTransform: 'uppercase', color: W.muted}}>cfo.ai · Cash and runway</span>
      </div>
      <div style={{marginTop: 6, fontSize: 30, fontWeight: 720, letterSpacing: '-0.025em'}}>Cash at the end of each month, by case</div>
      <svg width={cw} height={ch + 40} style={{position: 'absolute', left: 60, top: 150, overflow: 'visible'}}>
        {[0, 20000, 40000, 60000].map((v) => (
          <g key={v}>
            <line x1={0} x2={cw} y1={Y(v)} y2={Y(v)} stroke={v === 0 ? W.line2 : W.line} strokeWidth={v === 0 ? 1.5 : 1} />
            <text x={-12} y={Y(v) + 5} textAnchor="end" fontFamily={MONO} fontSize={14} fill={W.muted}>{v === 0 ? '0' : `${v / 1000}K`}</text>
          </g>
        ))}
        {months.map((m, i) => (
          <text key={m} x={X(i * 2)} y={ch + 30} textAnchor="middle" fontFamily={MONO} fontSize={14} fill={W.muted}>{m}</text>
        ))}
        {lines.map(([name, vals, color, i]) => {
          const t = draw + i * ms(fps, 220);
          const prog = clamp01(tween(f, t, t + ms(fps, 1300), 0, 1, EASE.camera));
          return <path key={name} d={path(vals)} fill="none" stroke={color} strokeWidth={i === 2 ? 4 : 3} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={`${len} ${len}`} strokeDashoffset={len * (1 - prog)} />;
        })}
      </svg>
      <div style={{position: 'absolute', left: 870, top: 150, width: 334}}>
        <div style={{fontSize: 18, color: W.muted}}>Founder draw, a month</div>
        <div style={{fontFamily: MONO, fontSize: 40, fontWeight: 500, marginTop: 4}}>${Math.round((3000 * (1 - k)) / 250) * 250 === 0 ? '0' : (Math.round((3000 * (1 - k)) / 250) * 250).toLocaleString('en-US')}</div>
        <div style={{position: 'relative', height: 30, marginTop: 14}}>
          <div style={{position: 'absolute', left: 0, right: 0, top: 12, height: 6, borderRadius: 3, background: W.line2}} />
          <div style={{position: 'absolute', left: 0, top: 12, height: 6, borderRadius: 3, background: W.ink, width: 334 * 0.5 * (1 - k)}} />
          <div style={{position: 'absolute', top: 2, left: 334 * 0.5 * (1 - k) - 13, width: 26, height: 26, borderRadius: 13, background: '#fff', boxShadow: `0 0 0 1.5px ${W.line2}, 0 3px 8px rgba(23,16,14,0.18)`}} />
        </div>
        <div style={{marginTop: 34, fontSize: 18, color: W.muted}}>Downside, cash after month 12</div>
        <div style={{fontFamily: MONO, fontSize: 40, fontWeight: 500, marginTop: 4, color: end < 0 ? W.accentInk : W.ink}}>{end < 0 ? '-$' : '$'}{Math.abs(Math.round(end)).toLocaleString('en-US')}</div>
        <div style={{marginTop: 26, fontSize: 18, color: W.muted}}>Downside, cash runs out</div>
        <div style={{fontSize: 32, fontWeight: 700, letterSpacing: '-0.02em', marginTop: 4}}>{down.some((v) => v < 0) ? 'July 2027' : 'Not this year'}</div>
        <div style={{marginTop: 34, display: 'flex', flexDirection: 'column', gap: 9, fontSize: 17, color: W.ink2}}>
          {lines.map(([name, , color]) => (
            <span key={name} style={{display: 'flex', alignItems: 'center', gap: 10}}><i style={{width: 22, height: 4, borderRadius: 2, background: color}} />{name}</span>
          ))}
        </div>
      </div>
    </div>
  );
};

/** Before and after the kept fix, on the same request. Logical 1400×460. */
export const WdBeforeAfter: React.FC<P> = (p) => {
  const {f, fps} = p;
  const at = useAt(p);
  const sides = [
    {t: at('before'), label: 'Before the fix', big: '11 of 14', line: 'runs went wrong, from the culprit on', small: '7 of 8 replays and 4 of 6 ordinary runs', hot: true},
    {t: at('after'), label: 'After the fix', big: '0 of 30', line: 'replays failed', small: 'at most 6.2% at 95%, from these replays alone', hot: false},
  ];
  const arrow = fade(f, sides[1].t - ms(fps, 200), fps, 300);
  return (
    <div style={{width: 1400, height: 460, display: 'flex', alignItems: 'stretch', gap: 28, fontFamily: UI, color: W.ink, position: 'relative'}}>
      {sides.map((s, i) => {
        const o = fade(f, s.t, fps, 320);
        const pop = sp(f, s.t, fps, 0.7, 2.4);
        return (
          <div key={i} style={{flex: 1, background: W.card, borderRadius: 30, boxShadow: `inset 0 0 0 1px ${W.line}, 0 30px 70px -30px rgba(23,16,14,0.28)`, padding: '40px 46px', boxSizing: 'border-box', opacity: o, transform: `translateY(${(1 - pop) * 22}px)`}}>
            <div style={{fontSize: 18, fontWeight: 600, letterSpacing: '0.11em', textTransform: 'uppercase', color: W.muted}}>{s.label}</div>
            <div style={{marginTop: 26, fontSize: 132, fontWeight: 780, letterSpacing: '-0.05em', lineHeight: 1, color: s.hot ? W.accentInk : W.ink}}>{s.big}</div>
            <div style={{marginTop: 16, fontSize: 32, fontWeight: 650, letterSpacing: '-0.02em'}}>{s.line}</div>
            <div style={{marginTop: 18, fontFamily: MONO, fontSize: 19, color: W.muted}}>{s.small}</div>
          </div>
        );
      })}
      <div style={{position: 'absolute', left: 700 - 34, top: 230 - 34, width: 68, height: 68, borderRadius: 34, background: W.ink, color: W.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 34, fontWeight: 600, opacity: arrow, transform: `scale(${0.7 + 0.3 * arrow})`}}>→</div>
    </div>
  );
};

/** What each of the three tools does in the product. Logical 1620×520. */
export const WdTools: React.FC<P> = (p) => {
  const {f, fps} = p;
  const at = useAt(p);
  const tools = [
    {t: at('t1'), name: 'neatlogs', job: 'The evidence', lines: ['240 runs traced in the dashboard', '18 counted before any replay', 'Damages read from the traces', 'The investigation is a trace too']},
    {t: at('t2'), name: 'Entire', job: 'The motive', lines: ['A checkpoint behind the culprit', 'The request, word for word', 'entire why checks each changed line', 'The code graph gives alibis']},
    {t: at('t3'), name: 'cfo.ai', job: 'The plan', lines: ['Pricing, costs, revenue, runway', 'Four cases, side by side', 'Unit cost from six real investigations', 'A simulator for the big levers']},
  ];
  return (
    <div style={{width: 1620, height: 520, display: 'flex', gap: 26, fontFamily: UI, color: W.ink}}>
      {tools.map((tool, i) => {
        const o = fade(f, tool.t, fps, 300);
        const pop = sp(f, tool.t, fps, 0.68, 2.5);
        return (
          <div key={i} style={{flex: 1, background: W.card, borderRadius: 30, boxShadow: `inset 0 0 0 1px ${W.line}, 0 30px 70px -30px rgba(23,16,14,0.28)`, padding: '38px 40px', boxSizing: 'border-box', opacity: o, transform: `translateY(${(1 - pop) * 26}px) scale(${0.94 + 0.06 * pop})`}}>
            <div style={{fontFamily: MONO, fontSize: 17, letterSpacing: '0.1em', textTransform: 'uppercase', color: W.accentInk}}>{tool.job}</div>
            <div style={{marginTop: 10, fontSize: 62, fontWeight: 770, letterSpacing: '-0.04em', lineHeight: 1.05}}>{tool.name}</div>
            <div style={{marginTop: 26, borderTop: `1px solid ${W.line}`}}>
              {tool.lines.map((line, n) => {
                const lo = fade(f, tool.t + ms(fps, 260) + n * ms(fps, 120), fps, 260);
                return (
                  <div key={n} style={{display: 'flex', alignItems: 'center', gap: 14, height: 62, borderBottom: `1px solid ${W.line}`, fontSize: 23, color: W.ink2, opacity: lo, transform: `translateX(${(1 - lo) * -10}px)`}}>
                    <span style={{width: 8, height: 8, borderRadius: 4, background: W.accent, flex: 'none'}} />
                    {line}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const SCREENS_WHODUNIT: Record<string, React.FC<any>> = {WdMark, WdLog, WdChat, WdTerminal, WdLineup, WdMotive, WdExhibits, WdFix, WdTrace, WdDamage, WdCase, WdStats, WdPlan, WdBeforeAfter, WdTools};
