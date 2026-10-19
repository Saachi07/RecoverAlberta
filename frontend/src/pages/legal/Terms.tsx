import { LegalLayout } from "./LegalLayout";
import { BUSINESS } from "../../legal/business";

export default function Terms() {
  return (
    <LegalLayout title="Terms of Service">

      <h2>ACCEPTANCE OF TERMS</h2>
      <p>
        By creating an account or using Rebuildr (the "Service"), you agree to these Terms.
        If you do not agree, do not use the Service.
      </p>

      <h2>DEFINITIONS</h2>
      <p>
        <strong>"Rebuildr"</strong> means the application, a free, non-commercial student project
        based in Alberta, Canada, that provides disaster preparedness reminders, document
        organization tools, and plain-language policy summaries.
      </p>
      <p>
        <strong>"Content"</strong> means any photos, documents, inventory lists, or other data
        you upload.
      </p>

      <h2>NO LEGAL OR INSURANCE ADVICE</h2>
      <p>
        Rebuildr helps you organize damage inventory, parse insurance documents, and surface
        relief resources. Rebuildr is not a substitute for professional legal, insurance, or
        financial advice. No automated output constitutes an attorney-client relationship,
        insurance adjustment, or fiduciary duty.
      </p>

      <h2>YOUR ACCOUNT</h2>
      <p>
        You are responsible for your login credentials and all activity under your account.
        You must notify Rebuildr immediately of any unauthorized access.
      </p>

      <h2>YOUR CONTENT - OWNERSHIP AND LICENSE</h2>
      <p>
        You retain ownership of your Content. You grant Rebuildr a limited license to host,
        store, transmit, display, copy, and analyze your Content solely to operate and maintain
        the Service. This license ends when you delete your Content or close your account,
        except for reasonable backups. Rebuildr will not sell your Content.
      </p>

      <h2>ACCEPTABLE USE</h2>
      <p>
        You may not upload Content you do not own or have permission to use; access another
        user's data; harass others; reverse engineer the Service; or use automated scripts
        that impair performance. Violation may result in immediate account termination.
      </p>

      <h2>DATA PROCESSORS AND AI ANALYSIS</h2>
      <p>
        Rebuildr uses Supabase (database, authentication, storage) and Google Gemini (AI analysis
        of photos and documents). By using Rebuildr, you consent to your Content being processed
        by these processors, which may operate servers outside Canada. Google Gemini outputs may
        be inaccurate or incomplete. Reliance on AI outputs is at your sole risk. Because AI
        analysis is central to the Service, we cannot analyze a file without sending it to Google.
        If you do not agree to that, do not upload files. See the Privacy Policy for details.
      </p>

      <h2>DISCLAIMER OF WARRANTIES</h2>
      <p>
        The Service is provided "as is" and "as available." To the maximum extent permitted by
        Alberta law, Rebuildr disclaims all warranties, including merchantability, fitness for a
        particular purpose, accuracy of insurance document parsing, uninterrupted service, and
        security of data. No recovery plan or resource match is guaranteed correct.
      </p>

      <h2>LIMITATION OF LIABILITY</h2>
      <p>
        To the maximum extent permitted by Alberta law, Rebuildr's total liability for any claim
        arising from these Terms or the Service shall not exceed the greater of (a) the amount
        you paid Rebuildr in the prior 12 months (the Service is free), or (b) $100. Nothing in these Terms limits rights
        you have under consumer protection or privacy law that cannot be waived. Rebuildr is not liable for any
        indirect, incidental, special, consequential, or punitive damages, including lost profits,
        lost data, or insurance claim denials. This limitation applies even if Rebuildr has been
        advised of such damages.
      </p>

      <h2>INDEMNIFICATION</h2>
      <p>
        You agree to indemnify and hold harmless Rebuildr from any claims, damages, and expenses
        (including reasonable legal fees) arising from your Content, your violation of these
        Terms, or your misuse of the Service.
      </p>

      <h2>TERMINATION AND DATA DELETION</h2>
      <p>
        You may delete your account at any time. Rebuildr will remove your Content from active
        systems within 30 days, except for legal compliance or backups. Rebuildr may suspend or
        terminate your account immediately for violating these Terms. Provisions that by their nature
        should continue (ownership, disclaimers, limits of liability, indemnity, governing law) survive termination.
      </p>

      <h2>GOVERNING LAW</h2>
      <p>
        These Terms are governed by the laws of the Province of Alberta and the federal laws of
        Canada applicable therein. Any dispute shall be resolved exclusively in the courts of
        Calgary, Alberta.
      </p>

      <h2>COPYRIGHT COMPLAINTS</h2>
      <p>
        If you believe your copyright-protected work has been copied on the Service without
        permission, please contact Rebuildr at {BUSINESS.contactEmail} with a description of the
        work and its location. We will respond to valid notices.
      </p>

      <h2>CHANGES TO THESE TERMS</h2>
      <p>
        Rebuildr may update these Terms. Material changes will be notified by email or in-app notice.
        Continued use after the effective date constitutes acceptance. If you object, delete your account.
      </p>

      <h2>GENERAL</h2>
      <p>
        If any provision is unenforceable, the remainder remains in effect. Failure to enforce a right
        does not waive that right. These Terms are the entire agreement between you and Rebuildr.
      </p>

      <h2>CONTACT</h2>
      <p>For questions or account deletion: {BUSINESS.contactEmail}</p>

      <h2>NOT A LAW FIRM</h2>
      <p>
        Rebuildr is not a law firm, and these Terms are not legal advice. No communication with Rebuildr creates an attorney-client relationship. You are solely
        responsible for ensuring these terms comply with all applicable laws. If you need legal advice,
        consult a licensed Alberta lawyer.
      </p>
    </LegalLayout>
  );
}
