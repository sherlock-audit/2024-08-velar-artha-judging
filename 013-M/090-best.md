Hot Purple Buffalo

Medium

# Loss of Funds From Profitable Positions Running Out of Collateral

## Summary
When profitable positions run out of collateral, they receive no payout, even if they had a positive PnL. This is not only disadvantageous to users, but it critically removes all liquidation incentive. These zero'd out positions will continue to underpay fees until someone liquidates the position for no fee, losing money to gas in the process.

## Vulnerability Detail
When calculating the pnl of either a long or short position that is to be closed, if the collateral drops to zero due to fee obligations then they [do not receive a payout](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/positions.vy#L295): 

```vyper
# remaining first calculating in `calc_fees`
  c0              : uint256       = pos.collateral
  c1              : Val           = self.deduct(c0,           fees.funding_paid)
  c2              : Val           = self.deduct(c1.remaining, fees.borrowing_paid)
  # Funding fees prioritized over borrowing fees.
  funding_paid    : uint256       = c1.deducted
  borrowing_paid  : uint256       = c2.deducted
  remaining       : uint256       = c2.remaining

...
# later passed to `calc_pnl`
  final  : uint256       = 0 if remaining == 0 else (
...
# longs
  payout : uint256       = self.MATH.quote_to_base(final, ctx)
...
# shorts
  payout   : uint256 = final
```

However, it's possible for a position to run out of collateral yet still have a positive PnL. In these cases, no payout is received. This [payout is what's sent](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/positions.vy#L195) to the user **or liquidator** when a position is closed:

```vyper
# longs
    base_transfer   : [self.MATH.PLUS(pnl.payout),
# shorts
    quote_transfer  : [self.MATH.PLUS(pnl.payout),
```

In these cases neither the user closing his position, nor the liquidator receives any payment. 

## Impact
While it may be intended design to penalize users for letting a position run out of collateral, this is a dangerous design choice. It's possible to end up in a situation where a position has run negative due to the funding fees and now has no incentive for liquidation. This will be the case even if it could have been profitable to liquidate this position due to the PnL of the position. 

This scenario is dependent on liquidation bots malfunctioning since the liquidatability of a position does not factor in profit (only losses). However, it is acknowledged as a possibility that this scenario may occur throughout the codebase as safeguards are introduced to protect against this scenario elsewhere. In this particular scenario, no particular safeguard exists.

These positions will continue to decay causing further damage to the system until someone is willing to liquidate the position for no payment. It is unlikely that a liquidation bot would be willing to lose money to do so and would likely require admin intervention. By the time admin intervenes, it's most likely that further losses would have already resulted from the decay of the position. 

## Code Snippet

## Tool used

Manual Review

## Recommendation
During liquidations, provide the liquidator with the remaining PnL even if the position has run negative due to fees. This will maintain the current design of penalizing negative positions while mitigating the possibility of positions with no liquidation incentive.

Alternatively, include a user's PnL in his payout even if the collateral runs out. This may not be feasible due to particular design choices to ensure the user doesn't let his position run negative.