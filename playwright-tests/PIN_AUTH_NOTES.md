# PIN Authentication Notes for Testing

## PIN Screen Structure

The GODFIN app uses a PIN screen with **4 separate input fields**, one for each digit of the 4-digit PIN.

### Key Selectors

| Element | Selector | Notes |
|---------|----------|-------|
| PIN Input Fields | `input[type="password"]` | There are exactly 4 of these, each accepting 1 digit |
| PIN Screen Container | The parent div contains all 4 inputs | Use `.locator('input[type="password"]').count()` to verify |

### PIN Entry Flow

1. Navigate to app root (`/`)
2. Wait for networkidle state
3. Locate the 4 PIN input fields
4. Fill each digit into its respective field:
   - Field 0: '1'
   - Field 1: '2'
   - Field 2: '3'
   - Field 3: '4'
5. Wait for auto-submit (the `onComplete` callback fires when all 4 digits are entered)
6. Verify redirect to root URL (away from `/pin`)

### Auto-Submit Behavior

The PIN screen **does NOT have a submit button**. The form auto-submits via an `onComplete` callback when:
- All 4 input fields contain a digit
- The callback is triggered in `PinInput.jsx` line 22-24

### Screenshot Paths

- Debug screenshot: `../screenshots/pin_screen_debug.png`
- After PIN entry: `../screenshots/after_pin.png`
- Main app: `../screenshots/main_app.png`

### Common Issues

- **Incorrect PIN entry**: Filling '1234' into the first field only (each field accepts max 1 character)
- **Solution**: Iterate through all 4 fields and fill one digit each

### Working Code Pattern

```javascript
const pinInputs = page.locator('input[type="password"]');
const pin = '1234';
for (let i = 0; i < 4; i++) {
  await pinInputs.nth(i).fill(pin[i]);
}
```

## Verification

Run smoke tests:
```bash
cd playwright-tests
npx playwright test tests/smoke.test.js --reporter=list
```

All 4 tests should pass:
1. App loads on port 5200
2. Backend responds on port 5100
3. PIN screen appears and accepts 1234
4. Main app content visible after PIN