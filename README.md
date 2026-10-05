# Fouse Digital

A responsive, dependency-free static website for service businesses nationwide.

## Preview

Serve the repository with any static server, for example:

```sh
python3 -m http.server 8765
```

Open `http://localhost:8765`. The site uses `index.html`, `styles.css`, and `script.js`; no build step is required.

## Connect review requests before launch

The destination is intentionally unset. No personal or placeholder email is included. While unset, the form explains that online requests are unavailable and never claims to send or store a request.

Set `REVIEW_EMAIL` at the top of `script.js` to a verified business inbox. The form will prepare a URL-encoded email containing the visitor's details. Visitors must send it in their own email app. This is not a server-backed form, and requires an email application configured on their device.

For direct submissions without an email app, replace the mailto flow with a verified HTTPS form service or backend. Validate submissions server-side, add spam protection, show success only after confirmed delivery, and update the form's delivery and privacy text to match the provider. Never put private API credentials in the browser script.

## Content and scope

- Primary CTA: free lead-path review.
- First case-study client pilot: $299 one time; availability and case-study terms confirmed before kickoff.
- Standard Lead Capture Starter: $950 one time.
- Optional ongoing care: $149/month.
- No fabricated testimonials, customer counts, case studies, or results.

Confirm the proposed package inclusions and care scope before taking paid orders. This initial site does not collect payments or publish a deployed website.

## Accessibility and behavior

Semantic page structure, visible focus states, a skip link, native form validation, keyboard-accessible FAQs, mobile navigation with Escape support, reduced-motion support, and mobile layouts. Navigation and FAQs work without JavaScript; email preparation requires JavaScript. The site uses system fonts and has no external tracking scripts.
