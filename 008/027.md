Hot Purple Buffalo

Medium

# Hardcoded Value Breaks Core Contract Functionality

## Summary
The use of a hardcoded value for the pool id in [`apy.vy`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/api.vy) proxied calls makes every other pool in the system inaccessible.

## Vulnerability Detail
The comments indicate that `apy.vy` is the entry-point contract, which proxy's calls to core. However, each call made to `core.vy` includes a hardcoded value of 1 for the pool id:
```vyper
  return self.CORE.mint(1, base_token, quote_token, lp_token, base_amt, quote_amt, ctx)
  return self.CORE.burn(1, base_token, quote_token, lp_token, lp_amt, ctx)
  return self.CORE.open(1, base_token, quote_token, long, collateral0, leverage, ctx)
  return self.CORE.close(1, base_token, quote_token, position_id, ctx)
  return self.CORE.liquidate(1, base_token, quote_token, position_id, ctx)
```

Within each of these functions in [`core.vy`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/core.vy#L168-L172), the following checks are enforced:
```vyper
  pool       : PoolState = self.POOLS.lookup(id)
...
  assert pool.base_token  == base_token , ERR_PRECONDITIONS
  assert pool.quote_token == quote_token, ERR_PRECONDITIONS
```

However the pools contract is [designed to support](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/pools.vy#L96) multiple pools with differing pool id:
```vyper
def fresh(
  symbol     : String[65],
  base_token : address,
  quote_token: address,
  lp_token   : address) -> PoolState:
  self._INTERNAL()
  return self.insert(PoolState({
    id               : self.next_pool_id(),
...

def next_pool_id() -> uint256:
  id : uint256 = self.POOL_ID
  nxt: uint256 = id + 1
  self.POOL_ID = nxt
  return nxt
```

Thus, any user action with `core.vy` can interact only with this first pool and all pools with an id differing from 1 will be inaccessible.

## Impact
Core contract functionality is broken, leading to a DoS (which doesn't compromise funds, since pools cannot be interacted with to begin with).

## Code Snippet

## Tool used

Manual Review

## Recommendation
Add an `id: uint256` parameter to the mentioned functions of `api.vy`, and forward this value to the calls of `core.vy`, rather than hardcoding 1.