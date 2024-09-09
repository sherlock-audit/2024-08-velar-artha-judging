Hot Purple Buffalo

High

# DoS of LP Withdrawals Due to Abuse of `unlocked_reserves`

## Summary
LP withdrawals can be blocked by a malicious actor inflating the OI to intentionally increase `unlocked_reserves`.

## Vulnerability Detail
The protocol locks user deposits in order to ensure future payout obligations can be met, a key functionality outlined in the comment specifications. The `pool.vy` function [`unlocked_reserves`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/pools.vy#L125-L130) reports the token reserves not currently tied up to fulfill future payouts:

```vyper
def unlocked_reserves(id: uint256) -> Tokens:
  ps: PoolState = Pools(self).lookup(id)
  return Tokens({
    base : ps.base_reserves  - ps.base_interest,
    quote: ps.quote_reserves - ps.quote_interest,
  })
```

This function is mentioned in [`calc_burn`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/pools.vy#L216-L222) which is called when LPs are making a withdrawal:

```vyper
  unlocked: Tokens  = Pools(self).unlocked_reserves(id)
  ...
  assert uv         >= bv,             ERR_PRECONDITIONS
  assert amts.base  <= unlocked.base,  ERR_PRECONDITIONS
  assert amts.quote <= unlocked.quote, ERR_PRECONDITIONS
```

Additionally, after every user action in `core.vy` (including burn and open) an [invariants](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/core.vy#L126-L133) check is performed with similar enforcement:

```vyper
def INVARIANTS(id: uint256, base_token: address, quote_token: address):
  pool         : PoolState = self.POOLS.lookup(id)
...
  assert pool.base_reserves  >= pool.base_interest,  ERR_INVARIANTS
  assert pool.quote_reserves >= pool.quote_interest, ERR_INVARIANTS
```

Critically, the same comparison between `interest` and `reserves` is being made in both cases. Since `open` increases the `interest`, a malicious attacker can take out positions with large enough size and leverage to decrease `unlocked_reserves` to an arbitrarily small value.

As long as he is well-capitalized, he can take out equal notional size positions on both the long and short side, eliminating price fluctuations and funding payments from the cost of this attack, and locking both quote and base reserves. While he would still pay borrowing rates, as well as the initial cost of opening a position, these costs are low enough to enable him to maintain this DoS (assuming he manages his position periodically to avoid liquidation).

## Impact
With a large enough bankroll, all withdrawals can be blocked for several months at a nominal cost to the attacker. Anytime the unlocked reserves grows as a result of user actions (eg. mint, close), he can simply open more positions to extend the attack.

Withdrawals can very easily be blocked for a period of 4 hours (DoS period mentioned in the [contest rules](https://audits.sherlock.xyz/contests/526)) with a much more modest bankroll and cost of attack.

Opening new positions will also be blocked, but the blocking of withdrawals is much more problematic as this is a time-sensitive operation given fluctuating crypto prices and user liquidity needs (especially if the attack is carried out for the long durations described). This would significantly erode trust in the protocol and discourage future depositors, even after the attack has concluded.

## Code Snippet

## Tool used

Manual Review

## Recommendation
Specifically for the opening of positions, enforce a lower limit of accessible reserves in order to facilitate withdrawals even when positions can no longer be opened.

For example at the end of opening a position, consider asserting:
```vyper
  assert pool.base_reserves  >= 2*pool.base_interest,  ERR_INVARIANTS
  assert pool.quote_reserves >= 2*pool.quote_interest, ERR_INVARIANTS
```