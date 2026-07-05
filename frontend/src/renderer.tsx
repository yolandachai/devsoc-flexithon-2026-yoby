import { createRoot } from 'react-dom/client';
import App from './App';
import './index.css';

const FONT_FAMILIES = [
  'Redaction',
  'Redaction 10',
  'Redaction 20',
  'Redaction 35',
  'Redaction 50',
  'Redaction 70',
  'Redaction 100',
];

async function waitForFonts() {
  await Promise.all(
    FONT_FAMILIES.flatMap((family) => [
      document.fonts.load(`normal 16px "${family}"`),
      document.fonts.load(`bold 16px "${family}"`),
      document.fonts.load(`italic 16px "${family}"`),
    ]),
  );
  await document.fonts.ready;
}

waitForFonts().finally(() => {
  const root = createRoot(document.getElementById('root')!);
  root.render(<App />);
});
