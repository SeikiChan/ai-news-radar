# Options Flow GitHub Scan

Date: 2026-05-27 local

## Verdict

No high-star open-source project gives free, reliable, real-time unusual-options tape comparable to FlowAlgo, Unusual Whales, or Bloomberg-style flow.

The practical free layer is a public options-chain anomaly scanner:

- Use option chain snapshots.
- Flag volume, open interest, premium, and DTE anomalies.
- Treat the result as market-behavior evidence, not proof of institutional buying.
- Keep paid/social flow APIs as a higher-quality optional layer.

## Repositories Checked

| Repository | Stars checked | Verdict |
| --- | ---: | --- |
| `OpenBB-finance/OpenBB` | 68,189 | Strong open-source finance platform. Useful design reference for broad analyst data plumbing, not a free unusual-flow tape by itself. |
| `unusual-whales/unusual-whales-official-mcp` | 56 | Official MCP wrapper, but it depends on Unusual Whales API access. Good future connector if the user has credentials. |
| `erikmaday/unusual-whales-mcp` | 60 | Community MCP wrapper for Unusual Whales API. Same credential dependency. |
| `SC4RECOIN/FlowAlgo-Options-Trader` | 145 | Uses FlowAlgo/Alpaca style flow; old and depends on external flow access. Not suitable as a direct free source. |
| `GBERESEARCH/volvisualizer` | 48 | Useful options-chain/IV reference, not unusual order-flow feed. |
| `sudoshu/OptionsHacker` | 65 | ThinkScript/options-chain study reference, not a server-side data source. |
| `SweepCast/Unusual-Options` | 1 | Vendor information repo, not a usable open-source feed. |

## Implemented In This System

`src/abnormal_news_radar/options_chain.py` adds the free public layer:

- Fetch Yahoo public option chain snapshots.
- Flag contracts with volume >= 1,000.
- Require estimated premium >= $250,000.
- Prefer volume/open-interest >= 1.0.
- Prefer <= 45 DTE and near-the-money contracts.
- Merge the result into the existing `options_flow` evidence object.

This does not claim to identify the buyer, seller, sweep route, or institution. It only says the public chain shows abnormal activity worth using as a supporting clue.
