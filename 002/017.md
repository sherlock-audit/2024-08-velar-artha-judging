Amateur Nylon Canary

Medium

# Healthy positions may be liquidated because of inappropriate judgment

## Summary
Healthy positions may be liquidated in one special case

## Vulnerability Detail
In `is_liquidatable()`, there are some comments about the position's health. `A position becomes liquidatable when its current value is less than
    a configurable fraction of the initial collateral`. 
The problem is that when `pnl.remaining` equals `required`, this position should be healthy and cannot be liquidated. But this edge case will be though as unhealthy and can be liquidated.

```vyper
@external
@view
def is_liquidatable(position: PositionState, pnl: PnL) -> bool:
    """
    A position becomes liquidatable when its current value is less than
    a configurable fraction of the initial collateral, scaled by
    leverage.
    """
    percent : uint256 = self.PARAMS.LIQUIDATION_THRESHOLD * position.leverage
    required: uint256 = (position.collateral * percent) / 100
    return not (pnl.remaining > required)
```

## Impact
Healthy positions may be liquidated and take some loss.

## Code Snippet
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/params.vy#L117-L138

## Tool used

Manual Review

## Recommendation
```diff
-    return not (pnl.remaining > required)
+    return not (pnl.remaining >= required)
```