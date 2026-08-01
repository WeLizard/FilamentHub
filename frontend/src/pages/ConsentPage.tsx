import { Shield } from 'lucide-react';

import { LegalDocumentPage } from '../components/LegalDocumentPage';

export const ConsentPage = () => (
  <LegalDocumentPage
    documentType="personal_data_consent"
    route="/personal-data-consent"
    fallbackTitleKey="consentPage.title"
    icon={Shield}
    iconClassName="from-green-500 to-emerald-500 shadow-green-500/25"
  />
);
