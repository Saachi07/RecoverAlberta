import { useEffect, useRef, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Landing from "./pages/Landing";
import Dashboard from "./pages/Dashboard";
import NewCase from "./pages/NewCase";
import CaseHub from "./pages/CaseHub";
import Inventory from "./pages/Inventory";
import Recommendations from "./pages/Recommendations";
import Emergency from "./pages/Emergency";
import Documents from "./pages/Documents";
import NotFound from "./pages/NotFound";
import Profile from "./pages/Profile";
import Prepare from "./pages/Prepare";
import FirstRun from "./pages/FirstRun";
import Settings from "./pages/Settings";
import Terms from "./pages/legal/Terms";
import Privacy from "./pages/legal/Privacy";
import Cookies from "./pages/legal/Cookies";
import Refunds from "./pages/legal/Refunds";
import Presentation from './pages/Presentation';
import { TermsGate } from "./components/TermsGate";
import { BrandLoader } from "./components/BrandLoader";
import { HelpFooter } from "./components/HelpFooter";
import { CasePicker } from "./components/CasePicker";
import { OfflineBanner } from "./components/OfflineBanner";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ToastProvider } from "./components/Toast";
import { CasesProvider, useCases } from "./lib/CasesContext";
import { PageBackProvider, usePageBack } from "./lib/PageBackContext";
import { BackButton } from "./components/BackButton";
import { useStartRecovery } from "./lib/useStartRecovery";
import { useDismissable } from "./lib/useDismissable";
import { api } from "./api";
import { isAlertRelevantToLocation } from "./lib/regionMapping";

type DerivedNotif = {
  id: string;
  title: string;
  body: string;
  to?: string;
  unread: boolean;
};

// Read/dismissed state for derived notifications, persisted locally so the
// red badge actually goes away once the user has seen things. A permanently
// red badge is a low-grade stressor for an already anxious user.
const SEEN_KEY = "rebuildr.notifs.seen";
const DISMISSED_KEY = "rebuildr.notifs.dismissed";

function readIdSet(key: string): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(key) ?? "[]") as string[]);
  } catch {
    return new Set();
  }
}

function writeIdSet(key: string, ids: Set<string>) {
  try {
    localStorage.setItem(key, JSON.stringify(Array.from(ids).slice(-200)));
  } catch {
    /* storage full or unavailable, fine, this is best-effort */
  }
}

