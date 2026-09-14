---
name: Clinical Recovery Precision
colors:
  surface: '#effcff'
  surface-dim: '#b3e2ed'
  surface-bright: '#effcff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#def8ff'
  surface-container: '#cbf5ff'
  surface-container-high: '#c1f0fb'
  surface-container-highest: '#bbeaf6'
  on-surface: '#001f25'
  on-surface-variant: '#3f484d'
  inverse-surface: '#00363e'
  inverse-on-surface: '#d5f7ff'
  outline: '#6f787e'
  outline-variant: '#bec8cd'
  surface-tint: '#006782'
  primary: '#00647f'
  on-primary: '#ffffff'
  primary-container: '#1e7e9d'
  on-primary-container: '#fbfdff'
  inverse-primary: '#80d1f3'
  secondary: '#006781'
  on-secondary: '#ffffff'
  secondary-container: '#89ddfd'
  on-secondary-container: '#00627a'
  tertiary: '#7a5500'
  on-tertiary: '#ffffff'
  tertiary-container: '#9a6c00'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#bbe9ff'
  primary-fixed-dim: '#80d1f3'
  on-primary-fixed: '#001f29'
  on-primary-fixed-variant: '#004d63'
  secondary-fixed: '#b9eaff'
  secondary-fixed-dim: '#7ed2f2'
  on-secondary-fixed: '#001f29'
  on-secondary-fixed-variant: '#004d61'
  tertiary-fixed: '#ffdeab'
  tertiary-fixed-dim: '#ffba32'
  on-tertiary-fixed: '#271900'
  on-tertiary-fixed-variant: '#5f4100'
  background: '#effcff'
  on-background: '#001f25'
  surface-variant: '#bbeaf6'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 2rem
    fontWeight: '600'
    lineHeight: 2.5rem
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 1.5rem
    fontWeight: '600'
    lineHeight: 2rem
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 1.25rem
    fontWeight: '600'
    lineHeight: 1.75rem
    letterSpacing: -0.01em
  title-sm:
    fontFamily: Inter
    fontSize: 1rem
    fontWeight: '600'
    lineHeight: 1.5rem
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Inter
    fontSize: 1rem
    fontWeight: '400'
    lineHeight: 1.5rem
  body-md:
    fontFamily: Inter
    fontSize: 0.875rem
    fontWeight: '400'
    lineHeight: 1.375rem
  body-sm:
    fontFamily: Inter
    fontSize: 0.75rem
    fontWeight: '400'
    lineHeight: 1.125rem
  label-md:
    fontFamily: Inter
    fontSize: 0.8125rem
    fontWeight: '500'
    lineHeight: 1.125rem
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 0.6875rem
    fontWeight: '600'
    lineHeight: 1rem
    letterSpacing: 0.04em
  metric-tabular:
    fontFamily: Inter
    fontSize: 1.75rem
    fontWeight: '600'
    lineHeight: 2rem
    letterSpacing: -0.03em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1.25rem
  margin: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
---

## Brand & Style

This design system establishes an ultra-refined, high-fidelity administrative environment for clinicians managing post-operative knee replacement recoveries. The design movement is grounded in **Precision Clinical Minimalism**: zero dark surfaces, pristine high-key contrast, zero decorative visual noise, and deliberate chromatic restraints that keep cognitive load to an absolute minimum during intensive patient triage.

The aesthetic evokes clinical authority, hygiene, and calmness. It trades heavy drop shadows and saturated fills for hairline division, meticulous typographic hierarchy, and surgical data density. Clinicians operate within an interface that feels like an advanced clinical workstation: quiet, fast, orderly, and deeply trustworthy.

Key aesthetic tenants:
- **High-Key Luminescence:** The entire canvas is flooded with daylight tones. Contrast is delivered entirely through precise typography and hairline structural borders rather than dark blocks or heavy surfaces.
- **Severity-First Hierarchy:** Saturated color is treated as an alert state. Warm amber and muted clinical red are strictly reserved for triage urgency; neutral and deep teal govern everyday administrative structure.
- **Airy Density:** Ample interior element padding paired with strict vertical alignment allows vast amounts of tabular biometric telemetry (range of motion, pain trajectory, adherence) to remain immediately scannable without visual fatigue.

## Colors

