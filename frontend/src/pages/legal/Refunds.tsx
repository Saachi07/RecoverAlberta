import { LegalLayout } from "./LegalLayout";
import { BUSINESS } from "../../legal/business";

export default function Refunds() {
  return (
    <LegalLayout title="Refund Policy">
      <p>
        {BUSINESS.productName} is free to use. We do not charge for accounts, scans, or any other
        feature, and we do not collect payment details, so there is nothing to refund.
      </p>
      <p>
        If we ever add paid features, we will publish the price, billing terms, and refund rules here
        and ask for your agreement before you are charged.
      </p>
    </LegalLayout>
  );
}
