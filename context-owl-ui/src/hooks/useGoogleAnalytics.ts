import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

const GA_MEASUREMENT_ID = import.meta.env.VITE_GA_MEASUREMENT_ID;

export const initGA = () => {
  if (!GA_MEASUREMENT_ID) {
    return;
  }

  // Initialize dataLayer and gtag function before script loads
  window.dataLayer = window.dataLayer || [];
  window.gtag = function (..._args: any[]) {
    window.dataLayer.push(arguments);
  };

  // Load gtag script first, then configure after it loads
  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`;
  script.onload = () => {
    // Now safe to call gtag after script loads
    window.gtag('js', new Date());
    window.gtag('config', GA_MEASUREMENT_ID);
  };
  document.head.appendChild(script);
};

export const usePageTracking = () => {
  const location = useLocation();

  useEffect(() => {
    if (!GA_MEASUREMENT_ID || !window.gtag) {
      return;
    }

    // Send page_view event when location changes
    window.gtag('event', 'page_view', {
      page_path: location.pathname,
      page_title: document.title,
    });
  }, [location]);
};
