import React, { useState, useEffect } from 'react';

export const CookieBanner: React.FC = () => {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const consent = localStorage.getItem('cookie-consent');
    if (!consent) {
      setIsVisible(true);
    }
  }, []);

  const acceptCookies = () => {
    localStorage.setItem('cookie-consent', 'accepted');
    setIsVisible(false);
    // Initialize analytics here if applicable
  };

  if (!isVisible) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-gray-900 text-white p-4 z-50 flex flex-col sm:flex-row items-center justify-between shadow-lg">
      <div className="text-sm mb-4 sm:mb-0 mr-4">
        We use cookies to improve your experience and analyze site traffic. By continuing to use this site, you agree to our <a href="/legal/privacy" className="underline hover:text-blue-300">Privacy Policy</a> and <a href="/legal/terms" className="underline hover:text-blue-300">Terms of Service</a>.
      </div>
      <button 
        onClick={acceptCookies}
        className="whitespace-nowrap px-6 py-2 bg-blue-600 hover:bg-blue-700 rounded-md font-medium transition-colors"
      >
        Accept
      </button>
    </div>
  );
};