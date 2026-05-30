# Signal Model

## Scoring

Start from zero. Add signal weights based on title, summary, and source metadata.

| Signal | Weight |
| --- | ---: |
| mass production | 30 |
| high-volume production | 28 |
| customer prepayment / advance payment | 25 |
| lifecycle revenue / lifetime revenue | 24 |
| volume production | 24 |
| design win | 22 |
| capacity reservation / capacity commitment | 22 |
| production order / purchase order | 22 |
| manufacturing readiness / production qualification | 20 |
| multi-year agreement / long-term agreement | 18 |
| book-to-bill / backlog acceleration | 18 |
| follow-up order / customer ramps / ramp production | 18 |
| pre-production units | 16 |
| demand exceeds capacity / supply constrained | 16 |
| field trials | 14 |
| named hyperscaler / strategic customer | 14 |
| qualification to production | 14 |
| external light source / 1.6T / 6.4T | 10-12 |
| data center demand | 10 |
| AI customer / AI infrastructure | 8 |
| silicon photonics / CPO / optical interconnect | 8 |
| new product ramp | 8 |
| analyst upgrade / price target | 4 |
| generic AI mention | 2 |

## Penalties

| Risk | Penalty |
| --- | ---: |
| common stock offering / ATM / dilution | -18 |
| going concern / liquidity warning | -25 |
| revenue miss / guidance cut | -16 |
| lawsuit / investigation | -12 |
| generic sponsored content | -8 |

## Alert Bands

| Score | Band | Meaning |
| ---: | --- | --- |
| 35+ | hard alert | Read now. Possible thesis-changing item. |
| 20-34 | watch alert | Add to research queue. |
| 10-19 | weak alert | Save, but do not interrupt. |
| < 10 | ignore | Noise unless repeated. |

## False Positive Rules

- A press release with only "AI" and no customer, money, capacity, order, or backlog is noise.
- A partnership with no economics is medium quality at best.
- A stock already up 300%+ should require stronger evidence before alerting.
- OTC and foreign ordinary names need a liquidity warning in the output.
- A strategic counterparty name alone is not enough. It only adds weight when the article also contains order, production, revenue, qualification, capacity, or similar evidence language.
