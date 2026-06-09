# Kalshi BTC Agent Trading System

The target is an auditable automated trading system, not a generic market
dashboard.

## Six layers

1. **Market data**
   - Kalshi event, contract, quote, size, order-book, and settlement-rule feeds
   - Coinbase and additional BTC reference feeds
   - Synchronized timestamps and SQLite history

2. **Contract intelligence**
   - Preserve Kalshi's event-to-contract hierarchy
   - Parse range, close time, BRTI observation window, fees, and tradability
   - Reject ambiguous or unsupported settlement conditions

3. **Specialist agents**
   - Quant agent: fair probability and executable edge
   - Momentum agent: short-horizon BTC direction and acceleration
   - Market-quality agent: spread, displayed depth, and stale-quote checks
   - Settlement agent: Coinbase/BRTI basis and rule risk
   - Skeptic agent: searches for reasons the apparent edge is false
   - Risk agent: position size and portfolio veto

4. **Orchestration**
   - Every agent returns a structured opinion and evidence
   - Any hard safety veto rejects the trade
   - Deterministic code calculates fees, exposure, and order size
   - Full decision record is stored before execution

5. **Paper trading and validation**
   - Replay historical snapshots with latency, spread, fees, and missed fills
   - Measure calibration, expected value, drawdown, and agent contribution
   - No strategy reaches live execution without defined acceptance criteria

6. **Execution**
   - Kalshi-authenticated limit orders only
   - Percentage-of-equity sizing
   - Per-event and total exposure limits
   - Daily loss and drawdown kill switches
   - Manual emergency stop

## Initial risk defaults

- Standard allocation: 5% of current equity
- Strong edge: 7.5%
- Exceptional edge: 10%
- Maximum exposure per event: 10%
- Maximum total open exposure: 25%
- Daily loss stop: 10%
- Portfolio drawdown stop: 20%

These are editable policy defaults, not recommendations.

## Delivery stages

1. Read-only live recorder
2. Structured deterministic agent pipeline
3. Paper portfolio and replay
4. LLM research agents with structured outputs
5. Authenticated read-only account view
6. Explicitly enabled live execution
