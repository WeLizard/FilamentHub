/** Страница восстановления пароля */

import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { ResetPasswordModal } from '../components/ResetPasswordModal';
import { useTranslation } from 'react-i18next';

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    const tokenParam = searchParams.get('token');
    if (tokenParam) {
      setToken(tokenParam);
    } else {
      // Если токена нет, перенаправляем на главную
      navigate('/');
    }
  }, [searchParams, navigate]);

  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="text-white text-xl">{t('resetPasswordPage.loading')}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
      <ResetPasswordModal
        isOpen={true}
        onClose={() => navigate('/')}
        token={token}
      />
    </div>
  );
}

