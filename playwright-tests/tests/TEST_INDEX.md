# Playwright Test Index

**Generated:** 2026-03-08
**Phase:** P3.5 Test Script Fix
**Total Test Files:** 10
**Total Tests:** 235
**Pass Rate:** 85.5% (201/235)

---

## Test Files

| # | File | Tests | Based On |
|---|------|-------|----------|
| 1 | `01_navigation.test.js` | 12 | system_map.md - Frontend Routes |
| 2 | `02_ui_components.test.js` | 25 | UI_TESTING_SUMMARY.md |
| 3 | `03_features.test.js` | 20 | feature_inventory.md, feature_testing/*.md |
| 4 | `04_forms_and_inputs.test.js` | 18 | edge_case_testing/edge_case_audit.md |
| 5 | `05_graphs_and_charts.test.js` | 15 | graph_testing/*.md |
| 6 | `06_filters.test.js` | 20 | filter_testing/*.md |
| 7 | `07_api_integration.test.js` | 15 | integration_testing/integration_audit.md |
| 8 | `08_security.test.js` | 15 | MASTER_BUG_LIST.md - Security bugs |
| 9 | `09_edge_cases.test.js` | 20 | edge_case_testing/edge_case_audit.md |
| 10 | `10_regression.test.js` | 30 | MASTER_BUG_LIST.md - CRITICAL/HIGH bugs |

---

## Test Categories

### Navigation Tests (01)
- Route loading verification
- Protected route authentication
- Navigation menu completeness
- Session persistence

### UI Components Tests (02)
- GlassButton interactions
- GlassInput validation
- GlassSelect dropdowns
- FilterBar functionality
- Modal accessibility
- Loading/error states
- ARIA compliance

### Features Tests (03)
- Transaction Management workflow
- Dashboard loading
- Review Queue resolution
- Budget/Goals creation
- Income tracking
- Statement Upload
- Reports generation
- Audit Manager
- Settings configuration

### Forms and Inputs Tests (04)
- Valid data submission
- Empty form validation
- Special character handling
- XSS prevention
- Boundary values
- Network error handling

### Graphs and Charts Tests (05)
- Pie chart rendering
- Line chart rendering
- Empty data handling
- Single data point
- Large data sets
- Responsive behavior
- Tooltips

### Filters Tests (06)
- Search debouncing
- Category filtering
- Date range filtering
- Sort functionality
- Combined filters
- Filter persistence
- Clear filters
- Special characters

### API Integration Tests (07)
- Transaction create flow
- Dashboard update flow
- Review resolution flow
- Audit lock flow
- Statement upload flow
- Error handling
- Network failures

### Security Tests (08)
- Authentication flow
- PIN validation
- Session management
- XSS prevention
- Authorization checks
- Input sanitization

### Edge Cases Tests (09)
- Empty states
- Rapid actions
- Large data handling
- Network failures
- Session expiry
- Input boundaries

### Regression Tests (10)
- CRITICAL bugs verification
- HIGH bugs verification
- MEDIUM bugs verification
- UI bugs verification

---

## Helper Files

| File | Purpose |
|------|---------|
| `helpers/auth.js` | PIN authentication helper, includes `enterPIN()`, `isOnPinScreen()`, and `navigateTo()` |
| `playwright.config.js` | Playwright configuration |

---

## Selector Reference

### PIN Authentication
- **PIN Inputs:** `input[type="password"]` (4 separate fields)
- **Auth Token:** Memory-only in the renderer; reload/window recreation requires the PIN
- **Helper:** Use `enterPIN(page)` from helpers/auth.js

### Navigation
- **Use `navigateTo(page, '/path')`** instead of `page.goto('/path')` to preserve auth
- **Links:** `a[href="/transactions"]`, `a[href="/settings"]`, etc.

### Search Input
- **Selector:** `input[placeholder="Search merchants..."]`
- **Note:** Located on Transactions page

### File Upload
- **Selector:** `input[type="file"]`
- **Note:** Hidden input - use `toHaveCount(1)` instead of `toBeVisible()`

### Empty States
- **Review Queue:** "All transactions categorized!", "No transactions need review right now."
- **Transactions:** Shows transaction table when data exists

### Gmail Integration
- **Location:** Settings page (`/settings`)
- **Text:** "Gmail Integration", "Gmail Connected"

---

## Running Tests

### Run all tests:
```bash
cd playwright-tests
npx playwright test --reporter=list
```

### Run specific test file:
```bash
npx playwright test tests/01_navigation.test.js --reporter=list
```

### Run with headed browser:
```bash
npx playwright test --headed
```

### Run specific test:
```bash
npx playwright test -g "Dashboard loads"
```

---

## Test Coverage

### From Phase 1 Reports

| Report | Coverage |
|--------|----------|
| system_map.md | All routes tested |
| feature_inventory.md | All 15 features tested |
| UI_TESTING_SUMMARY.md | All 27 components referenced |
| integration_audit.md | All 14 integration paths tested |
| edge_case_audit.md | All 47 edge cases referenced |
| MASTER_BUG_LIST.md | All CRITICAL/HIGH bugs referenced |
| graph_testing/*.md | All charts tested |
| filter_testing/*.md | All filters tested |

### Bug Coverage

| Severity | Tests |
|----------|-------|
| CRITICAL | 15 tests |
| HIGH | 41 tests |
| MEDIUM | 76 tests |
| LOW | 46 tests |

---

## Known Issues (Test Limitations)

1. **Mock Data Required**: Some tests require specific data states that may not exist in a fresh database
2. **Browser Context**: Security tests requiring multiple browser contexts may need adjustment
3. **Timing**: Some async operations may need additional wait times on slower machines
4. **Data Dependencies**: Tests that require existing data (e.g., edit transaction) may skip if no data

---

## Screenshots

Screenshots are saved to `playwright-tests/screenshots/`:
- `route_*.png` - Navigation screenshots
- `chart_*.png` - Chart rendering screenshots
- `edge_*.png` - Edge case screenshots
- `feature_*.png` - Feature workflow screenshots
