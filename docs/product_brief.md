# Product Brief

## Goal

Build a local research terminal that helps detect early public evidence of future capital flow.

This is for the "Serenity-style" workflow:

1. identify the next AI system bottleneck;
2. find the small set of public companies exposed to it;
3. monitor public filings, press releases, earnings language, and technical events;
4. alert when a company moves from story to evidence.

## Non-Goals

- Do not clone Bloomberg.
- Do not scrape copyrighted full articles.
- Do not treat social posts as truth.
- Do not generate buy/sell orders.
- Do not optimize for many alerts.

## First Themes

- AI photonics / CPO / silicon photonics
- AI data layer / accelerated storage
- AI electrical infrastructure
- physical AI / robotics / drones
- AI-RAN and sovereign telecom
- rare-earth and supply-chain security

## Signal Hierarchy

High quality signals:

- customer prepayment
- capacity reservation
- multi-year supply agreement
- named hyperscaler / named strategic customer
- backlog and book-to-bill acceleration
- management says demand exceeds capacity
- new production order after qualification
- business segment gets broken out for the first time

Medium quality signals:

- product launch
- partnership without economics
- analyst upgrade
- conference presentation
- hiring or capex expansion

Low quality signals:

- generic AI mention
- unverifiable social-media rumor
- vague memorandum of understanding
- management hype without numbers

## Operating Question

For every alert, ask:

> Is this a hard signal that future revenue or capacity is changing, or is it only a narrative headline?

## Rerating Radar Standard

The system is not expected to identify the absolute bottom of a small-cap move.
It is expected to detect when public evidence density changes before the story becomes fully consensus.

A useful alert can be late if it is still early relative to broad market recognition. The target pattern is:

1. company moves from concept to customer validation;
2. validation moves from technical work to production qualification;
3. production qualification moves to order, lifecycle revenue, capacity reservation, or named tier-one partner;
4. price and volume confirm that the market is starting to care.

## Discovery-First Architecture

The watchlist is not a fixed universe of allowed companies.
It is a seed layer for known names and aliases.

The primary workflow is news-driven:

1. collect public evidence from wires, filings, exchange announcements, company IR pages, and vertical industry media;
2. identify articles with hard evidence regardless of whether the company is already known;
3. infer the company and create a discovered candidate;
4. attach evidence terms, source, and article link;
5. later enrich the candidate with ticker, exchange, market cap, price/volume reaction, and filing history.

OpenAI API integration should be used as a second-stage analyst for entity extraction, summarization, and industry-role classification.
It should not replace deterministic source collection, citation links, or scoreable evidence terms.
