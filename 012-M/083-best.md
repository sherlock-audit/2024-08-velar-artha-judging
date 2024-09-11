Hot Purple Buffalo

Medium

# Funding Paid != Funding Received

## Summary
Due to special requirements around receiving funding fees for a position, the funding fees received can be less than that paid. These funding fee payments are still payed, but a portion of them will not be withdrawn, and become stuck funds. This also violates the contract specification that `sum(funding_received) = sum(funding_paid)`.

## Vulnerability Detail
In [`calc_fees`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/positions.vy#L257-L263) there are two special conditions that impact a position's receipt of funding payments:

```vyper
  # When there are negative positions (liquidation bot failure):
  avail           : uint256       = pool.base_collateral if pos.long else (
                                    pool.quote_collateral )
  # 1) we penalize negative positions by setting their funding_received to zero
  funding_received: uint256       = 0 if remaining == 0 else (
    # 2) funding_received may add up to more than available collateral, and
    #    we will pay funding fees out on a first come first serve basis
                                    min(fees.funding_received, avail) )
```

If the position has run out of collateral by the time it is being closed, he will receive none of his share of funding payments. Additionally, if the available collateral is not high enough to service the funding fee receipt, he will receive only the greatest amount that is available.

These funding fee payments are still always made ([deducted](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/positions.vy#L250) from remaining collateral), whether they are received or not:

```vyper
  c1              : Val           = self.deduct(c0,           fees.funding_paid)
```

When a position is closed under most circumstances, the pool will have enough collateral to service the corresponding fee payment:

```vyper
# longs
base_collateral : [self.MATH.MINUS(fees.funding_received)],
quote_collateral: [self.MATH.PLUS(fees.funding_paid),
                       self.MATH.MINUS(pos.collateral)],
...
# shorts
base_collateral : [self.MATH.PLUS(fees.funding_paid), # <-
                       self.MATH.MINUS(pos.collateral)],
quote_collateral: [self.MATH.MINUS(fees.funding_received)],
```

When positions are closed, the original collateral (which was placed into the pool upon opening) is removed. However, the amount of funding payments a position made is added to the pool for later receipt. Thus, when positions are still open there is enough position collateral to fulfill the funding fee payment and when they close the funding payment made by that position still remains in the pool.

Only when the amount of funding a position paid exceeded its original collateral, will there will not be enough collateral to service the receipt of funding fees, as alluded to in the comments. However, it's possible for users to pay the full funding fee, but if the borrow fee exceeds the collateral balance remaining thereafter, they will not receive any funding fees. As a result, it's possible for funding fees to be paid which are never received.

Further, even in the case of funding fee underpayment, setting the funding fee received to 0 does not remedy this issue. The funding fees which he underpaid were in a differing token from those which he would receive, so this only furthers the imbalance of fees received to paid. 

## Impact
`core.vy` includes a specification for one of the invariants of the protocol:
```vyper
#    * funding payments match
#        sum(funding_received) = sum(funding_paid)
```

This invariant is clearly broken as some portion of paid funding fees will not be received under all circumstances, so code is not to spec. This will also lead to some stuck funds, as a portion of the paid funding fees will never be deducted from the collateral. This can in turn lead to dilution of fees for future funding fee recipients, as the payments will be distributed evenly to the entire collateral including these stuck funds which will never be removed.

## Code Snippet

## Tool used

Manual Review

## Recommendation
Consider an alternative method of accounting for funding fees, as there are many cases under the current accounting where fees received/paid can fall out of sync. 

For example, include a new state variable that explicitly tracks unpaid funding fee payments and perform some pro rata or market adjustment to future funding fee recipients, specifically for *that token*.