The color palette is built exclusively around light-mode clarity, leaning on cold surgical undertones to maintain clinical rigor while avoiding harsh monochrome deadness.

### Application Roles
- **Canvas Base (`#F7F8FA`):** The non-intrusive foundation for the entire viewport. It sets an intentional 1.5% contrast offset against all working surfaces.
- **Pure Surfaces (`#FFFFFF`):** Applied to cards, panels, the top navigation bar, the sidebar rail, and table rows to elevate interactive planes effortlessly against the off-white canvas.
- **Structural Borders (`#E4E8EC`):** A hairline 1px container delineation across all components, replacing blurred dropshadows entirely.
- **Apollo Deep Teal (`#023B44`):** The primary typographic ink. Provides near-black WCAG AAA contrast for titles, metric readings, and key tabular values without the brutal harshness of `#000000`.
- **Slate Grey (`#6B7580`):** Secondary ink used strictly for metadata, baseline labels, inactive icons, and timestamps.
- **Apollo Teal (`#2582A1`):** Action drivers, selected tab indicators, active patient states, and real-time synchronization beacons.
- **Blue Chill (`#097895`):** Hover and focus rings, active pressed states, and secondary interactive borders.
- **Apollo Mango (`#FDB931`):** Restricted entirely to moderate review states, protocol deviations, or non-acute check-in anomalies.
- **Muted Clinical Red (`#C4544A`):** Exclusively reserved for acute triage escalation (e.g., severe joint swelling, critical pain spikes, suspected DVT markers). Never utilized for decorative error boundaries or destructive action buttons.

## Typography

Typographic execution relies on **Inter**, configured with open source OpenType features tailored to clinical data: `tnum` (tabular numbers) and `cv05` / `cv08` enabled across the dashboard to ensure column alignment in telemetry tables (flexion/extension angles, surgical postoperative day count, recovery delta scores).

### Hierarchy & Rules
- **Tabular Rigor:** All numeric figures in triage queues, metric cards, and charts must utilize `font-feature-settings: "tnum" 1` to prevent jitter during live data feeds.
- **Display Weights:** Headlines never exceed a weight of `600`. Heavy black weights (`800`+) are avoided to preserve the light, clinical baseline.
- **Labels & Microcopy:** `label-sm` utilizes subtle uppercase tracking for table headers, metadata caps, and status tags (`letterSpacing: 0.04em`) to maintain sharp differentiation against standard sentence-cased medical notes.
- **Reading Contrast:** Primary clinical titles use `#023B44`, maintaining an 11:1 contrast ratio against white containers. Secondary labels utilize `#6B7580`, yielding a 4.6:1 ratio, strictly adhering to WCAG AA for micro-telemetry.

## Layout & Spacing

The layout is built on a responsive 12-column clinical grid with a permanent collapsed vertical command rail and a horizontal top operational strip.

### Screen Layout Architecture
- **Navigation Rail:** 64px width fixed left rail, anchored to the viewport height. Pure white background, separated from the canvas by a crisp `1px solid #E4E8EC` right border.
- **Top Bar:** 56px height pinned top strip spanning the rest of the viewport width. Houses active clinical tenant selection, current facility department, and live telemetry synchronization heartbeat indicator.
- **Main Canvas:** Dynamic scroll container utilizing `margin: 1.5rem` outer padding on standard desktop viewports (1440px+), scaling down to `1rem` on compact hospital tablet displays (1024px).
- **Grid Cadence:** Primary triage dashboards divide patient metrics into 4-column cards (spanning 3 columns each on 12-col grids) or 3-column splits for comparative recovery charts against the primary queue.
- **Row Spacing:** Data tables and triage lists utilize an unvarying row height of 56px to ensure predictable targeting on hospital tablet touch screens and ergonomic eye-tracking across hundreds of recovery records.

## Elevation & Depth

This design system replaces traditional drop shadows with **Low-Contrast Outlines and Structural Planar Layering**. Dark shadows conflict with the sterile, light-flooded aesthetic required of clinical dashboards.

