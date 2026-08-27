import type { ReactElement } from 'react'

/**
 * The five roles, each as a small isometric object.
 *
 * These are rendered rather than illustrated: every face carries its own gradient, the
 * top faces catch the light from the upper left, the side faces fall away, and each object
 * sits on a soft contact shadow. That is what makes them read as objects rather than icons
 * at 40px, and it is why they are SVG rather than PNG — they stay crisp on a 4K projector
 * and they take the accent colour of the role.
 */

type Tone = {
  lit: string      // top face, catching the light
  mid: string      // front face
  dark: string     // side face, falling away
  deep: string     // the deepest crease
  glow: string     // the ground bloom
}

const TONES: Record<string, Tone> = {
  teal:  { lit: '#5eead4', mid: '#14b8a6', dark: '#0d9488', deep: '#0f766e', glow: '#99f6e4' },
  blue:  { lit: '#93c5fd', mid: '#3b82f6', dark: '#2563eb', deep: '#1d4ed8', glow: '#bfdbfe' },
  amber: { lit: '#fcd34d', mid: '#f59e0b', dark: '#d97706', deep: '#b45309', glow: '#fde68a' },
  rose:  { lit: '#fda4af', mid: '#f43f5e', dark: '#e11d48', deep: '#be123c', glow: '#fecdd3' },
  slate: { lit: '#cbd5e1', mid: '#64748b', dark: '#475569', deep: '#334155', glow: '#e2e8f0' },
}

function toneOf(accent: string): Tone {
  return TONES[accent] ?? TONES.blue
}

/** Gradients are per-instance so two avatars on one page cannot share an id. */
function Defs({ id, tone }: { id: string; tone: Tone }) {
  return (
    <defs>
      <linearGradient id={`${id}-top`} x1="0" y1="0" x2="0.7" y2="1">
        <stop offset="0" stopColor="#ffffff" stopOpacity="0.92" />
        <stop offset="0.45" stopColor={tone.lit} />
        <stop offset="1" stopColor={tone.mid} />
      </linearGradient>
      <linearGradient id={`${id}-front`} x1="0" y1="0" x2="0.2" y2="1">
        <stop offset="0" stopColor={tone.mid} />
        <stop offset="1" stopColor={tone.dark} />
      </linearGradient>
      <linearGradient id={`${id}-side`} x1="0" y1="0" x2="1" y2="0.8">
        <stop offset="0" stopColor={tone.dark} />
        <stop offset="1" stopColor={tone.deep} />
      </linearGradient>
      <linearGradient id={`${id}-glass`} x1="0" y1="0" x2="0.8" y2="1">
        <stop offset="0" stopColor="#ffffff" stopOpacity="0.85" />
        <stop offset="0.55" stopColor="#ffffff" stopOpacity="0.24" />
        <stop offset="1" stopColor="#ffffff" stopOpacity="0.55" />
      </linearGradient>
      <radialGradient id={`${id}-bloom`} cx="0.5" cy="0.5" r="0.5">
        <stop offset="0" stopColor={tone.glow} stopOpacity="0.85" />
        <stop offset="1" stopColor={tone.glow} stopOpacity="0" />
      </radialGradient>
      <radialGradient id={`${id}-shadow`} cx="0.5" cy="0.5" r="0.5">
        <stop offset="0" stopColor="#0f172a" stopOpacity="0.28" />
        <stop offset="0.7" stopColor="#0f172a" stopOpacity="0.08" />
        <stop offset="1" stopColor="#0f172a" stopOpacity="0" />
      </radialGradient>
    </defs>
  )
}

/** The soft pool of light and the contact shadow every object sits in. */
function Ground({ id }: { id: string }) {
  return (
    <>
      <ellipse cx="48" cy="52" rx="40" ry="30" fill={`url(#${id}-bloom)`} opacity="0.55" />
      <ellipse cx="48" cy="76" rx="25" ry="7" fill={`url(#${id}-shadow)`} />
    </>
  )
}

