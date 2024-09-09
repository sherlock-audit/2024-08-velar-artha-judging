Amateur Nylon Canary

Medium

# Incorrect borrowing fee calculation

## Summary
Traders with high collateral, low leverage will pay more borrowing fee than traders with low collateral, high leverage.

## Vulnerability Detail
Traders in markets can add some leverage in order to get higher profits. LPs have to lock `collateral * leverage` value token to match this leverage position. Traders have to pay some borrowing fee for the locked token. The borrowing fee should be related with locked token amount.
The problem is that the borrowing fee is related with this position's collateral amount, not related with leverage. This could cause some positions with less locked token amount need to pay more borrowing fees.
For example:
- Alice opens one long position with 50000 USDT, 2x leverage in BTC/USDT market.
- Bob opens one long position with 10000 USDT, 20x leverage in BTC/USDT market.
- Lps have to lock more BTC tokens for Bob compared with Alice's position. However, Alice has to pay more borrowing fee because she has one higher collateral amount.

```vyper
@external
@view
def calc_fees(id: uint256) -> FeesPaid:
  pos             : PositionState = Positions(self).lookup(id)
  pool            : PoolState     = self.POOLS.lookup(pos.pool)
  # Here collateral is this position's collateral.
  fees            : SumFees       = self.FEES.calc(
@>                                    pos.pool, pos.long, pos.collateral, pos.opened_at)
```
```vyper
@external
@view
def calc(id: uint256, long: bool, collateral: uint256, opened_at: uint256) -> SumFees:
    period: Period  = self.query(id, opened_at)
    P_b   : uint256 = self.apply(collateral, period.borrowing_long) if long else (
                      self.apply(collateral, period.borrowing_short) )
```
## Impact
Trading positions with less locked interest may have to pay more borrowing fee.

## Code Snippet
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/fees.vy#L263-L274

## Tool used
Manual Review

## Recommendation
Borrowing fee should be in propotion to positions' locked interest.