function useDerivedNotifications(): {
  notifs: DerivedNotif[];
  markSeen: (id: string) => void;
  dismiss: (id: string) => void;
} {
  const { user } = useAuth();
  // Reuse the shared cases list instead of refetching /cases here. Both this
  // effect and CasesProvider used to request /cases (and retry on the slow
  // cold-start backend), doubling the request pile-up; now there's one fetch.
  const { cases } = useCases();
  const [notifs, setNotifs] = useState<DerivedNotif[]>([]);
  const [seen, setSeen] = useState<Set<string>>(() => readIdSet(SEEN_KEY));
  const [dismissed, setDismissed] = useState<Set<string>>(() => readIdSet(DISMISSED_KEY));

  useEffect(() => {
    if (!user) { setNotifs([]); return; }
    // Wait for the shared cases list rather than fetching our own copy.
    if (cases === null) return;
    let cancelled = false;
    (async () => {
      try {
        const [docsRes, alertsRes, meRes] = await Promise.all([
          api.listMyDocuments(),
          api.listAlerts(),
          api.getMe(),
        ]);
        if (cancelled) return;
        const out: DerivedNotif[] = [];
        const docs = docsRes.documents;
        const alerts = (alertsRes && (alertsRes.alerts ?? [])) || [];
        const weatherTerms = ["tornado", "wildfire", "flood", "winter storm", "evacuation"];
        const profileRegion = meRes?.profile?.region || null;
        const caseRegion = cases && cases.length > 0 ? cases[0].region : null;
        const userLocation = profileRegion || caseRegion || null;

        // Filter alerts by region: map user's municipality to Alberta 511 regions
        // and only show alerts relevant to that location.
        const filteredAlerts = alerts.filter((a) => {
          try {
            const alertRegions = (a.regions || []).map((r: any) => String(r || "")).filter(Boolean);
            return isAlertRelevantToLocation(userLocation, alertRegions);
          } catch {
            return true;
          }
        });
        const hasPolicy = docs.some((d) => d.doc_type === "insurance_policy" || d.doc_type === "policy");
        if (!hasPolicy) {
          out.push({
            id: "policy-missing",
            title: "Upload your insurance policy",
            body: "We use your policy to find deadlines and coverage gaps. It only takes a minute.",
            to: "/documents",
            unread: true,
          });
        }

        if (cases.length === 0) {
          out.push({
            id: "no-case",
            title: "Start your first case",
            body: "Tell us what happened so we can build your plan.",
            to: "/cases/new",
            unread: true,
          });
        } else {
          const latest = cases[0];
          out.push({
            id: `recs-${latest.id}`,
            title: "Your recovery plan is ready",
            body: `Open the latest plan for ${latest.case_name}.`,
            to: `/cases/${latest.id}/recommendations`,
            unread: false,
          });

          // Check inventory for the latest case; if missing or empty, remind user
          try {
            const itemsRes = await api.listItems(latest.id);
            const items = itemsRes?.items ?? [];
            if (!items || items.length === 0) {
              out.push({
                id: `inventory-missing-${latest.id}`,
                title: "Complete your home inventory",
                body: "A detailed home inventory helps document your losses. Adding photos and items now makes everything easier later.",
                to: `/cases/${latest.id}/inventory`,
                unread: true,
              });
            }
          } catch {
            // don't block notifications if the inventory check fails
          }
        }

        // Surface document deadlines pulled out by Gemini.
        for (const d of docs) {
          const fields = (d.gemini_analysis?.key_fields ?? {}) as Record<string, unknown>;
          const deadline = fields["deadline"] ?? fields["filing_deadline"] ?? fields["due_date"];
          if (typeof deadline === "string" && deadline.trim()) {
            out.push({
              id: `deadline-${d.id}`,
              title: `Deadline in ${d.name}`,
              body: String(deadline),
              to: "/documents",
              unread: true,
            });
          }
        }

        // Surface weather / Alberta 511 alerts
        for (const a of filteredAlerts) {
          try {
            const send = !!a.send_notification;
            if (!send) continue;
            const msg = String(a.message || a.long_description || a.description || "");
            const lower = msg.toLowerCase();
            const high = weatherTerms.some((t) => lower.includes(t));
            const insuranceAppend = !hasPolicy ? "\n\nPlease upload your insurance documents to prepare for potential claims." : "";
            out.push({
              id: `alert-${a.id}`,
              title: `${high ? "Important: " : ""}${String(a.title || "Weather alert")}`,
              body: `${msg}${insuranceAppend}`,
              to: "/emergency",
              unread: true,
            });
          } catch {
            // swallow malformed alerts
            continue;
          }
        }

        setNotifs(out);
      } catch {
        if (!cancelled) setNotifs([]);
      }
    })();
    return () => { cancelled = true; };
  }, [user, cases]);

  const visible = notifs
    .filter((n) => !dismissed.has(n.id))
    .map((n) => ({ ...n, unread: n.unread && !seen.has(n.id) }));

  function markSeen(id: string) {
    setSeen((prev) => {
      const next = new Set(prev).add(id);
      writeIdSet(SEEN_KEY, next);
      return next;
    });
  }

  function dismiss(id: string) {
    setDismissed((prev) => {
      const next = new Set(prev).add(id);
      writeIdSet(DISMISSED_KEY, next);
      return next;
    });
    markSeen(id);
  }

  return { notifs: visible, markSeen, dismiss };
}

