Kind Banana Sloth

Medium

# Liquidity providers can remove liquidity to force positions into high fees

## Summary
Liquidity providers can remove liquidity to force positions into high fees

## Vulnerability Detail
Within the protocol, position fees are based on utilization of the total LP amount.
```vyper
def dynamic_fees(pool: PoolState) -> DynFees:
    long_utilization : uint256 = self.utilization(pool.base_reserves, pool.base_interest)
    short_utilization: uint256 = self.utilization(pool.quote_reserves, pool.quote_interest)
    borrowing_long   : uint256 = self.check_fee(
      self.scale(self.PARAMS.MAX_FEE, long_utilization))
    borrowing_short  : uint256 = self.check_fee(
      self.scale(self.PARAMS.MAX_FEE, short_utilization))
    funding_long     : uint256 = self.funding_fee(
      borrowing_long, long_utilization,  short_utilization)
    funding_short    : uint256 = self.funding_fee(
      borrowing_short, short_utilization,  long_utilization)
    return DynFees({
        borrowing_long : borrowing_long,
        borrowing_short: borrowing_short,
        funding_long   : funding_long,
        funding_short  : funding_short,
    })
```
The problem is that this number is dynamic and LP providers can abuse it at any point

Consider the following scenario:
1. There's a lot of liquidity in the pool
2. User opens a position for a fraction of it, expecting low fees due the low utilization
3. LP providers withdraw most of liquidity, forcing high utilization ratio and ultimately high fees.


## Impact
Loss of funds


## Code Snippet
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/params.vy#L33

## Tool used

Manual Review

## Recommendation
Consider using a different way to calculate fees which is not manipulatable by the LP providers.