// ── Policy Holder: their car, three-quarter view ───────────────────────
function Holder({ id, tone }: { id: string; tone: Tone }) {
  return (
    <>
      {/* body — the lower mass, catching light along the shoulder line */}
      <path d="M20 62c-3 0-5-2-5-5v-6c0-3 2-5 5-6l6-1 6-11c1-3 4-4 7-4h16c3 0 6 1 7 4l6 11 6 1c3 1 5 3 5 6v6c0 3-2 5-5 5z"
            fill={`url(#${id}-front)`} />
      {/* roof and glasshouse */}
      <path d="M32 44l5-9c1-2 2-3 5-3h12c3 0 4 1 5 3l5 9z" fill={`url(#${id}-top)`} />
      <path d="M35 43l4-7c0-1 1-1 2-1h14c1 0 2 0 2 1l4 7z" fill={`url(#${id}-glass)`} />
      {/* the shoulder highlight — this is what makes the flank look curved */}
      <path d="M17 51c4-2 12-3 31-3s27 1 31 3" stroke="#ffffff" strokeOpacity="0.4"
            strokeWidth="1.6" fill="none" strokeLinecap="round" />
      {/* wheels, with a lit rim so they sit under the arch rather than on it */}
      <g>
        <ellipse cx="30" cy="63" rx="7" ry="7" fill={tone.deep} />
        <ellipse cx="30" cy="63" rx="3.2" ry="3.2" fill={tone.lit} opacity="0.9" />
        <ellipse cx="66" cy="63" rx="7" ry="7" fill={tone.deep} />
        <ellipse cx="66" cy="63" rx="3.2" ry="3.2" fill={tone.lit} opacity="0.9" />
      </g>
      {/* headlamp */}
      <ellipse cx="79" cy="53" rx="3" ry="2.2" fill="#fffbeb" opacity="0.95" />
    </>
  )
}

// ── Claim Handler: the file, open on the desk ──────────────────────────
function Handler({ id, tone }: { id: string; tone: Tone }) {
  return (
    <>
      {/* the folder underneath, extruded so the stack has depth */}
      <path d="M18 40h26l5 6h29v28a4 4 0 0 1-4 4H22a4 4 0 0 1-4-4z"
            fill={`url(#${id}-side)`} />
      {/* the paper, lifted and tilted — the lit face */}
      <path d="M26 30h30l8 8v30H26z" fill="#ffffff" />
      <path d="M56 30l8 8h-8z" fill={tone.glow} />
      {/* the lines of the file, weighted so the eye reads "a document" not "a rectangle" */}
      <g stroke={tone.dark} strokeWidth="2.2" strokeLinecap="round" opacity="0.55">
        <path d="M32 42h16M32 49h22M32 56h22M32 63h13" />
      </g>
      {/* the front flap of the folder, over the paper */}
      <path d="M18 46h63v24a4 4 0 0 1-4 4H22a4 4 0 0 1-4-4z" fill={`url(#${id}-front)`} />
      <path d="M18 46h63v5H18z" fill={`url(#${id}-top)`} opacity="0.85" />
      {/* the tab, so the folder reads as a filed claim */}
      <path d="M44 40h12v6H44z" fill={`url(#${id}-top)`} />
    </>
  )
}

// ── Motor Assessor: the toolbox ───────────────────────────────────────
function Assessor({ id, tone }: { id: string; tone: Tone }) {
  return (
    <>
      {/* the handle arch, behind the lid so the lid overlaps it */}
      <path d="M36 34v-4a12 12 0 0 1 24 0v4" fill="none" stroke={tone.deep}
            strokeWidth="6" strokeLinecap="round" />
      <path d="M36 34v-4a12 12 0 0 1 24 0v4" fill="none" stroke={tone.lit}
            strokeWidth="2" strokeLinecap="round" opacity="0.8" />

      {/* the lid: a lit top face and a front lip, which is what gives it thickness */}
      <path d="M16 40a4 4 0 0 1 4-4h56a4 4 0 0 1 4 4v6H16z" fill={`url(#${id}-top)`} />
      <path d="M16 46h64v6H16z" fill={`url(#${id}-front)`} />
      <path d="M16 40a4 4 0 0 1 4-4h56a4 4 0 0 1 4 4v2H16z" fill="#ffffff" opacity="0.32" />

      {/* the body */}
      <path d="M18 52h60v18a5 5 0 0 1-5 5H23a5 5 0 0 1-5-5z" fill={`url(#${id}-front)`} />
      {/* the shaded right flank, so it turns away from the light */}
      <path d="M62 52h16v18a5 5 0 0 1-5 5h-11z" fill={`url(#${id}-side)`} opacity="0.85" />
      {/* the latch */}
      <path d="M43 48h10v9a2 2 0 0 1-2 2h-6a2 2 0 0 1-2-2z" fill={tone.deep} />
      <path d="M45 50h6v4h-6z" fill="#ffffff" opacity="0.85" />
      {/* a hint of the tools inside, showing over the lid line */}
      <path d="M28 58h12M28 64h8" stroke="#ffffff" strokeOpacity="0.42" strokeWidth="2.4"
            strokeLinecap="round" />
    </>
  )
}


