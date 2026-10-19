import { LegalLayout } from "./LegalLayout";
import { BUSINESS } from "../../legal/business";

export default function Privacy() {
  return (
    <LegalLayout title="Privacy Policy">
      <p>
        This policy explains what {BUSINESS.productName} collects, why, who it is shared with, and
        the choices you have. It is written with Canada's PIPEDA and Alberta's Personal Information
        Protection Act in mind. It is a plain-language summary, not legal advice.
      </p>

      <h2>What we collect</h2>
      <ul>
        <li>Account details: your email address and sign-in state (managed by Supabase).</li>
        <li>Profile details you choose to give us: your name and general location.</li>
        <li>
          Recovery records you create: cases, inventory items, expenses, communication notes, and the
          photos and documents you upload. Photos and documents can contain sensitive information
          such as insurance policy numbers, addresses, and images of your home.
        </li>
        <li>Basic technical logs needed to run and debug the service (for example errors and request times).</li>
      </ul>
      <p>We do not run advertising or analytics trackers, and we do not use third-party embeds.</p>

      <h2>Why we use it</h2>
      <p>
        To store your records, analyze your photos and documents, match you with relevant recovery
        resources, keep your account secure, and fix problems. We do not sell your information.
      </p>

      <h2>Who processes it for us</h2>
      <ul>
        <li><strong>Supabase</strong> provides our database, sign-in, and file storage.</li>
        <li>
          <strong>Google (Gemini API)</strong> analyzes photos and documents you upload so we can
          build inventories and plain-language summaries. The file content is sent to Google for that
          purpose. Before sending documents we attempt to remove some personal identifiers, but
          redaction is not perfect, so please do not upload anything you are not comfortable sending.
        </li>
        <li><strong>Hosting providers</strong> run our servers.</li>
      </ul>
      <p>
        These providers may store or process data on servers outside Canada, including in the United
        States, where local laws may allow government access. Your photos and documents are used only
        to give you the service you asked for. Because analysis is the core of the product, we cannot
        analyze a file without sending it to Google.
      </p>
      <p>
        The "Try it yourself" demo on the home page sends the single photo you choose to the same
        Google service. We ask for your permission first, process it in memory, and do not store it.
      </p>

      <h2>Your consent</h2>
      <p>
        When you create an account you agree to this policy. Where we ask for a specific permission
        (for example before the demo scan), you can say no and keep using the rest of the site. You can
        withdraw consent by deleting your content or your account; some features then stop working.
      </p>

      <h2>How long we keep it</h2>
      <p>
        We keep your records until you delete them or delete your account. Deleting your account removes
        your cases, items, documents, stored files, and login. Backups held by our providers may keep
        copies for a short period before they expire.
      </p>

      <h2>Your rights</h2>
      <p>
        You can see and download your data and delete your account from Settings. You can also ask us
        to access, correct, or delete your information, or to explain how it is handled, by emailing us.
        If we cannot resolve a concern, you may complain to the Office of the Privacy Commissioner of
        Canada or the Office of the Information and Privacy Commissioner of Alberta.
      </p>

      <h2>Security</h2>
      <p>
        Data is encrypted in transit and stored with access controls so each account can only reach its
        own records. Documents live in a private bucket and are opened through short-lived links. No
        system is perfectly secure. If a breach creates a real risk of significant harm to you, we will
        notify you and the privacy regulators as the law requires.
      </p>

      <h2>Children</h2>
      <p>{BUSINESS.productName} is intended for adults. We do not knowingly collect information from children.</p>

      <h2>Changes</h2>
      <p>
        When this policy changes in a meaningful way, we update the date above and ask you to review and
        accept it again the next time you sign in.
      </p>
    </LegalLayout>
  );
}
