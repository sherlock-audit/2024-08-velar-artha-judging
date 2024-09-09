Kind Banana Sloth

Medium

# First depositor could DoS the pool

## Summary
First depositor could DoS the pool 

## Vulnerability Detail
Currently, when adding liquidity to a pool, the way LP tokens are calculated is the following: 
1. If LP total supply is 0, mint LP tokens equivalent the mint value
2. If LP total supply is not 0, mint LP tokens equivalent to `mintValue * lpSupply / poolValue`

```vyper
def f(mv: uint256, pv: uint256, ts: uint256) -> uint256:
  if ts == 0: return mv
  else      : return (mv * ts) / pv    # audit -> will revert if pv == 0
```

However, this opens up a problem where the first user can deposit a dust amount in the pool which has a value of just 1 wei and if the price before the next user deposits, the pool value will round down to 0. Then any subsequent attempts to add liquidity will fail, due to division by 0.

Unless the price goes back up, the pool will be DoS'd.

## Impact
DoS 

## Code Snippet
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/pools.vy#L178

## Tool used

Manual Review

## Recommendation
Add a minimum liquidity requirement.