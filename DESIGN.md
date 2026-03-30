# Design System — ReferralQ

## Product Context
- **What this is:** Multi-specialty referral triage SaaS for BC/Canadian physicians
- **Who it's for:** Specialist physicians (urologists, GI, orthopedics) and family physicians
- **Space/industry:** Healthcare SaaS, clinical workflow tools
- **Project type:** Dashboard-heavy web app + public pathway pages

## Aesthetic Direction
- **Direction:** Industrial/Utilitarian
- **Decoration level:** Minimal
- **Mood:** Precision instrument. Trustworthy, efficient, scannable. Modern clinic, not legacy EMR. Feels like a tool built by physicians for physicians.
- **Anti-patterns:** No gradients, no decorative blobs, no rounded pill shapes (except badges), no generic SaaS card grids, no purple accents.

## Typography
- **Display/Hero:** Plus Jakarta Sans (700) — geometric, modern, warm without being soft
- **Body:** Plus Jakarta Sans (400/500) — same family for unity, excellent table readability
- **UI/Labels:** Plus Jakarta Sans (600)
- **Data/Tables:** Plus Jakarta Sans with `font-variant-numeric: tabular-nums`
- **Code:** JetBrains Mono — for referral IDs, technical display
- **Loading:** Google Fonts `https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap`
- **Scale:**
  - caption: 12px
  - body/table: 14px
  - lead: 16px
  - h4: 20px
  - h3: 24px
  - h2: 32px
  - h1/hero: 40px

## Color
- **Approach:** Restrained. One accent + clinical neutrals. Color is functional, not decorative.
- **Primary:** `#1B6B93` — deep teal, clinical trust
- **Primary Light:** `#E8F4F8` — teal wash for active states, hover, highlights
- **Primary Dark:** `#145373` — hover/pressed states
- **Neutrals:** warm grays
  - Background: `#F8F9FA`
  - Surface: `#FFFFFF`
  - Border: `#DEE2E6`
  - Muted text: `#6C757D`
  - Text: `#212529`
- **Semantic:**
  - Success: `#198754`
  - Warning: `#D4930D`
  - Error: `#C62828`
  - Info: `#0D6EFD`
- **Category badge colors** (identity-level, not just functional):
  - Hematuria: `#C2185B`
  - PSA/Prostate: `#00796B`
  - Stones: `#F57F17`
  - Incontinence: `#303F9F`
  - UTI: `#7B1FA2`
  - ED: `#616161`
  - Other: `#9E9E9E`
  - Badge style: 20% opacity background, full color text, 40% opacity border
- **Dark mode:** Reduce saturation 10-20%, swap surface to `#1E1E1E`, background to `#121212`, primary light to `#1A3A4A`

## Spacing
- **Base unit:** 4px
- **Density:** Comfortable (physicians scan fast, needs rhythm without wasting viewport)
- **Scale:** 2xs(2px) xs(4px) sm(8px) md(16px) lg(24px) xl(32px) 2xl(48px) 3xl(64px)

## Layout
- **Approach:** Grid-disciplined
- **Grid:** 12 columns, responsive breakpoints at 576/768/992/1200px
- **Max content width:** 1280px
- **Border radius:** Hierarchical
  - sm: 4px (inputs, badges)
  - md: 8px (cards, panels)
  - lg: 12px (modals, large cards)
  - full: 9999px (badges only)

## Motion
- **Approach:** Minimal-functional
- **Easing:** enter(ease-out) exit(ease-in) move(ease-in-out)
- **Duration:** hover(150ms) transition(200ms) modal(250ms)
- **Rules:** No scroll-driven animation. No entrance effects. No loading spinners longer than 200ms. Physicians don't wait for UI to finish being clever.

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-29 | Initial design system | Industrial/utilitarian aesthetic for clinical trust and efficiency. Plus Jakarta Sans for warmth without softness. Deep teal primary as healthcare standard. Category badge colors as visual identity feature. |
| 2026-03-29 | Single typeface system | Plus Jakarta Sans everywhere. Reduces cognitive load, maintains unity. Risk: less visual hierarchy than multi-font systems. Mitigated by weight variation (400-700). |
| 2026-03-29 | Category colors as identity | Muted color badges become the visual language of the product. Specialists learn to associate colors with conditions. Differentiator vs gray-badge clinical tools. |
