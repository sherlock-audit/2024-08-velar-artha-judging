Amateur Nylon Canary

Medium

# Penalized funding received token will be locked in the contract

## Summary
If one position's funding received is penalized, these funding received will be locked in the contract.

## Vulnerability Detail
When we close one position, we will check the remaining collateral after we deduct the borrowing fee and possible funding paid. If there is not left collateral, the funding received will be set to 0 as one penalty.
In this case, the trader will not receive the funding received. And the `funding_received_want` will not be deducted from base_collateral considering one long position.
The problem is that traders with short position will still pay funding fees. This will cause `funding_received_want` will be left and anyone cannot withdraw this part.

```vyper
@external
@view
def calc_fees(id: uint256) -> FeesPaid:
  pos             : PositionState = Positions(self).lookup(id)
  pool            : PoolState     = self.POOLS.lookup(pos.pool)
  # Here collateral is this position's collateral.
  fees            : SumFees       = self.FEES.calc(
                                    pos.pool, pos.long, pos.collateral, pos.opened_at)
  # @audit-fp funding_paid, borrowing_paid will be paid via collateral.
  c0              : uint256       = pos.collateral
  # Funding paid and borrowing paid will be paid via the collateral.
  c1              : Val           = self.deduct(c0,           fees.funding_paid)
  c2              : Val           = self.deduct(c1.remaining, fees.borrowing_paid)
  # Funding fees prioritized over borrowing fees.
  # deduct funding fee at first, and then deduct borrowing fee.
  funding_paid    : uint256       = c1.deducted
  borrowing_paid  : uint256       = c2.deducted
  # collateral - funding paid fee - borrowing fee
  remaining       : uint256       = c2.remaining
  funding_received: uint256       = 0 if remaining == 0 else (
                                    min(fees.funding_received, avail) )
```
```vyper
@external
@view
def value(id: uint256, ctx: Ctx) -> PositionValue:
  # Get position state.
  pos   : PositionState = Positions(self).lookup(id)
  # All positions will eventually become liquidatable due to fees.
  fees  : FeesPaid      = Positions(self).calc_fees(id)
  pnl   : PnL           = Positions(self).calc_pnl(id, ctx, fees.remaining)

  deltas: Deltas        = Deltas({
    base_interest   : [self.MATH.MINUS(pos.interest)], # unlock LP tokens.
    quote_interest  : [],
    base_transfer   : [self.MATH.PLUS(pnl.payout),
                       self.MATH.PLUS(fees.funding_received)],
    base_reserves   : [self.MATH.MINUS(pnl.payout)], # base reserve: when traders win, they will get LP's base token,
                                                     # funding fee is not related with LP holders.

@>    base_collateral : [self.MATH.MINUS(fees.funding_received)], # ->
  ...
  }) if pos.long else ...

```

## Impact
Penalized funding received token will be locked in the contract

## Code Snippet
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/positions.vy#L242-L272

## Tool used

Manual Review

## Recommendation
Once the funding received is penalized, we can consider to transfer this part funds to collector directly.