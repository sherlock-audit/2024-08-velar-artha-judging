Kind Banana Sloth

High

# User could have impossible to close position if funding fees grow too big.

## Summary
User could have impossible to close position if funding fees grow too big.

## Vulnerability Detail
In order to prevent positions from becoming impossible to be closed due to funding fees surpassing collateral amount, there's the following code which pays out funding fees on a first-come first-serve basis.
```vyper
    # 2) funding_received may add up to more than available collateral, and
    #    we will pay funding fees out on a first come first serve basis
                                    min(fees.funding_received, avail) )
```

However, this wrongly assumes that the order of action would always be for the side which pays funding fees to close their position before the side which claims the funding fee.

Consider the following scenario:
1. There's an open long (for total collateral of `X`) and an open short position. Long position pays funding fee to the short position.
2. Eventually the funding fee grows larger than the whole long position (`X + Y`). it is due liquidation, but due to bot failure is not yet liquidated (which based on comments is expected and possible behaviour)
3. A new user opens a new long position, once with `X` collateral. (total quote collateral is currently 2X) 
4. The original long is closed. This does not have an impact on the total quote collateral, as it is increased by the `funding_paid` which in our case will be counted as exactly as much as the collateral (as in these calculations it cannot surpass it). And it then subtracts that same quote collateral.
5. The original short is closed. `funding_received` is calculated as `X + Y` and therefore that's the amount the total quote collateral is reduced by. The new total quote collateral is `2X - (X + Y) = X - Y`. 
6. Later when the user attempts to close their position it will fail as it will attempt subtracting `(X - Y) - X` which will underflow.

Marking this as High, as a user could abuse it to create a max leverage position which cannot be closed. Once it is done, because the position cannot be closed it will keep on accruing funding fees which are not actually backed up by collateral, allowing them to double down on the attack.

## Impact
Loss of funds

## Code Snippet
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/positions.vy#L250
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/positions.vy#L263
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/positions.vy#L211

## Tool used

Manual Review

## Recommendation
Fix is non-trivial.