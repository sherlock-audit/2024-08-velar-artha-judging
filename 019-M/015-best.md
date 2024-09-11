Amateur Nylon Canary

Medium

# Last LP in each pool may lose a few amount of reserve.

## Summary
Last Lp's burn() may be reverted if malicious users leave 1 wei share in this pool.

## Vulnerability Detail
At the end of each core function, we will trigger Fee's update. In the fee's update, we need to calculate the Lp tokens' utilization. The problem is that the utilization calculation will be reverted if reserves is not zero but less than 100.

This scenario is possible, especially when malicious users intent to do this.
- Malicious users can mint one very small share in one market, for example, 1 share.
- When last LP wants to burn his shares, the left reserve will be one very small amount but larger than 0. Because malicious users hold 1 share.
- When we want to update the fees, the transaction will be reverted because the utilization calculation will be reverted.

The last LP holder can still burn his most share via leaving some amount of share(reserves) into the pool.
Although this amount is not large, considering that this case could happen in every market, more LPs may take some loss because of this finding.

```vyper
@internal
@pure
def utilization(reserves: uint256, interest: uint256) -> uint256:
    # Then the last LP want to withdraw, will be reverted.
@>    return 0 if (reserves == 0 or interest == 0) else (interest / (reserves / 100))
```

```vyper
@external
@view
def calc_mint(
  id          : uint256,
  base_amt    : uint256,
  quote_amt   : uint256,
  total_supply: uint256,
  ctx         : Ctx) -> uint256:
  pv: uint256 = self.MATH.value(Pools(self).total_reserves(id), ctx).total_as_quote
  mv: uint256 = self.MATH.value(Tokens({base: base_amt, quote: quote_amt}), ctx).total_as_quote
  return Pools(self).f(mv, pv, total_supply)

# ts --> total supply
@external
@pure
def f(mv: uint256, pv: uint256, ts: uint256) -> uint256:
  if ts == 0: return mv
  else      : return (mv * ts) / pv

```
## Impact
Last LP holder in each pool may have to leave a few amount of reserve in this market.

## Code Snippet
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/params.vy#L57-L63

## Tool used

Manual Review

## Recommendation
Make sure the utilization calculation will not be reverted.