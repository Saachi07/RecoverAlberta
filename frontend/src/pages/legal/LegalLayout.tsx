import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { BUSINESS } from "../../legal/business";

export function LegalLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="legal" id="main">
      <h1>{title}</h1>
      <p className="muted-strong">Last updated: {BUSINESS.legalDateLabel} (version {BUSINESS.legalVersion})</p>
      {children}
      <h2>Who we are and how to reach us</h2>
      <p>
        {BUSINESS.operatorName}. Email: <a href={`mailto:${BUSINESS.contactEmail}`}>{BUSINESS.contactEmail}</a>.{" "}
        {BUSINESS.mailingAddress ? `Mailing address: ${BUSINESS.mailingAddress}.` : "Mailing address: available on request by email."}
      </p>
      <nav aria-label="Legal pages" className="legal-nav">
        <Link to="/legal/privacy">Privacy Policy</Link> · <Link to="/legal/terms">Terms of Service</Link> ·{" "}
        <Link to="/legal/cookies">Cookies and local storage</Link> · <Link to="/legal/refunds">Refunds</Link>
      </nav>
    </main>
  );
}
