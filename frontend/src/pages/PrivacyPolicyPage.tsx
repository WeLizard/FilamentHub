import { Lock } from 'lucide-react';

import { LegalDocumentPage } from '../components/LegalDocumentPage';

export const PrivacyPolicyPage = () => (
  <LegalDocumentPage
    documentType="privacy_policy"
    route="/privacy-policy"
    fallbackTitleKey="privacyPage.title"
    icon={Lock}
    iconClassName="from-blue-500 to-cyan-500 shadow-blue-500/25"
  />
);
