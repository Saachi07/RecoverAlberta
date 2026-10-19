import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import DemoDropzone from "../components/DemoDropzone";
import { useAuth } from "../auth/AuthContext";

// The landing page leads with a hero and an unmissable Immediate Help block for
// anyone arriving mid-crisis, then shows the product through framed mockups
// instead of long paragraphs. Copy is kept short on purpose: a stressed reader
// should be able to scan it, not study it.

// Three product pillars, each shown with a real screenshot mockup. Detail lives
// on the inner pages, so each pillar links out rather than explaining in full.
// Image paths are prefixed with BASE_URL so they resolve under the GitHub Pages
// subpath (/Rebuildr/) as well as at the local-dev root (/).
const BASE = import.meta.env.BASE_URL;
const PILLARS = [
  {
    title: "List what you lost",
    body: "Photograph a room and our AI drafts an inventory with estimated values. You review and edit it before anything is saved.",
    // Drop a screenshot of the inventory scan result here (PNG, ~390px wide).
    img: `${BASE}landing/mockup-inventory.png`,
    alt: "Rebuildr inventory: a scanned room with itemized values",
  },
  {
    title: "Read your insurance, for you",
    body: "Upload your policy and we draft a plain-language summary of coverage, deductibles, and deadlines. Always confirm the details with your insurer.",
    // Drop a screenshot of the document analysis summary here.
    img: `${BASE}landing/mockup-policy.png`,
    alt: "Rebuildr policy analysis: plain-language summary with deadlines",
  },
  {
    title: "A plan, one step at a time",
    body: "Everything becomes a clear set of next steps, with the dates that matter.",
    // Drop a screenshot of the recommendations / plan view here.
    img: `${BASE}landing/mockup-plan.png`,
    alt: "Rebuildr recovery plan: prioritized next steps",
  },
];

// Rebuildr is calibrated to Alberta's programs and deadlines for now (the
// Disaster Recovery Program, provincial relief, regional municipalities). A
// quiet regional anchor near the top tells a local visitor the guidance is
// built for where they are, not generic.
const ALBERTA_REGIONS = [
  "Edmonton",
  "Calgary",
  "Fort McMurray",
  "Red Deer",
  "Lethbridge",
  "Regional municipalities",
];

// The provincial programs Rebuildr is built around. Plain reference info, kept
// honest (no invented "live" figures), so a local visitor sees the platform
// speaks their jurisdiction's language.
const ALBERTA_DESK = [
  {
    title: "Disaster Recovery Program",
    detail: "Provincial help for uninsurable losses. We track its deadlines and what it asks for.",
  },
  {
    title: "211 Alberta",
    detail: "Free, 24/7 line for shelter, food, and crisis support across the province.",
  },
  {
    title: "Alberta Emergency Alert",
    detail: "Official wildfire, flood, and evacuation notices for your area.",
  },
];

