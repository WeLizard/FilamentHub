import { Package } from 'lucide-react';

import { LegalDocumentPage } from '../components/LegalDocumentPage';

export const TermsPage = () => (
  <LegalDocumentPage
    documentType="terms"
    route="/user-agreement"
    fallbackTitleKey="termsPage.title"
    icon={Package}
    iconClassName="from-purple-500 to-pink-500 shadow-purple-500/25"
  />
);
