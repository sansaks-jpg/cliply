---
name: Monochrome Logic
colors:
  surface: '#131315'
  surface-dim: '#131315'
  surface-bright: '#39393b'
  surface-container-lowest: '#0e0e10'
  surface-container-low: '#1c1b1d'
  surface-container: '#201f22'
  surface-container-high: '#2a2a2c'
  surface-container-highest: '#353437'
  on-surface: '#e5e1e4'
  on-surface-variant: '#c4c7c8'
  inverse-surface: '#e5e1e4'
  inverse-on-surface: '#313032'
  outline: '#8e9192'
  outline-variant: '#444748'
  surface-tint: '#c6c6c7'
  primary: '#ffffff'
  on-primary: '#2f3131'
  primary-container: '#e2e2e2'
  on-primary-container: '#636565'
  inverse-primary: '#5d5f5f'
  secondary: '#c6c6cf'
  on-secondary: '#2f3037'
  secondary-container: '#45464e'
  on-secondary-container: '#b4b4bd'
  tertiary: '#ffffff'
  on-tertiary: '#2f3131'
  tertiary-container: '#e2e2e2'
  on-tertiary-container: '#636565'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e2e2e2'
  primary-fixed-dim: '#c6c6c7'
  on-primary-fixed: '#1a1c1c'
  on-primary-fixed-variant: '#454747'
  secondary-fixed: '#e2e1eb'
  secondary-fixed-dim: '#c6c6cf'
  on-secondary-fixed: '#1a1b22'
  on-secondary-fixed-variant: '#45464e'
  tertiary-fixed: '#e2e2e2'
  tertiary-fixed-dim: '#c6c6c7'
  on-tertiary-fixed: '#1a1c1c'
  on-tertiary-fixed-variant: '#454747'
  background: '#131315'
  on-background: '#e5e1e4'
  surface-variant: '#353437'
typography:
  display:
    fontFamily: Plus Jakarta Sans
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.04em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: '1.4'
  body-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  label-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.4'
    letterSpacing: 0.02em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 48px
  max-width: 1200px
---

## Brand & Style

This design system is built on the principles of **Utility Minimalism**. It moves away from the saturated, neon-heavy aesthetics common in modern AI tools, opting instead for a professional, high-fidelity environment that mirrors industry leaders like Linear and Vercel.

The brand personality is **Precise, Authentic, and Decisive**. It targets power users who value speed and clarity over visual spectacle. The aesthetic is defined by a rigorous monochrome palette, generous negative space, and a systematic approach to hierarchy that eliminates visual noise. The goal is to evoke a sense of high-end craftsmanship where the tool recedes to let the user's work take center stage.

## Colors

The palette is strictly achromatic, leveraging a deep black foundation to create a "void" where content appears to float. 

- **Primary:** Pure White (#FFFFFF) is reserved for high-priority text, primary actions, and critical iconography.
- **Secondary:** Zinc Silver (#A1A1AA) handles secondary information and muted states.
- **Surface:** The background is an absolute black (#000000) for OLED efficiency and depth, while UI containers use a slightly elevated zinc-dark (#09090B).
- **Accents:** No hue-based accents are used. Interactive states are communicated through opacity shifts, inverted colors, or subtle border highlights.

## Typography

Using **Plus Jakarta Sans** as the sole typeface ensures a modern, geometric clarity. The system relies on weight and contrast rather than size variety to establish hierarchy.

Large display headings use tight tracking and heavy weights to feel impactful yet refined. Body text is kept at a comfortable 14px or 16px to maintain an "app-like" utility feel. Labels are frequently set in semi-bold at 12px for technical metadata and UI controls. White space between text blocks should be intentional and aggressive to prevent "slop" and clutter.

## Layout & Spacing

The layout follows a **Rigid Grid** philosophy. Content is contained within a 12-column grid on desktop with generous 24px gutters.

- **Desktop:** 12 columns, 48px side margins. Elements should align to the grid, often spanning 4 or 6 columns for balanced symmetry.
- **Mobile:** 4 columns, 16px side margins.
- **Rhythm:** All spacing (padding, margins, gaps) must be multiples of 4px. Use larger gaps (40px+) between major sections to emphasize the premium, spacious feel of the design system.

## Elevation & Depth

Depth is achieved through **Tonal Layering** and **Micro-Borders** rather than traditional shadows.

- **Tier 0 (Background):** Absolute Black (#000000).
- **Tier 1 (Cards/Panels):** Zinc-Dark (#09090B) with a 1px solid border (#27272A).
- **Tier 2 (Popovers/Modals):** Zinc-Elevated (#18181B) with a slightly brighter 1px border (#3F3F46).

Shadows, if used at all, should be "Invisible Shadows"—extreme diffusion (64px+ blur) with very low opacity (15%) to suggest a subtle lift without appearing heavy or artificial.

## Shapes

The shape language is **Soft-Geometric**. Based on the logo's squircle-inspired container, the design system utilizes a controlled corner radius that suggests approachability within a professional framework.

- **Standard Elements:** 0.25rem (4px) for input fields, buttons, and small UI elements.
- **Containers:** 0.75rem (12px) for cards, modals, and major sections to echo the logo's outer profile.
- **Icons:** Should use a consistent 2px stroke weight to match the precision of the typography.

## Components

- **Buttons:** Primary buttons are Solid White with Black text. Secondary buttons use a Ghost style—transparent background with a Zinc border that fills slightly on hover. 
- **Input Fields:** Minimalist design with only a bottom border or a very subtle 1px frame. Focus states use a sharp White border transition. No glow effects.
- **Chips:** Small, pill-shaped tags with Zinc backgrounds and White text. They should feel like metadata rather than decorative elements.
- **Cards:** Flat surfaces with 1px borders. Interactive cards should slightly brighten their border color on hover rather than scaling or adding a shadow.
- **Lists:** Clean rows separated by 1px dividers (#18181B). Hover states should use a subtle background tint (#09090B) to guide the eye.
- **Iconography:** Use "Linear" style icons with no fills. Icons should be monochrome and perfectly aligned to a 20px or 24px grid.