// ── Special Investigations: the lens over the network ──────────────────
function Siu({ id, tone }: { id: string; tone: Tone }) {
  return (
    <>
      {/* the graph on the ground: parties, vehicles, a repairer */}
      <g stroke={tone.dark} strokeWidth="2" opacity="0.5" strokeLinecap="round">
        <path d="M28 64 46 52M46 52 68 60M28 64 40 74M68 60 60 74M46 52 44 34" />
      </g>
      <g>
        <circle cx="28" cy="64" r="5" fill={`url(#${id}-front)`} />
        <circle cx="68" cy="60" r="5" fill={`url(#${id}-front)`} />
        <circle cx="40" cy="74" r="4" fill={`url(#${id}-side)`} />
        <circle cx="60" cy="74" r="4" fill={`url(#${id}-side)`} />
        <circle cx="44" cy="34" r="4" fill={`url(#${id}-side)`} />
        {/* the node under the lens is the one that matters, so it is lit */}
        <circle cx="46" cy="52" r="7" fill={`url(#${id}-top)`} />
      </g>
      {/* the lens itself, with a real rim and a glass highlight */}
      <g>
        <circle cx="46" cy="50" r="20" fill={`url(#${id}-glass)`} opacity="0.55" />
        <circle cx="46" cy="50" r="20" fill="none" stroke={tone.deep} strokeWidth="5" />
        <circle cx="46" cy="50" r="20" fill="none" stroke={tone.lit} strokeWidth="1.6"
                opacity="0.85" />
        <path d="M34 40a17 17 0 0 1 12-6" stroke="#ffffff" strokeOpacity="0.8"
              strokeWidth="3" fill="none" strokeLinecap="round" />
        {/* the handle, extruded so it has a top and a side */}
        <path d="M60 64l14 14a4 4 0 0 1-6 6L54 70z" fill={`url(#${id}-front)`} />
        <path d="M60 64l14 14a4 4 0 0 1-1 1L58 66z" fill={`url(#${id}-top)`} />
      </g>
    </>
  )
}

// ── Compliance & Operations: the shield on its plinth ──────────────────
function Compliance({ id, tone }: { id: string; tone: Tone }) {
  return (
    <>
      {/* the plinth — this is the "operations" half: it holds things up */}
      <path d="M24 68h48l4 8H20z" fill={`url(#${id}-side)`} />
      <path d="M28 62h40l4 6H24z" fill={`url(#${id}-front)`} />
      {/* the shield, standing on it */}
      <path d="M48 16l24 8v18c0 14-10 23-24 27-14-4-24-13-24-27V24z"
            fill={`url(#${id}-front)`} />
      {/* the lit half — a shield split down the light axis reads as curved metal */}
      <path d="M48 16v53c-14-4-24-13-24-27V24z" fill={`url(#${id}-top)`} opacity="0.55" />
      <path d="M48 16l24 8v18c0 14-10 23-24 27" fill="none" stroke={tone.lit}
            strokeWidth="1.6" opacity="0.7" />
      {/* the inner field, so the tick sits on something */}
      <path d="M48 24l17 6v13c0 10-7 16-17 19-10-3-17-9-17-19V30z"
            fill="#ffffff" opacity="0.16" />
      {/* the tick */}
      <path d="M39 43l7 8 13-15" stroke="#ffffff" strokeWidth="5" fill="none"
            strokeLinecap="round" strokeLinejoin="round" />
      <path d="M39 43l7 8 13-15" stroke={tone.lit} strokeWidth="1.8" fill="none"
            strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
    </>
  )
}

const SCENES: Record<string, (p: { id: string; tone: Tone }) => ReactElement> = {
  holder: Holder,
  handler: Handler,
  assessor: Assessor,
  siu: Siu,
  compliance: Compliance,
}

export function Avatar3D({
  avatar,
  accent = 'blue',
  size = 40,
  className = '',
}: {
  avatar: string
  accent?: string
  size?: number
  className?: string
}) {
  const tone = toneOf(accent)
  const Scene = SCENES[avatar] ?? Handler
  // Deterministic per avatar+accent, so the same role always renders the same ids and
  // React never has to re-key the gradients.
  const id = `av-${avatar}-${accent}`
  return (
    <svg
      viewBox="0 0 96 96"
      width={size}
      height={size}
      className={`shrink-0 ${className}`}
      role="img"
      aria-hidden
    >
      <Defs id={id} tone={tone} />
      <Ground id={id} />
      <Scene id={id} tone={tone} />
    </svg>
  )
}

/** The same object, framed in a soft tile — for the role switcher and headers. */
export function AvatarTile({
  avatar,
  accent = 'blue',
  size = 44,
  ring = false,
}: {
  avatar: string
  accent?: string
  size?: number
  ring?: boolean
}) {
  const tone = toneOf(accent)
  return (
    <span
      className={`inline-flex items-center justify-center rounded-2xl shrink-0 ${
        ring ? 'ring-2 ring-offset-1' : ''
      }`}
      style={{
        width: size,
        height: size,
        background: `linear-gradient(145deg, ${tone.glow}55, ${tone.glow}18)`,
        ...(ring ? ({ '--tw-ring-color': tone.mid } as Record<string, string>) : {}),
      }}
    >
      <Avatar3D avatar={avatar} accent={accent} size={Math.round(size * 0.82)} />
    </span>
  )
}
