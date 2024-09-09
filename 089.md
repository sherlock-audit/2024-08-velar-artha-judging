Kind Banana Sloth

High

# Whale LP providers can open positions on both sides to force users into high fees.

## Summary
Whale LP providers can open positions on both sides to force users into high fees.

## Vulnerability Detail
LP fees within the protocol are based on utilization percentage of the total funds in the pool. The problem is that this could easily be abused by LP providers in the following way.

Consider a pool where the majority of the liquidity is provided by a single user.
1. Users have opened positions at a relatively low utilization ratio
2. The whale LP provider opens same size positions in both directions at 1 leverage.
3. This increases everyone's fees. Given that the LP provider holds majority of the liquidity, most of the new fees will go towards them, making them a profit.

As long as the whale can maintain majority of the liquidity provided, attack remains profitable. If at any point they can no longer afford maintaining majority, they can simply close their positions without taking a loss, so this is basically risk-free.


## Impact
Loss of funds

## Code Snippet
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/params.vy#L33

## Tool used

Manual Review

## Recommendation
Consider a different way to calculate fees