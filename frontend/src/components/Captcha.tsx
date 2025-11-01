/** ЗАГЛУШКА: Компонент капчи - визуальная заглушка */

import { useState } from 'react';
import { RefreshCw, Shield } from 'lucide-react';

interface CaptchaProps {
  value: string;
  onChange: (value: string) => void;
  onVerify: (isVerified: boolean) => void;
}

export const Captcha: React.FC<CaptchaProps> = ({ value, onChange, onVerify }) => {
  const [captchaCode, setCaptchaCode] = useState(() => {
    // Генерируем случайный код
    return Math.random().toString(36).substring(2, 8).toUpperCase();
  });
  const [isVerified, setIsVerified] = useState(false);

  const handleRefresh = () => {
    const newCode = Math.random().toString(36).substring(2, 8).toUpperCase();
    setCaptchaCode(newCode);
    setIsVerified(false);
    onChange('');
    onVerify(false);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const inputValue = e.target.value.toUpperCase();
    onChange(inputValue);

    if (inputValue === captchaCode) {
      setIsVerified(true);
      onVerify(true);
    } else {
      setIsVerified(false);
      onVerify(false);
    }
  };

  return (
    <div className="bg-white/5 rounded-xl p-4 border border-white/10">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-2">
          <Shield className="w-4 h-4 text-purple-400" />
          <label className="text-gray-300 text-sm font-medium">Подтвердите, что вы не робот</label>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          className="p-1 text-gray-400 hover:text-white transition-colors"
          title="Обновить капчу"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <div className="flex items-center space-x-3">
        {/* Captcha Display */}
        <div className="flex-1 bg-white/10 rounded-lg p-4 border border-white/20">
          <div className="flex items-center justify-center space-x-2">
            {captchaCode.split('').map((char, index) => (
              <span
                key={index}
                className="text-2xl font-bold text-white"
                style={{
                  transform: `rotate(${Math.random() * 20 - 10}deg)`,
                  textShadow: '2px 2px 4px rgba(0,0,0,0.3)',
                }}
              >
                {char}
              </span>
            ))}
          </div>
          <div className="mt-2 flex items-center justify-center space-x-1">
            {/* Декоративные линии для "реалистичности" */}
            {[...Array(6)].map((_, i) => (
              <div
                key={i}
                className="h-0.5 bg-white/20 rounded-full"
                style={{ width: `${Math.random() * 20 + 10}px` }}
              ></div>
            ))}
          </div>
        </div>

        {/* Input */}
        <div className="flex-1">
          <input
            type="text"
            value={value}
            onChange={handleInputChange}
            placeholder="Введите код"
            maxLength={6}
            className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all text-center font-mono text-lg"
          />
        </div>
      </div>

      {/* Status */}
      {value && (
        <div className="mt-2 text-xs text-center">
          {isVerified ? (
            <span className="text-green-400 flex items-center justify-center space-x-1">
              <Shield className="w-3 h-3" />
              <span>Проверка пройдена</span>
            </span>
          ) : (
            <span className="text-red-400">Код неверный</span>
          )}
        </div>
      )}
    </div>
  );
};

