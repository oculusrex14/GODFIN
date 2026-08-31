import { installDemoTransport } from './demo/transport';
import './demo/demo.css';

installDemoTransport();

const badge = document.createElement('aside');
badge.className = 'godfin-demo-badge';
badge.setAttribute('role', 'note');
badge.innerHTML = `
  <strong>Synthetic desktop demo</strong>
  <span>Made-up household · no bank, Gmail, AI, or payment connection</span>
  <a href="/">Exit demo</a>
`;
document.body.append(badge);

await import('./main.jsx');
