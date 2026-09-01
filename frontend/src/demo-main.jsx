import { installDemoTransport } from './demo/transport';
import './demo/demo.css';

const NativeDate = window.Date;
const DEMO_NOW = NativeDate.parse('2026-07-31T12:00:00+05:30');

class DemoDate extends NativeDate {
  constructor(...args) {
    super(...(args.length === 0 ? [DEMO_NOW] : args));
  }

  static now() {
    return DEMO_NOW;
  }
}

window.Date = DemoDate;
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