### Elevation Principles
- **Flat 0 (Canvas Base):** `#F7F8FA`. No elevation.
- **Flat 1 (Primary Functional Surfaces):** `#FFFFFF` paired with an explicit `1px solid #E4E8EC` perimeter border. Used for metric cards, table headers, sidebar, topbar, and drawer containers. No box shadow is applied.
- **Hover & Interaction Tier:** When cards or table rows become active or hovered, they do not lift or project shadows. Instead, their border transitions smoothly to `1px solid #2582A1` (or `#097895`), accompanied by a subtle background shift to `#FAFCFD`.
- **Modals and Clinical Flyouts:** Clinical drill-down sheets and drawer panels utilize a razor-thin ambient shadow: `box-shadow: 0px 8px 24px -4px rgba(2, 59, 68, 0.06)`, maintaining the cool `#023B44` tint rather than neutral carbon blacks.

## Shapes

The design system employs a **Soft (0.25rem / 4px to 0.5rem / 8px)** shape philosophy. Soft corners signal precision, high data density, and technical calibration, moving away from hyper-rounded consumer software aesthetics toward an instrument-grade interface.

### Border Radius Rules
- **Base Components (`rounded` / 4px):** Form controls, text input boxes, dropdown menus, table row highlight enclosures, and secondary outline buttons.
- **Containers (`rounded-lg` / 8px):** Metric monitoring cards, patient profile summaries, triage tables, and modal containers.
- **Status Pills (`rounded-full` / 9999px):** Triage severity indicators and live sync indicators exclusively use full pill-capsules to clearly separate status indicators from rectangular interactive cards and buttons.

## Components

### 1. Minimalist Collapsed Left Navigation
- **Dimensions & Surface:** 64px width, `#FFFFFF` background, `1px solid #E4E8EC` right border.
- **Items:** 40px × 40px icon containers with 4px border radius.
- **Active State:** Icon switches from `#6B7580` to `#2582A1`. An absolute 3px wide vertical indicator bar in `#2582A1` sits flush against the left edge of the rail. Tooltip flyouts appear on hover in `#023B44` with white micro-text.

### 2. Clinical Topbar
- **Structure:** 56px height, pure `#FFFFFF` background, hairline bottom border (`#E4E8EC`).
- **Live Sync Beacon:** Displays a pulsating indicator with a 6px solid teal circle (`#2582A1`) surrounded by an animated semi-transparent ring (`rgba(37, 130, 161, 0.2)`), paired with `body-sm` text: "Live Telemetry Sync".
- **Tenant Selector:** Clean outline trigger with a 1px `#E4E8EC` border, housing hospital location, department title in `#023B44`, and a subtle chevron icon.

### 3. Metric Cards
- **Structure:** White container, 8px radius, 1px `#E4E8EC` border, `space-md` internal padding.
- **Content Flow:** Upper label in `label-sm` slate text (`#6B7580`) uppercase; primary reading in `metric-tabular` deep teal (`#023B44`); trailing trend micro-badge denoting post-op deviation (e.g., "+14° Flexion").

### 4. Triage Queue Rows & Severity Pills
- **Ordering:** Triage queues are strictly grouped by qualitative severity tiers (Critical -> Attention -> On Track). No synthetic numerical risk scores.
- **Row Styling:** `#FFFFFF` background with alternating hover state `#FAFCFD`. Hairline divider `#E4E8EC` between rows.
- **Severity Badges:**
  - *Emergency Tier:* Pill tag, light muted red background (`rgba(196, 84, 74, 0.1)`), 1px solid `rgba(196, 84, 74, 0.25)`, text `#C4544A` (`label-sm`, weight 600).
  - *Review Tier:* Pill tag, light mango background (`rgba(253, 185, 49, 0.15)`), 1px solid `rgba(253, 185, 49, 0.4)`, text `#A56F00` (optimized for readability against white).
  - *On-Track Tier:* Pill tag, subtle teal wash (`rgba(37, 130, 161, 0.08)`), 1px solid `rgba(37, 130, 161, 0.2)`, text `#2582A1`.

### 5. Buttons & Controls
- **Outline Buttons (Primary):** White background, 1px solid `#2582A1`, text `#2582A1`, 4px radius. On hover: background `#F0F7F9`, border `#097895`, text `#097895`.
- **Secondary Buttons:** White background, 1px solid `#E4E8EC`, text `#023B44`. On hover: border `#6B7580`.
- **Form Inputs & Search:** `#FFFFFF` background, 1px solid `#E4E8EC`, 4px radius, placeholder in `#6B7580`. Focus ring: 1px solid `#2582A1` with an outer glow of `0 0 0 2px rgba(37, 130, 161, 0.15)`.