// The primary call to action. Rather than linking straight into a guarded
// route (which silently bounces a visitor whose session hasn't been
// established yet), it makes sure there is a session first, then navigates.
// That way the button always does something visible, and surfaces an error if
// a session genuinely can't be created instead of looping back to the landing
// page.
function StartButton() {
  const { ensureSession } = useAuth();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Land on the phase-aware home, not straight into a recovery case. A visitor
  // before any disaster gets the welcome (prepare vs recovery), someone already
  // preparing gets the prepare hub, and someone mid-recovery gets their
  // dashboard. Forcing everyone into "Tell us what happened" wrongly assumed a
  // disaster had occurred and gave preparers no way in.
  const start = "/home";
  return (
    <div>
      <button
        className="big"
        disabled={busy}
        onClick={async () => {
          setErr(null);
          setBusy(true);
          try {
            const ok = await ensureSession();
            if (ok) {
              nav(start);
            } else {
              setErr("We couldn't get things started just now. Please try again in a moment.");
            }
          } catch {
            setErr("We couldn't get things started just now. Please try again in a moment.");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Getting things ready…" : "Start when you're ready"}
      </button>
      {err && <p className="error" style={{ marginTop: 10 }}>{err}</p>}
    </div>
  );
}

export default function Landing() {
  return (
    <div className="container">
      <div className="hero">
        <img className="hero-logo" src={`${BASE}brand/logo.png`} alt="Rebuildr" />
        <h1>You're not doing this alone.</h1>
        <p className="warm">
          Rebuildr helps you document what you lost, understand your insurance,
          and turn it into a clear recovery plan.
        </p>
        <div className="cta-row">
          <StartButton />
        </div>
      </div>

      {/* #15: Immediate Help is the single most prominent block, sized and
          colored so a person in crisis cannot miss it. */}
      <section className="immediate-help" aria-label="Immediate help">
        <div>
          <h2>Need help right now?</h2>
          <p>
            If you or someone near you is in danger, call <strong>911</strong>.
            For shelter, food, or someone to talk to, get help lines that pick up
            24/7.
          </p>
        </div>
        <Link to="/emergency"><button className="urgent big">Get help now</button></Link>
      </section>

      {/* Regional anchor: built for Alberta's programs and deadlines. */}
      <section className="region-band" aria-label="Where Rebuildr works">
        <div className="region-band-head">
          <span className="region-tag">Alberta</span>
          <p>
            Built around Alberta's recovery programs, relief funding, and
            filing deadlines, so the guidance fits the rules where you live.
          </p>
        </div>
        <ul className="region-list">
          {ALBERTA_REGIONS.map((r) => (
            <li key={r} className="pill">{r}</li>
          ))}
        </ul>
        <div className="region-grid">
          {ALBERTA_DESK.map((d) => (
            <div key={d.title} className="region-card">
              <strong>{d.title}</strong>
              <span>{d.detail}</span>
            </div>
          ))}
        </div>
      </section>

      {/* #2: interactive no-login demo of the AI scan. */}
      <section className="landing-section">
        <div className="section-head">
          <h2>Try it yourself</h2>
          <p className="muted-strong">
            See what our AI finds in one photo of a room. No account needed.
          </p>
        </div>
        <DemoDropzone />
      </section>

      {/* #1 + #16: show the product through framed mockups, not paragraphs. */}
      <section className="landing-section">
        <div className="section-head">
          <h2>What Rebuildr does</h2>
        </div>
        <div className="grid grid-3">
          {PILLARS.map((p) => (
            <div key={p.title} className="pillar">
              <div className="phone-mock">
                <img src={p.img} alt={p.alt} />
              </div>
              <h3>{p.title}</h3>
              <p className="muted-strong">{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* #3: concrete security/trust statement, true to the RLS setup. */}
      <section className="landing-section">
        <div className="card calm-card trust-badge">
          <div className="trust-mark" aria-hidden>Privacy</div>
          <div>
            <h2 style={{ marginTop: 0 }}>How we handle your information</h2>
            <p className="muted-strong" style={{ marginBottom: 6 }}>
              Your records are encrypted in transit and stored so each account can only reach its own.
              We do not sell your information or run ad trackers. Photos and documents you upload are
              sent to Google's Gemini service for analysis. You can download your data or delete your
              account from Settings.
            </p>
            <p className="muted-strong" style={{ margin: 0 }}>
              Read our{" "}
              <Link to="/legal/privacy" style={{ color: "var(--focus)", textDecoration: "underline" }}>Privacy Policy</Link>{" "}
              and{" "}
              <Link to="/legal/terms" style={{ color: "var(--focus)", textDecoration: "underline" }}>Terms of Service</Link>.
            </p>
          </div>
        </div>
      </section>

      <section className="landing-section center-cta">
        <h2>Ready when you are</h2>
        <p className="muted-strong" style={{ maxWidth: 520, margin: "0 auto 20px" }}>
          Start with a single photo or document. We will be here for the rest.
        </p>
        <div className="cta-row" style={{ justifyContent: "center" }}>
          <StartButton />
        </div>
      </section>

      <footer className="landing-footer">
        <Link to="/legal/privacy">Privacy Policy</Link>
        <span aria-hidden>·</span>
        <Link to="/legal/terms">Terms of Service</Link>
        <span aria-hidden>·</span>
        <Link to="/legal/cookies">Cookies</Link>
        <span aria-hidden>·</span>
        <Link to="/legal/refunds">Refunds</Link>
        <span aria-hidden>·</span>
        <Link to="/emergency">Get help now</Link>
      </footer>
    </div>
  );
}