function NotificationsButton() {
  const { notifs, markSeen, dismiss } = useDerivedNotifications();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const nav = useNavigate();
  const unreadCount = notifs.filter((n) => n.unread).length;

  useDismissable(ref, open, () => setOpen(false));

  return (
    <div className="nav-pop" ref={ref}>
      <button
        className="icon-btn"
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <svg aria-hidden viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.7 21a2 2 0 0 1-3.4 0" />
        </svg>
        {unreadCount > 0 && <span className="dot-badge">{unreadCount}</span>}
      </button>
      {open && (
        <div className="popover">
          <div className="popover-header">What needs attention</div>
          {notifs.length === 0 && (
            <div className="notif-empty">You're all caught up.</div>
          )}
          {notifs.map((n) => (
            <div
              key={n.id}
              className={`notif-item${n.unread ? " unread" : ""}${n.to ? " actionable" : ""}`}
              onClick={() => {
                markSeen(n.id);
                if (n.to) { setOpen(false); nav(n.to); }
              }}
            >
              <div className="row" style={{ gap: 6, flexWrap: "nowrap", alignItems: "flex-start" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="notif-title">{n.title}</div>
                  <div className="notif-body">{n.body}</div>
                </div>
                <button
                  className="close-x"
                  aria-label={`Dismiss "${n.title}"`}
                  onClick={(e) => { e.stopPropagation(); dismiss(n.id); }}
                >
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Phase-aware targets for the two contextual sections. With an active case,
// Plan and Inventory resolve to that case; otherwise Plan starts a case and
// Inventory opens the preparedness flow where pre-loss inventory lives.
function useSectionTargets() {
  const { latest, phase, latestOpen } = useCases();
  const planTo = latest ? `/cases/${latest.id}/recommendations` : "/cases/new";
  const inventoryTo =
    phase === "recovery" && latestOpen ? `/cases/${latestOpen.id}/inventory` : "/prepare";
  return { planTo, inventoryTo };
}

// The avatar opens one menu holding both navigation (Plan, Dashboard,
// Inventory, Documents) and account actions. Folding the sections in here keeps
// the header uncluttered; only "Get help" stays out on its own, since burying
// emergency contacts in a dropdown adds friction at the worst moment.
function ProfileMenu() {
  const { user, signOut } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const { planTo, inventoryTo } = useSectionTargets();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useDismissable(ref, open, () => setOpen(false));

  const initial = (user?.email ?? "?").trim().charAt(0).toUpperCase();
  const sections = [
    { label: "Plan", to: planTo },
    { label: "Dashboard", to: "/dashboard" },
    { label: "Inventory", to: inventoryTo },
    { label: "Documents", to: "/documents" },
  ];

  return (
    <div className="nav-pop" ref={ref}>
      <button
        className="avatar-btn"
        aria-label="Menu"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {initial}
      </button>
      {open && (
        <div className="popover" role="menu">
          <div className="profile-head">
            <div className="avatar-lg">{initial}</div>
            <div>
              <div className="profile-name">Signed in</div>
              <div className="profile-email">{user?.email}</div>
            </div>
          </div>
          {sections.map((s) => (
            <button
              key={s.label}
              className="menu-item"
              aria-current={loc.pathname === s.to || undefined}
              onClick={() => { setOpen(false); nav(s.to); }}
            >
              {s.label}
            </button>
          ))}
          <div className="menu-divider" />
          <button className="menu-item" onClick={() => { setOpen(false); nav("/profile"); }}>
            View profile
          </button>
          <button className="menu-item" onClick={() => { setOpen(false); nav("/settings"); }}>
            Settings
          </button>
          <button
            className="menu-item danger-text"
            onClick={async () => { setOpen(false); await signOut(); nav("/"); }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

// Bottom tab bar links on phones: the essentials, always one thumb-tap away,
// including emergency help. Desktop navigation lives in the avatar menu now,
// so this is mobile-only.
function SectionLinks({ className }: { className: string }) {
  const { planTo, inventoryTo } = useSectionTargets();
  const cls = ({ isActive }: { isActive: boolean }) => (isActive ? "active" : "");
  return (
    <nav className={className} aria-label="Main sections">
      <NavLink to={planTo} end className={cls}>Plan</NavLink>
      <NavLink to={inventoryTo} end className={cls}>Inventory</NavLink>
      <NavLink to="/emergency" className={({ isActive }) => (isActive ? "active urgent-link" : "urgent-link")}>
        Get help
      </NavLink>
    </nav>
  );
}

// Text-only chip shown while preparing. Tapping it starts recovery. We never
// use it in recovery phase, the rest of the nav already reflects an open case.
function PhaseChip() {
  const { phase } = useCases();
  const startRecovery = useStartRecovery();
  const [busy, setBusy] = useState(false);
  if (phase !== "prepare") return null;
  return (
    <button
      className="phase-chip"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await startRecovery();
        } finally {
          setBusy(false);
        }
      }}
    >
      Preparing
    </button>
  );
}

// "Try our product" must reliably land a signed-out visitor inside the app.
// Linking straight to /home bounces them back here whenever a session hasn't
// been established yet, so we ensure one first and then navigate.
function TryProductButton() {
  const { ensureSession } = useAuth();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  return (
    <button
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          // Only navigate once a session exists; both targets are guarded, so
          // navigating without one would just bounce back here.
          if (await ensureSession()) nav("/home");
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? "Loading…" : "Try our product"}
    </button>
  );
}

function Nav() {
  const { user } = useAuth();
  return (
    <div className="nav">
      <Link to={user ? "/home" : "/"} className="brand">
        <img className="brand-mark" src={`${import.meta.env.BASE_URL}brand/logo.png`} alt="" aria-hidden />
        <span>Rebuildr</span>
      </Link>
      <div className="row">
        {user ? (
          <>
            <PhaseChip />
            <CasePicker />
            <NavLink to="/emergency" className={({ isActive }) => (isActive ? "nav-help active" : "nav-help")}>Get help</NavLink>
            <NotificationsButton />
            <ProfileMenu />
          </>
        ) : (
          <>
            <Link to="/emergency" className="urgent-link">Get help now</Link>
            <TryProductButton />
          </>
        )}
      </div>
    </div>
  );
}

// Bottom tab bar on phones: the four places a stressed user needs, always
// one thumb-tap away, including emergency help.
function MobileTabBar() {
  const { user } = useAuth();
  const loc = useLocation();
  if (!user) return null;
  if (loc.pathname.startsWith("/login") || loc.pathname.startsWith("/legal")) return null;
  return <SectionLinks className="tabbar" />;
}

function ActionBar() {
  const { user } = useAuth();
  const loc = useLocation();
  const back = usePageBack();
  if (!user) return null;
  if (loc.pathname.startsWith("/login") || loc.pathname.startsWith("/legal")) return null;
  // The case picker now lives in the main nav row, so there's no sub-bar left.
  // The page's back control floats over the top-left of the content instead of
  // sitting in a full-width strip; nothing renders when there's no back target.
  if (!back) return null;
  return (
    <div className="back-fab">
      <BackButton to={back.to} label={back.label} />
    </div>
  );
}

function Private({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) return <BrandLoader />;
  // Demo mode signs everyone in automatically, so there's no /login page; if a
  // session genuinely can't be established we send people to the landing page
  // rather than a route that no longer exists.
  if (!user) return <Navigate to="/" replace />;
  return children;
}

// The phase-aware landing for a signed-in user. Phase is derived from server
// state, so the same account shows the same home on every device. While the
// lists are still loading we show the spinner rather than guessing, otherwise
// the wrong phase would flash before the real one settles.
//
// A brand-new user (no cases, no inventory) gets the one-time situational
// welcome instead of the prepare hub. Everyone else auto-lands where they
// left off: in recovery, straight into their active case (the case page is the
// informative home now); the prepare hub otherwise. The Dashboard remains the
// fallback when the only open case is still an unfinished draft.
function Home() {
  const { cases, myItems, phase, isNewUser, openCases } = useCases();
  if (cases === null || myItems === null) {
    return <BrandLoader message="Loading your recovery space…" />;
  }
  if (phase === "prepare" && isNewUser) return <FirstRun />;
  if (phase === "prepare") return <Prepare />;
  const activeCase = openCases.find((c) => c.status === "active");
  return activeCase ? <Navigate to={`/cases/${activeCase.id}`} replace /> : <Dashboard />;
}

export default function App() {
  const location = useLocation();
  return (
    <CasesProvider>
      <PageBackProvider>
      <ToastProvider>
        <TermsGate>
          <OfflineBanner />
          <header className="site-header">
            <Nav />
            <ActionBar />
          </header>
          <ErrorBoundary routeKey={location.pathname}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/emergency" element={<Emergency />} />
            <Route path="/legal/terms" element={<Terms />} />
            <Route path="/legal/privacy" element={<Privacy />} />
            <Route path="/legal/cookies" element={<Cookies />} />
            <Route path="/legal/refunds" element={<Refunds />} />
            <Route path="/home" element={<Private><Home /></Private>} />
            <Route path="/dashboard" element={<Private><Dashboard /></Private>} />
            <Route path="/profile" element={<Private><Profile /></Private>} />
            <Route path="/prepare" element={<Private><Prepare /></Private>} />
            <Route path="/settings" element={<Private><Settings /></Private>} />
            <Route path="/documents" element={<Private><Documents /></Private>} />
            <Route path="/cases/new" element={<Private><NewCase /></Private>} />
            <Route path="/cases/:id" element={<Private><CaseHub /></Private>} />
            <Route path="/cases/:id/inventory" element={<Private><Inventory /></Private>} />
            <Route path="/cases/:id/recommendations" element={<Private><Recommendations /></Private>} />
            <Route path="*" element={<NotFound />} />
            <Route path="/booth" element={<Presentation />} />
          </Routes>
          </ErrorBoundary>
          <HelpFooter />
          <MobileTabBar />
        </TermsGate>
      </ToastProvider>
      </PageBackProvider>
    </CasesProvider>
  );
}
