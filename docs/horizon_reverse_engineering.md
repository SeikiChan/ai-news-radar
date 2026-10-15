# Horizon comparison and REA evidence

Date: 2026-10-15. Reference: [Thysrael/Horizon](https://github.com/Thysrael/Horizon).

## Evidence

- REA `analyze-javascript-application` inspected the reference site's checked
  out `docs/assets/js/horizon.js` as inert JavaScript. Evidence ID:
  `ev_1a8731d3648509134c62a9fffc5991eec6860153cf811a6eea1a4692293fae8a`.
  It found the `horizon-lang` local storage preference at lines 66 and 109.
  Source inspection shows the same script decorates score badges and switches
  English/Chinese pages. This is presentation code, not the scoring pipeline.
- The open-source [orchestrator](https://github.com/Thysrael/Horizon/blob/main/src/orchestrator.py)
  implements URL deduplication, optional AI topic merging, per-profile filters,
  and balanced digest selection before summary delivery.
- Horizon's [profile contract](https://github.com/Thysrael/Horizon/blob/main/docs/profiles.md)
  separates editorial rules from a reader's thresholds and source settings.
  Its output blocks can request historical or web context with cited results.
- Our pipeline has deterministic finance evidence scoring and many downstream
  checks, but the previous brief ranked stored candidates solely by score.
  It could put an old story or several items from one company at the top.

REA's static result establishes script structure and storage references. It
does not prove browser execution or Python pipeline behavior. The latter
conclusions come from the referenced source files and local tests.

## Implemented response

1. The daily brief uses a 72-hour publication window. If the publisher gives
   no date, it uses the earliest recorded retrieval time for a repeated article.
   Historical rows remain
   in local storage. Legacy rows with neither timestamp stay visible because
   their age cannot be established.
2. The brief orders by research action before score. A financial health veto
   therefore keeps a high-scoring but unsafe candidate below actionable ideas.
3. A digest gives each identified company one lead. It retains other articles
   as separately linked updates and does not claim that they are duplicates.
   The full current research queue remains available under Opportunities.
4. The Markdown and JSON exports use the same digest selection as the web brief.

## Next decisions

- Add a source configuration wizard only after a small set of finance-specific
  presets has been validated. A general AI profile framework would introduce
  expensive scoring calls and make the hard-signal rubric harder to audit.
- Consider cross-source event clustering after assembling a labeled sample of
  true and false duplicates. Sharing a company or a broad headline term is not
  sufficient evidence that two disclosures are the same event.
- Validate alert quality with the existing forward-return report before adding
  more sources or delivery channels. Measure precision, false positives,
  source failure rates, and time from publication to first alert.
