# Rhize Outreach Guide

## First time

Run `/rhize-outreach:setup`. Review the prerequisite check and selected private data location, then choose “Install pinned workflow” to fetch the pinned runtime and prepare local storage. The wizard does not request email, Supabase, Vercel, DataForSEO, or other credentials.

## Run a business through the workflow

1. Start `/rhize-outreach:run` and leave its terminal open. The local UI opens in your default browser.
2. Choose an area and an industry informed by Rhize's experience profile. Review candidates and their evidence, or add a business you found manually. Select one business to start its workflow.
3. Review the research, website concept, and audit. The background agent cannot run an actual design-system CLI or inspect a rendered page with a browser, so perform that visual review yourself.
4. Accept the website/audit package only when it is ready. This resumes the email draft. Inspect and revise it before marking it reviewed. Nothing sends automatically.

The graph saves progress and resumes after a service restart. If the task is blocked, run `/rhize-outreach:doctor` and follow the reported cause.

## Choose the review checkpoint

Use `review-outreach-package` for the website concept and audit. Use `review-outreach-email`
for the personalized message, sender/recipient, booking link and accepted-package consistency.
Name the checkpoint explicitly when a request covers both. Reviewing or accepting copy never
sends the message or publishes a website.

## What this does not do

The current plugin is local and draft-only: no shared Supabase data, no GHL/Gmail delivery, no Vercel publishing, and no automated post-call bottleneck report. An audit or a draft is not proof of prospect consent or of any promised marketing result.

## Frontend package review

A tool-equipped Claude or Codex host can use `rhize-devflow:frontend-development` to select
relevant design/motion/craft skills and `browser-qa` to inspect the current candidate's rendered
pages. Record actual skill use and URL/build, viewport, state/action and artifact evidence.
Missing or disabled capabilities remain unavailable. The background executor still cannot run
these external design/browser workflows; installing host skills does not upgrade it or clear
the existing human package acceptance gate.
