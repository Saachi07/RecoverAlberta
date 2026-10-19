import { LegalLayout } from "./LegalLayout";

export default function Cookies() {
  return (
    <LegalLayout title="Cookies and local storage">
      <p>
        We do not use advertising cookies, analytics cookies, or third-party trackers. The only things
        stored in your browser are needed to make the features you use work, so we do not show a cookie
        banner. If that ever changes, we will ask for your permission first and update this page.
      </p>
      <h2>What is stored on your device</h2>
      <ul>
        <li><strong>Sign-in session</strong> (Supabase, local storage): keeps you signed in. Needed to use your account.</li>
        <li><strong>Drafts and checklists</strong> (local storage): unsent inventory drafts, your preparedness checklist, and coverage notes, so you do not lose work if the page reloads.</li>
        <li><strong>Dismissed notices</strong> (local or session storage): remembers which tips and alerts you closed.</li>
        <li><strong>Offline copy of the app</strong> (service worker cache): lets the Emergency contacts page open without a signal.</li>
      </ul>
      <h2>Clearing it</h2>
      <p>
        You can clear this data any time in your browser settings. Signing out and clearing site data
        removes the session and local drafts from that device. Your saved records on our servers stay
        until you delete them.
      </p>
    </LegalLayout>
  );
}
