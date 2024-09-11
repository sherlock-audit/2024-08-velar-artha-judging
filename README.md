# Issue M-1: Traders may decrease their trading loss via mint/burn 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/12 

## Found by 
0x37
## Summary
When traders have some trading loss, they can decrease their trading loss via mint LP before closing position and burn LP after closing position.

## Vulnerability Detail
When traders open one position with long or short size, traders have some negative unrealized Pnl. When traders close their positions, LP holders as traders' counterparty, will take traders' loss as their profits.
The problem is that there is not any limitation for mint()/burn() functions. Traders can make use of this problem to decrease their trading loss.
For example:
1. Alice opens one Long position in BTC/USDT market.
2. BTC price decreases and Alice's long position has some negative Pnl.
3. Alice wants to close her position.
4. Alice borrows one huge amount of BTC/USDT and mint in this BTC/USDT market to own lots of shares.
5. Alice closes her position and her loss will become LP's profit, this will increase LP share's price.
6. Alice burns her share with one higher share price.

In this way, Alice can avoid most of her trading loss.

## Impact
Traders have ways to avoid trading loss. This means that LPs will lose some profits that they deserve.

## Code Snippet
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/core.vy#L154-L226

## Tool used
Manual Review

## Recommendation
Add one LP locking mechanism. When someone mints some shares in the market, he cannot burn his shares immediately. After a cool down period, he can burn his shares.

# Issue M-2: Incorrect borrowing fee calculation 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/14 

## Found by 
0x37, KupiaSec
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

# Issue M-3: Last LP in each pool may lose a few amount of reserve. 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/15 

## Found by 
0x37
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

# Issue M-4: Healthy positions may be liquidated because of inappropriate judgment 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/17 

## Found by 
0x0x0xw3, 0x37, 0xaliyah, 0xnbvc, bareli, oxwhite
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

# Issue M-5: Penalized funding received token will be locked in the contract 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/18 

## Found by 
0x37
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

# Issue M-6: Hardcoded Value Breaks Core Contract Functionality 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/27 

## Found by 
0xbranded, ydlee
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

# Issue M-7: DoS of LP Withdrawals Due to Abuse of `unlocked_reserves` 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/28 

## Found by 
0xbranded
## Summary
LP withdrawals can be blocked by a malicious actor inflating the OI to intentionally increase `unlocked_reserves`.

## Vulnerability Detail
The protocol locks user deposits in order to ensure future payout obligations can be met, a key functionality outlined in the comment specifications. The `pool.vy` function [`unlocked_reserves`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/pools.vy#L125-L130) reports the token reserves not currently tied up to fulfill future payouts:

```vyper
def unlocked_reserves(id: uint256) -> Tokens:
  ps: PoolState = Pools(self).lookup(id)
  return Tokens({
    base : ps.base_reserves  - ps.base_interest,
    quote: ps.quote_reserves - ps.quote_interest,
  })
```

This function is mentioned in [`calc_burn`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/pools.vy#L216-L222) which is called when LPs are making a withdrawal:

```vyper
  unlocked: Tokens  = Pools(self).unlocked_reserves(id)
  ...
  assert uv         >= bv,             ERR_PRECONDITIONS
  assert amts.base  <= unlocked.base,  ERR_PRECONDITIONS
  assert amts.quote <= unlocked.quote, ERR_PRECONDITIONS
```

Additionally, after every user action in `core.vy` (including burn and open) an [invariants](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/core.vy#L126-L133) check is performed with similar enforcement:

```vyper
def INVARIANTS(id: uint256, base_token: address, quote_token: address):
  pool         : PoolState = self.POOLS.lookup(id)
...
  assert pool.base_reserves  >= pool.base_interest,  ERR_INVARIANTS
  assert pool.quote_reserves >= pool.quote_interest, ERR_INVARIANTS
```

Critically, the same comparison between `interest` and `reserves` is being made in both cases. Since `open` increases the `interest`, a malicious attacker can take out positions with large enough size and leverage to decrease `unlocked_reserves` to an arbitrarily small value.

As long as he is well-capitalized, he can take out equal notional size positions on both the long and short side, eliminating price fluctuations and funding payments from the cost of this attack, and locking both quote and base reserves. While he would still pay borrowing rates, as well as the initial cost of opening a position, these costs are low enough to enable him to maintain this DoS (assuming he manages his position periodically to avoid liquidation).

## Impact
With a large enough bankroll, all withdrawals can be blocked for several months at a nominal cost to the attacker. Anytime the unlocked reserves grows as a result of user actions (eg. mint, close), he can simply open more positions to extend the attack.

Withdrawals can very easily be blocked for a period of 4 hours (DoS period mentioned in the [contest rules](https://audits.sherlock.xyz/contests/526)) with a much more modest bankroll and cost of attack.

Opening new positions will also be blocked, but the blocking of withdrawals is much more problematic as this is a time-sensitive operation given fluctuating crypto prices and user liquidity needs (especially if the attack is carried out for the long durations described). This would significantly erode trust in the protocol and discourage future depositors, even after the attack has concluded.

## Code Snippet

## Tool used

Manual Review

## Recommendation
Specifically for the opening of positions, enforce a lower limit of accessible reserves in order to facilitate withdrawals even when positions can no longer be opened.

For example at the end of opening a position, consider asserting:
```vyper
  assert pool.base_reserves  >= 2*pool.base_interest,  ERR_INVARIANTS
  assert pool.quote_reserves >= 2*pool.quote_interest, ERR_INVARIANTS
```

# Issue M-8: Loss of Funds and Delayed Liquidations Due to Inaccurate Fee Accrual 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/38 

## Found by 
0xbranded
## Summary
All time-dependent fees in the system accrue according to an inaccurate approximation that will progressively lead to significant deviations from their implied cumulative value. This applies to both long/short rates, with both funding paid/received and borrowing rates impacted. As a result, liquidations will be delayed and LPs/funding recipients will be significantly underpaid.

## Vulnerability Detail
Each [fee calculation](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/fees.vy#L164-L193) in `fees.vy`, such as


```vyper
borrowing_long_sum  : uint256 = self.extend(fs.borrowing_long_sum,  fs.borrowing_long,  new_terms)
borrowing_short_sum : uint256 = self.extend(fs.borrowing_short_sum, fs.borrowing_short, new_terms)
funding_long_sum    : uint256 = self.extend(fs.funding_long_sum,    fs.funding_long,    new_terms)
funding_short_sum   : uint256 = self.extend(fs.funding_short_sum,   fs.funding_short,   new_terms)
```

makes use of the [same underlying calculation](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/fees.vy#L94-L98) through the use of `extend`:

```vyper
def extend(X: uint256, x_m: uint256, m: uint256) -> uint256:
  return X + (m*x_m)
```

That is, given a rate `r` and a number of intervals `n`, the fee contribution of each interval is given by $nr$, and the overall rate accrues as $\sum\limits_i n_ir_i$. However, this calculation is problematic since the percentage rates are naively added up and applied entirely at once, rather than applying them continuously.

The exact fee calculation over each interval is given $(1+r)^n$ (now expressed as a ratio of 1), and the overall rate accrues as $\prod\limits_i (1 + {r_i})^{n_i}$. The Taylor expansion of each segment of this polynomial is given by $(1+r)^n = 1 + nr + \frac{1}{2}(n-1)nr^2 + \frac{1}{6}(n-2)(n-1)nr^3 + \cdots$

Notice that the existing calculation is effectively the linear taylor approximation for the true rate:
$(1+r)^n = 1 + nr +O(r^2)$

The error is bounded above by $R_2(r) \leq \frac{n(n-1)(1+r)^{n-2}}{2}r^2$. Critically, this approximation is relatively accurate **assuming n and r are not too large**. This assumption does not hold. 

Starting with `r`, fees are applied with 9 decimals of precision:

```vyper
DENOM: constant(uint256) = 1_000_000_000

def apply(x: uint256, numerator: uint256) -> Fee:
  fee      : uint256 = (x * numerator) / DENOM
```

These fees are applied on a per-block basis. The BOB chain has an average block time of [2.0 seconds](https://explorer.gobob.xyz/). Using the existing fee calculation, `r = 10` will translate into an 8 hour funding rate of 0.0288%, or an annualized rate of 15.78%, a suitable estimate for what might be expected. 

Using the average block time of 2.0 seconds, we find that `n = 1.58e7` blocks in a 365 day calendar year.

Given these values, the existing fee calculation $1 + nr$ yields a 15.78% annual interest rate while the exact value $(1+r)^n$ yields a 17.09% annual interest rate. This represents a 7.68% error in the interest rate over a single year.

As n grows larger, the error continues to grow. Over a 4 year period, `n = 6.31e7` blocks and using the same `r = 10` from before we get interest rates of 63.12% and 83.03% for the current approach and the exact calculation, respectively. A 28.26% error in the interest rate results over this time period. This error steadily converges to 100%, with a **99.7% error over a 30 year period**.

The assumption regarding the average value of `r = 10` (0.0288% 8 hour rate) was made based on [past funding rates for BTC](https://www.coinglass.com/funding/BTC). The funding rate over an 8 hour period has ranged between 0.01% and 0.25% over the past year. Given varying market conditions, as well as differing risk profiles for altcoins vs BTC, this is considered a fair and conservative estimate on average. Even if the assumed interest rate were halved (`r = 5`, 0.0144% 8 hour rate), errors of 3.9% and 15.0% occur over a 1 and 4 year period, respectively. On the other hand if doubled (`r = 20`, 0.0576% 8 hour rate), errors of 15% and 50% occur over the same respective timespans.

Note that during periods of elevated rates, the errors described will grow non-linearly. For example, given `r = 100` (0.288% 8 hour rate), the existing method will yield an effective annual rate of 157.8%. The exact calculation yields a rate of 384.5%. While these rates are not representative of typical market conditions, it should paint a picture of how drastically inaccurate the current calculation could be, depending on the circumstances. The assumptions made above should serve as a rough estimate of average conditions, however periods with rates above this average are weighted more heavily than periods with lower rates.

## Impact
Any Taylor approximation of the true rate is a strict underestimate. As a result, significant underpayments of funding fees and borrowing fees will consistently occur for every pool/position, disincentivizing LPs and carry traders and eroding confidence/trust in the system. Further, positions paying funding fees (historically longs) are effectively subsidized under the current model, increasing utilization and reducing capital efficiency. These positions (typically longs) will also take longer to liquidate and LP funds are locked for longer as a result.

As a rough demonstration, consider a pool with an average long collateral value of $10M over a 4-year period, with an average 8-hour long funding rate of 0.0288% (as assumed above). Over this time period, longs are expected to pay $8.8M in funding fees to shorts. In reality they will pay $6.3M, **representing a shortfall of $2.5M** that should have been deducted from longs and paid to shorts.

Assuming a 50% imbalance between shorts and longs, the average annual borrow rate is 31.56%, so LPs for this pool will also be underpaid by $5.0M from longs, in addition to a similar fee underpayments from shorts.

Under this scenario, longs would have taken 25 months to liquidate from fees alone, when they should have taken 23 months to liquidate. This 10% deviation in absolute liquidation time underscores the true difference in liquidation time. When PnL/volatility are taken into account, these differences at the margin make all the difference and can result in LP funds being locked for far longer than this difference suggests. Additionally, positions which should have been liquidated may now post a profit, further increasing risk for LPs.

These underpayments occur persistently, at all times and for every vault, and represent material losses for funding recipients and lenders, as well as significantly disrupt the proper liquidation process.

## Code Snippet
For the PoC, `r = 10`, `long_collateral = short_collateral = 10^7 * 10^18` and `n = 6.3 * 10^7` blocks (4 years), as outlined above.

The smart contracts were stripped to isolate the relevant logic, and [foundry](https://github.com/0xKitsune/Foundry-Vyper) was used for testing. To run the test, clone the repo and place `Fee.vy` in `vyper_contracts`, and place `Fee.t.sol`, `Cheat.sol`, and `IFee.sol` under `src/test`.

<details>
<summary>Fee.t.sol</summary>

```solidity

// SPDX-License-Identifier: MIT
pragma solidity >=0.8.13;

import {CheatCodes} from "./Cheat.sol";

import "../../lib/ds-test/test.sol";
import "../../lib/utils/Console.sol";
import "../../lib/utils/VyperDeployer.sol";

import "./IFee.sol";

contract FeeTest is DSTest {
    ///@notice create a new instance of VyperDeployer
    VyperDeployer vyperDeployer = new VyperDeployer();
    CheatCodes vm = CheatCodes(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    IFee fee;
    uint256 constant YEAR = (60*60*24*(365) + 60*60*24 / 4); //includes leap year

    function setUp() public {
        ///@notice deploy a new instance of ISimplestore by passing in the address of the deployed Vyper contract
        fee = IFee(vyperDeployer.deployContract("Fee"));
    }

    function testCalc() public {
        uint256 blocksIn4Yr = (4*YEAR) / 2;

        vm.roll(blocksIn4Yr);

        fee.update();

        // pools were initialized at block 0
        fee.calc(true, 1e25, 0); // (current) linear fee approximation
        fee.calc2(true, 1e25, 0); // quadratic approximation
        fee.calc3(true, 1e25, 0); // cubic approximation
    }   
}
```
</details>

<details>
<summary> Fee.vy </summary>

```vyper

struct DynFees:
  funding_long   : uint256
  funding_short  : uint256

struct PoolState:
  base_collateral  : uint256
  quote_collateral : uint256

struct FeeState:
  t1                   : uint256
  funding_long         : uint256
  funding_short        : uint256
  long_collateral      : uint256
  short_collateral     : uint256
  funding_long_sum     : uint256
  funding_short_sum    : uint256
  received_long_sum    : uint256
  received_short_sum   : uint256

struct SumFees:
  funding_paid    : uint256
  funding_received: uint256

struct Period:
  funding_long   : uint256
  funding_short  : uint256
  received_long  : uint256
  received_short : uint256

#starting point hardcoded
@external
def __init__():
  self.FEE_STORE = FeeState({
  t1                   : block.number,
  funding_long         : 10,
  funding_short        : 0,
  long_collateral      : 10_000_000_000_000_000_000_000_000,
  short_collateral     : 10_000_000_000_000_000_000_000_000,
  funding_long_sum     : 0,
  funding_short_sum    : 0,
  received_long_sum    : 0,
  received_short_sum   : 0,
  })

  self.FEE_STORE_AT[block.number] = self.FEE_STORE

  self.FEE_STORE2 = self.FEE_STORE
  self.FEE_STORE_AT2[block.number] = self.FEE_STORE
  self.FEE_STORE3 = self.FEE_STORE
  self.FEE_STORE_AT3[block.number] = self.FEE_STORE

# hardcoded funding rates for the scenario where funding is positive
@internal
@view
def dynamic_fees() -> DynFees:
    return DynFees({
        funding_long   : 10,
        funding_short  : 0,
    })

# #hardcoded pool to have 1e24 of quote and base collateral
@internal
@view
def lookup() -> PoolState:
  return PoolState({
    base_collateral  : 10_000_000_000_000_000_000_000_000,
    quote_collateral : 10_000_000_000_000_000_000_000_000,
  })


FEE_STORE   : FeeState
FEE_STORE_AT   : HashMap[uint256, FeeState]

FEE_STORE2   : FeeState
FEE_STORE_AT2   : HashMap[uint256, FeeState]

FEE_STORE3   : FeeState
FEE_STORE_AT3   : HashMap[uint256, FeeState]

@internal
@view
def lookupFees() -> FeeState:
  return self.FEE_STORE 

@internal
@view
def lookupFees2() -> FeeState:
  return self.FEE_STORE2

@internal
@view
def lookupFees3() -> FeeState:
  return self.FEE_STORE3

@internal
@view
def fees_at_block(height: uint256) -> FeeState:
  return self.FEE_STORE_AT[height]

@internal
@view
def fees_at_block2(height: uint256) -> FeeState:
  return self.FEE_STORE_AT2[height]

@internal
@view
def fees_at_block3(height: uint256) -> FeeState:
  return self.FEE_STORE_AT3[height]

@external
def update():
  fs: FeeState = self.current_fees()
  fs2: FeeState = self.current_fees2()
  fs3: FeeState = self.current_fees3()

  self.FEE_STORE_AT[block.number] = fs
  self.FEE_STORE = fs

  self.FEE_STORE_AT2[block.number] = fs2
  self.FEE_STORE2 = fs2

  self.FEE_STORE_AT3[block.number] = fs3
  self.FEE_STORE3 = fs3

#math
ZEROS: constant(uint256) = 1000000000000000000000000000
DENOM: constant(uint256) = 1_000_000_000

@internal
@pure
def extend(X: uint256, x_m: uint256, m: uint256) -> uint256:
  return X + (m*x_m)

@internal
@pure 
def o2(r: uint256, n: uint256) -> uint256:
  if(n == 0): 
    return 0
  return r*n + ((n-1)*n*(r**2)/2)/DENOM

@internal
@pure 
def o3(r: uint256, n: uint256) -> uint256:
  if(n == 0): 
    return 0
  if(n == 1):
    return r*n

  return r*n + ((n-1)*n*(r**2)/2)/DENOM + ((n-2)*(n-1)*n*(r**3)/6)/DENOM**2

@internal
@pure
def apply(x: uint256, numerator: uint256) -> uint256:
  """
  Fees are represented as numerator only, with the denominator defined
  here. This computes x*fee capped at x.
  """
  fee      : uint256 = (x * numerator) / DENOM
  fee_     : uint256 = fee     if fee <= x else x
  return fee_

@internal
@pure
def divide(paid: uint256, collateral: uint256) -> uint256:
  if collateral == 0: return 0
  else              : return (paid * ZEROS) / collateral

@internal
@pure
def multiply(ci: uint256, terms: uint256) -> uint256:
  return (ci * terms) / ZEROS

@internal
@pure
def slice(y_i: uint256, y_j: uint256) -> uint256:
  return y_j - y_i

@internal
@view
def current_fees() -> FeeState:
  """
  Update incremental fee state, called whenever the pool state changes.
  """
  # prev/last updated state
  fs       : FeeState  = self.lookupFees()
  # current state
  ps       : PoolState = self.lookup()
  new_fees : DynFees   = self.dynamic_fees()
  # number of blocks elapsed
  new_terms: uint256   = block.number - fs.t1

  funding_long_sum    : uint256 = self.extend(fs.funding_long_sum,    fs.funding_long,    new_terms)
  funding_short_sum   : uint256 = self.extend(fs.funding_short_sum,   fs.funding_short,   new_terms)

  paid_long_term      : uint256 = self.apply(fs.long_collateral, fs.funding_long * new_terms)
  received_short_term : uint256 = self.divide(paid_long_term,    fs.short_collateral)

  paid_short_term     : uint256 = self.apply(fs.short_collateral, fs.funding_short * new_terms)
  received_long_term  : uint256 = self.divide(paid_short_term,    fs.long_collateral)

  received_long_sum   : uint256 = self.extend(fs.received_long_sum,  received_long_term,  1)
  received_short_sum  : uint256 = self.extend(fs.received_short_sum, received_short_term, 1)

  if new_terms == 0:
    return FeeState({
    t1                   : fs.t1,
    funding_long         : new_fees.funding_long,
    funding_short        : new_fees.funding_short,
    long_collateral      : ps.quote_collateral,
    short_collateral     : ps.base_collateral,
    funding_long_sum     : fs.funding_long_sum,
    funding_short_sum    : fs.funding_short_sum,
    received_long_sum    : fs.received_long_sum,
    received_short_sum   : fs.received_short_sum,
    })
  else:
    return FeeState({
    t1                   : block.number,
    funding_long         : new_fees.funding_long,
    funding_short        : new_fees.funding_short,
    long_collateral      : ps.quote_collateral,
    short_collateral     : ps.base_collateral,
    funding_long_sum     : funding_long_sum,
    funding_short_sum    : funding_short_sum,
    received_long_sum    : received_long_sum,
    received_short_sum   : received_short_sum,
    })

@internal
@view
def current_fees2() -> FeeState:
  """
  Update incremental fee state, called whenever the pool state changes.
  """
  # prev/last updated state
  fs       : FeeState  = self.lookupFees2()
  # current state
  ps       : PoolState = self.lookup()
  new_fees : DynFees   = self.dynamic_fees()
  # number of blocks elapsed
  new_terms: uint256   = block.number - fs.t1

  o2_l: uint256 = self.o2(fs.funding_long, new_terms)
  o2_s: uint256 = self.o2(fs.funding_short, new_terms)

  funding_long_sum    : uint256 = self.extend(fs.funding_long_sum,    o2_l,    1)
  funding_short_sum   : uint256 = self.extend(fs.funding_short_sum,   o2_s,   1)

  paid_long_term      : uint256 = self.apply(fs.long_collateral, o2_l)
  received_short_term : uint256 = self.divide(paid_long_term,    fs.short_collateral)

  paid_short_term     : uint256 = self.apply(fs.short_collateral, o2_s)
  received_long_term  : uint256 = self.divide(paid_short_term,    fs.long_collateral)

  received_long_sum   : uint256 = self.extend(fs.received_long_sum,  received_long_term,  1)
  received_short_sum  : uint256 = self.extend(fs.received_short_sum, received_short_term, 1)

  if new_terms == 0:
    return FeeState({
    t1                   : fs.t1,
    funding_long         : new_fees.funding_long,
    funding_short        : new_fees.funding_short,
    long_collateral      : ps.quote_collateral,
    short_collateral     : ps.base_collateral,
    funding_long_sum     : fs.funding_long_sum,
    funding_short_sum    : fs.funding_short_sum,
    received_long_sum    : fs.received_long_sum,
    received_short_sum   : fs.received_short_sum,
    })
  else:
    return FeeState({
    t1                   : block.number,
    funding_long         : new_fees.funding_long,
    funding_short        : new_fees.funding_short,
    long_collateral      : ps.quote_collateral,
    short_collateral     : ps.base_collateral,
    funding_long_sum     : funding_long_sum,
    funding_short_sum    : funding_short_sum,
    received_long_sum    : received_long_sum,
    received_short_sum   : received_short_sum,
    })

@internal
@view
def current_fees3() -> FeeState:
  """
  Update incremental fee state, called whenever the pool state changes.
  """
  # prev/last updated state
  fs       : FeeState  = self.lookupFees3()
  # current state
  ps       : PoolState = self.lookup()
  new_fees : DynFees   = self.dynamic_fees()
  # number of blocks elapsed
  new_terms: uint256   = block.number - fs.t1

  o2_l: uint256 = self.o3(fs.funding_long, new_terms)
  o2_s: uint256 = self.o3(fs.funding_short, new_terms)

  funding_long_sum    : uint256 = self.extend(fs.funding_long_sum,    o2_l,    1)
  funding_short_sum   : uint256 = self.extend(fs.funding_short_sum,   o2_s,   1)

  paid_long_term      : uint256 = self.apply(fs.long_collateral, o2_l)
  received_short_term : uint256 = self.divide(paid_long_term,    fs.short_collateral)

  paid_short_term     : uint256 = self.apply(fs.short_collateral, o2_s)
  received_long_term  : uint256 = self.divide(paid_short_term,    fs.long_collateral)

  received_long_sum   : uint256 = self.extend(fs.received_long_sum,  received_long_term,  1)
  received_short_sum  : uint256 = self.extend(fs.received_short_sum, received_short_term, 1)

  if new_terms == 0:
    return FeeState({
    t1                   : fs.t1,
    funding_long         : new_fees.funding_long,
    funding_short        : new_fees.funding_short,
    long_collateral      : ps.quote_collateral,
    short_collateral     : ps.base_collateral,
    funding_long_sum     : fs.funding_long_sum,
    funding_short_sum    : fs.funding_short_sum,
    received_long_sum    : fs.received_long_sum,
    received_short_sum   : fs.received_short_sum,
    })
  else:
    return FeeState({
    t1                   : block.number,
    funding_long         : new_fees.funding_long,
    funding_short        : new_fees.funding_short,
    long_collateral      : ps.quote_collateral,
    short_collateral     : ps.base_collateral,
    funding_long_sum     : funding_long_sum,
    funding_short_sum    : funding_short_sum,
    received_long_sum    : received_long_sum,
    received_short_sum   : received_short_sum,
    })

@internal
@view
def query(opened_at: uint256) -> Period:
  """
  Return the total fees due from block `opened_at` to the current block.
  """
  fees_i : FeeState = self.fees_at_block(opened_at)
  fees_j : FeeState = self.current_fees()
  return Period({
    funding_long    : self.slice(fees_i.funding_long_sum,    fees_j.funding_long_sum),
    funding_short   : self.slice(fees_i.funding_short_sum,   fees_j.funding_short_sum),
    received_long   : self.slice(fees_i.received_long_sum,   fees_j.received_long_sum),
    received_short  : self.slice(fees_i.received_short_sum,  fees_j.received_short_sum),
  })

@external
@view
def calc(long: bool, collateral: uint256, opened_at: uint256) -> SumFees:
    period: Period  = self.query(opened_at)
    P_f   : uint256 = self.apply(collateral, period.funding_long) if long else (
                      self.apply(collateral, period.funding_short) )
    R_f   : uint256 = self.multiply(collateral, period.received_long) if long else (
                      self.multiply(collateral, period.received_short) )

    return SumFees({funding_paid: P_f, funding_received: R_f})

@internal
@view
def query2(opened_at: uint256) -> Period:
  """
  Return the total fees due from block `opened_at` to the current block.
  """
  fees_i : FeeState = self.fees_at_block2(opened_at)
  fees_j : FeeState = self.current_fees2()
  return Period({
    funding_long    : self.slice(fees_i.funding_long_sum,    fees_j.funding_long_sum),
    funding_short   : self.slice(fees_i.funding_short_sum,   fees_j.funding_short_sum),
    received_long   : self.slice(fees_i.received_long_sum,   fees_j.received_long_sum),
    received_short  : self.slice(fees_i.received_short_sum,  fees_j.received_short_sum),
  })

@external
@view
def calc2(long: bool, collateral: uint256, opened_at: uint256) -> SumFees:
    period: Period  = self.query2(opened_at)
    P_f   : uint256 = self.apply(collateral, period.funding_long) if long else (
                      self.apply(collateral, period.funding_short) )
    R_f   : uint256 = self.multiply(collateral, period.received_long) if long else (
                      self.multiply(collateral, period.received_short) )

    return SumFees({funding_paid: P_f, funding_received: R_f})

@internal
@view
def query3(opened_at: uint256) -> Period:
  """
  Return the total fees due from block `opened_at` to the current block.
  """
  fees_i : FeeState = self.fees_at_block3(opened_at)
  fees_j : FeeState = self.current_fees3()
  return Period({
    funding_long    : self.slice(fees_i.funding_long_sum,    fees_j.funding_long_sum),
    funding_short   : self.slice(fees_i.funding_short_sum,   fees_j.funding_short_sum),
    received_long   : self.slice(fees_i.received_long_sum,   fees_j.received_long_sum),
    received_short  : self.slice(fees_i.received_short_sum,  fees_j.received_short_sum),
  })

@external
@view
def calc3(long: bool, collateral: uint256, opened_at: uint256) -> SumFees:
    period: Period  = self.query3(opened_at)
    P_f   : uint256 = self.apply(collateral, period.funding_long) if long else (
                      self.apply(collateral, period.funding_short) )
    R_f   : uint256 = self.multiply(collateral, period.received_long) if long else (
                      self.multiply(collateral, period.received_short) )

    return SumFees({funding_paid: P_f, funding_received: R_f})
```
</details>

<details>
<summary> Cheat.sol </summary>

```solidity
interface CheatCodes {
    // This allows us to getRecordedLogs()
    struct Log {
        bytes32[] topics;
        bytes data;
    }

    // Possible caller modes for readCallers()
    enum CallerMode {
        None,
        Broadcast,
        RecurrentBroadcast,
        Prank,
        RecurrentPrank
    }

    enum AccountAccessKind {
        Call,
        DelegateCall,
        CallCode,
        StaticCall,
        Create,
        SelfDestruct,
        Resume
    }

    struct Wallet {
        address addr;
        uint256 publicKeyX;
        uint256 publicKeyY;
        uint256 privateKey;
    }

    struct ChainInfo {
        uint256 forkId;
        uint256 chainId;
    }

    struct AccountAccess {
        ChainInfo chainInfo;
        AccountAccessKind kind;
        address account;
        address accessor;
        bool initialized;
        uint256 oldBalance;
        uint256 newBalance;
        bytes deployedCode;
        uint256 value;
        bytes data;
        bool reverted;
        StorageAccess[] storageAccesses;
    }

    struct StorageAccess {
        address account;
        bytes32 slot;
        bool isWrite;
        bytes32 previousValue;
        bytes32 newValue;
        bool reverted;
    }

    // Derives a private key from the name, labels the account with that name, and returns the wallet
    function createWallet(string calldata) external returns (Wallet memory);

    // Generates a wallet from the private key and returns the wallet
    function createWallet(uint256) external returns (Wallet memory);

    // Generates a wallet from the private key, labels the account with that name, and returns the wallet
    function createWallet(uint256, string calldata) external returns (Wallet memory);

    // Signs data, (Wallet, digest) => (v, r, s)
    function sign(Wallet calldata, bytes32) external returns (uint8, bytes32, bytes32);

    // Get nonce for a Wallet
    function getNonce(Wallet calldata) external returns (uint64);

    // Set block.timestamp
    function warp(uint256) external;

    // Set block.number
    function roll(uint256) external;

    // Set block.basefee
    function fee(uint256) external;

    // Set block.difficulty
    // Does not work from the Paris hard fork and onwards, and will revert instead.
    function difficulty(uint256) external;
    
    // Set block.prevrandao
    // Does not work before the Paris hard fork, and will revert instead.
    function prevrandao(bytes32) external;

    // Set block.chainid
    function chainId(uint256) external;

    // Loads a storage slot from an address
    function load(address account, bytes32 slot) external returns (bytes32);

    // Stores a value to an address' storage slot
    function store(address account, bytes32 slot, bytes32 value) external;

    // Signs data
    function sign(uint256 privateKey, bytes32 digest)
        external
        returns (uint8 v, bytes32 r, bytes32 s);

    // Computes address for a given private key
    function addr(uint256 privateKey) external returns (address);

    // Derive a private key from a provided mnemonic string,
    // or mnemonic file path, at the derivation path m/44'/60'/0'/0/{index}.
    function deriveKey(string calldata, uint32) external returns (uint256);
    // Derive a private key from a provided mnemonic string, or mnemonic file path,
    // at the derivation path {path}{index}
    function deriveKey(string calldata, string calldata, uint32) external returns (uint256);

    // Gets the nonce of an account
    function getNonce(address account) external returns (uint64);

    // Sets the nonce of an account
    // The new nonce must be higher than the current nonce of the account
    function setNonce(address account, uint64 nonce) external;

    // Performs a foreign function call via terminal
    function ffi(string[] calldata) external returns (bytes memory);

    // Set environment variables, (name, value)
    function setEnv(string calldata, string calldata) external;

    // Read environment variables, (name) => (value)
    function envBool(string calldata) external returns (bool);
    function envUint(string calldata) external returns (uint256);
    function envInt(string calldata) external returns (int256);
    function envAddress(string calldata) external returns (address);
    function envBytes32(string calldata) external returns (bytes32);
    function envString(string calldata) external returns (string memory);
    function envBytes(string calldata) external returns (bytes memory);

    // Read environment variables as arrays, (name, delim) => (value[])
    function envBool(string calldata, string calldata)
        external
        returns (bool[] memory);
    function envUint(string calldata, string calldata)
        external
        returns (uint256[] memory);
    function envInt(string calldata, string calldata)
        external
        returns (int256[] memory);
    function envAddress(string calldata, string calldata)
        external
        returns (address[] memory);
    function envBytes32(string calldata, string calldata)
        external
        returns (bytes32[] memory);
    function envString(string calldata, string calldata)
        external
        returns (string[] memory);
    function envBytes(string calldata, string calldata)
        external
        returns (bytes[] memory);

    // Read environment variables with default value, (name, value) => (value)
    function envOr(string calldata, bool) external returns (bool);
    function envOr(string calldata, uint256) external returns (uint256);
    function envOr(string calldata, int256) external returns (int256);
    function envOr(string calldata, address) external returns (address);
    function envOr(string calldata, bytes32) external returns (bytes32);
    function envOr(string calldata, string calldata) external returns (string memory);
    function envOr(string calldata, bytes calldata) external returns (bytes memory);
    
    // Read environment variables as arrays with default value, (name, value[]) => (value[])
    function envOr(string calldata, string calldata, bool[] calldata) external returns (bool[] memory);
    function envOr(string calldata, string calldata, uint256[] calldata) external returns (uint256[] memory);
    function envOr(string calldata, string calldata, int256[] calldata) external returns (int256[] memory);
    function envOr(string calldata, string calldata, address[] calldata) external returns (address[] memory);
    function envOr(string calldata, string calldata, bytes32[] calldata) external returns (bytes32[] memory);
    function envOr(string calldata, string calldata, string[] calldata) external returns (string[] memory);
    function envOr(string calldata, string calldata, bytes[] calldata) external returns (bytes[] memory);

    // Convert Solidity types to strings
    function toString(address) external returns(string memory);
    function toString(bytes calldata) external returns(string memory);
    function toString(bytes32) external returns(string memory);
    function toString(bool) external returns(string memory);
    function toString(uint256) external returns(string memory);
    function toString(int256) external returns(string memory);

    // Sets the *next* call's msg.sender to be the input address
    function prank(address) external;

    // Sets all subsequent calls' msg.sender to be the input address
    // until `stopPrank` is called
    function startPrank(address) external;

    // Sets the *next* call's msg.sender to be the input address,
    // and the tx.origin to be the second input
    function prank(address, address) external;

    // Sets all subsequent calls' msg.sender to be the input address until
    // `stopPrank` is called, and the tx.origin to be the second input
    function startPrank(address, address) external;

    // Resets subsequent calls' msg.sender to be `address(this)`
    function stopPrank() external;

    // Reads the current `msg.sender` and `tx.origin` from state and reports if there is any active caller modification
    function readCallers() external returns (CallerMode callerMode, address msgSender, address txOrigin);

    // Sets an address' balance
    function deal(address who, uint256 newBalance) external;
    
    // Sets an address' code
    function etch(address who, bytes calldata code) external;

    // Marks a test as skipped. Must be called at the top of the test.
    function skip(bool skip) external;

    // Expects an error on next call
    function expectRevert() external;
    function expectRevert(bytes calldata) external;
    function expectRevert(bytes4) external;

    // Record all storage reads and writes
    function record() external;

    // Gets all accessed reads and write slot from a recording session,
    // for a given address
    function accesses(address)
        external
        returns (bytes32[] memory reads, bytes32[] memory writes);
    
    // Record all account accesses as part of CREATE, CALL or SELFDESTRUCT opcodes in order,
    // along with the context of the calls.
    function startStateDiffRecording() external;

    // Returns an ordered array of all account accesses from a `startStateDiffRecording` session.
    function stopAndReturnStateDiff() external returns (AccountAccess[] memory accesses);

    // Record all the transaction logs
    function recordLogs() external;

    // Gets all the recorded logs
    function getRecordedLogs() external returns (Log[] memory);

    // Prepare an expected log with the signature:
    //   (bool checkTopic1, bool checkTopic2, bool checkTopic3, bool checkData).
    //
    // Call this function, then emit an event, then call a function.
    // Internally after the call, we check if logs were emitted in the expected order
    // with the expected topics and data (as specified by the booleans)
    //
    // The second form also checks supplied address against emitting contract.
    function expectEmit(bool, bool, bool, bool) external;
    function expectEmit(bool, bool, bool, bool, address) external;

    // Mocks a call to an address, returning specified data.
    //
    // Calldata can either be strict or a partial match, e.g. if you only
    // pass a Solidity selector to the expected calldata, then the entire Solidity
    // function will be mocked.
    function mockCall(address, bytes calldata, bytes calldata) external;

    // Reverts a call to an address, returning the specified error
    //
    // Calldata can either be strict or a partial match, e.g. if you only
    // pass a Solidity selector to the expected calldata, then the entire Solidity
    // function will be mocked.
    function mockCallRevert(address where, bytes calldata data, bytes calldata retdata) external;

    // Clears all mocked and reverted mocked calls
    function clearMockedCalls() external;

    // Expect a call to an address with the specified calldata.
    // Calldata can either be strict or a partial match
    function expectCall(address callee, bytes calldata data) external;
    // Expect a call to an address with the specified
    // calldata and message value.
    // Calldata can either be strict or a partial match
    function expectCall(address callee, uint256, bytes calldata data) external;

    // Gets the _creation_ bytecode from an artifact file. Takes in the relative path to the json file
    function getCode(string calldata) external returns (bytes memory);
    // Gets the _deployed_ bytecode from an artifact file. Takes in the relative path to the json file
    function getDeployedCode(string calldata) external returns (bytes memory);

    // Label an address in test traces
    function label(address addr, string calldata label) external;
    
    // Retrieve the label of an address
    function getLabel(address addr) external returns (string memory);

    // When fuzzing, generate new inputs if conditional not met
    function assume(bool) external;

    // Set block.coinbase (who)
    function coinbase(address) external;

    // Using the address that calls the test contract or the address provided
    // as the sender, has the next call (at this call depth only) create a
    // transaction that can later be signed and sent onchain
    function broadcast() external;
    function broadcast(address) external;

    // Using the address that calls the test contract or the address provided
    // as the sender, has all subsequent calls (at this call depth only) create
    // transactions that can later be signed and sent onchain
    function startBroadcast() external;
    function startBroadcast(address) external;
    function startBroadcast(uint256 privateKey) external;

    // Stops collecting onchain transactions
    function stopBroadcast() external;

    // Reads the entire content of file to string, (path) => (data)
    function readFile(string calldata) external returns (string memory);
    // Get the path of the current project root
    function projectRoot() external returns (string memory);
    // Reads next line of file to string, (path) => (line)
    function readLine(string calldata) external returns (string memory);
    // Writes data to file, creating a file if it does not exist, and entirely replacing its contents if it does.
    // (path, data) => ()
    function writeFile(string calldata, string calldata) external;
    // Writes line to file, creating a file if it does not exist.
    // (path, data) => ()
    function writeLine(string calldata, string calldata) external;
    // Closes file for reading, resetting the offset and allowing to read it from beginning with readLine.
    // (path) => ()
    function closeFile(string calldata) external;
    // Removes file. This cheatcode will revert in the following situations, but is not limited to just these cases:
    // - Path points to a directory.
    // - The file doesn't exist.
    // - The user lacks permissions to remove the file.
    // (path) => ()
    function removeFile(string calldata) external;
    // Returns true if the given path points to an existing entity, else returns false
    // (path) => (bool)
    function exists(string calldata) external returns (bool);
    // Returns true if the path exists on disk and is pointing at a regular file, else returns false
    // (path) => (bool)
    function isFile(string calldata) external returns (bool);
    // Returns true if the path exists on disk and is pointing at a directory, else returns false
    // (path) => (bool)
    function isDir(string calldata) external returns (bool);
    
    // Return the value(s) that correspond to 'key'
    function parseJson(string memory json, string memory key) external returns (bytes memory);
    // Return the entire json file
    function parseJson(string memory json) external returns (bytes memory);
    // Check if a key exists in a json string
    function keyExists(string memory json, string memory key) external returns (bytes memory);
    // Get list of keys in a json string
    function parseJsonKeys(string memory json, string memory key) external returns (string[] memory);

    // Snapshot the current state of the evm.
    // Returns the id of the snapshot that was created.
    // To revert a snapshot use `revertTo`
    function snapshot() external returns (uint256);
    // Revert the state of the evm to a previous snapshot
    // Takes the snapshot id to revert to.
    // This deletes the snapshot and all snapshots taken after the given snapshot id.
    function revertTo(uint256) external returns (bool);

    // Creates a new fork with the given endpoint and block,
    // and returns the identifier of the fork
    function createFork(string calldata, uint256) external returns (uint256);
    // Creates a new fork with the given endpoint and the _latest_ block,
    // and returns the identifier of the fork
    function createFork(string calldata) external returns (uint256);

    // Creates _and_ also selects a new fork with the given endpoint and block,
    // and returns the identifier of the fork
    function createSelectFork(string calldata, uint256)
        external
        returns (uint256);
    // Creates _and_ also selects a new fork with the given endpoint and the
    // latest block and returns the identifier of the fork
    function createSelectFork(string calldata) external returns (uint256);

    // Takes a fork identifier created by `createFork` and
    // sets the corresponding forked state as active.
    function selectFork(uint256) external;

    // Returns the currently active fork
    // Reverts if no fork is currently active
    function activeFork() external returns (uint256);

    // Updates the currently active fork to given block number
    // This is similar to `roll` but for the currently active fork
    function rollFork(uint256) external;
    // Updates the given fork to given block number
    function rollFork(uint256 forkId, uint256 blockNumber) external;

    // Fetches the given transaction from the active fork and executes it on the current state
    function transact(bytes32) external;
    // Fetches the given transaction from the given fork and executes it on the current state
    function transact(uint256, bytes32) external;

    // Marks that the account(s) should use persistent storage across
    // fork swaps in a multifork setup, meaning, changes made to the state
    // of this account will be kept when switching forks
    function makePersistent(address) external;
    function makePersistent(address, address) external;
    function makePersistent(address, address, address) external;
    function makePersistent(address[] calldata) external;
    // Revokes persistent status from the address, previously added via `makePersistent`
    function revokePersistent(address) external;
    function revokePersistent(address[] calldata) external;
    // Returns true if the account is marked as persistent
    function isPersistent(address) external returns (bool);

    /// Returns the RPC url for the given alias
    function rpcUrl(string calldata) external returns (string memory);
    /// Returns all rpc urls and their aliases `[alias, url][]`
    function rpcUrls() external returns (string[2][] memory);
}

```
</details>

<details>
<summary> IFee.sol </summary>

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.13;

interface IFee {
    function update() external;
    function calc(bool, uint256, uint256) external returns(SumFees memory);
    function calc2(bool, uint256, uint256) external returns(SumFees memory);
    function calc3(bool, uint256, uint256) external returns(SumFees memory);
  
    struct SumFees{
        uint256 funding_paid;
        uint256 funding_received;
    }
}
```
</details>

## Tool used

Manual Review

## Recommendation
Consider replacing each `fs.<fee_rate> * new_terms` with an intermediate calculation using these two values. For a quadratic approximation, include

```vyper
@internal
@pure
def o2(r: uint256, n: uint256) -> uint256:
  if(n == 0): 
    return 0
  return r*n + ((n-1)*n*(r**2)/2)/DENOM
```

while for a cubic approximation, include

```vyper
@internal
@pure 
def o3(r: uint256, n: uint256) -> uint256:
  if(n == 0): 
    return 0
  if(n == 1):
    return r*n

  return r*n + ((n-1)*n*(r**2)/2)/DENOM + ((n-2)*(n-1)*n*(r**3)/6)/DENOM**2
```

Refer to `Fee.vy` above for guidance on necessary adjustments to the various functions.

The quadratic approximation will provide the largest improvement for the least added computational cost, and is the recommended compromise. As a reference, the quadratic approximation drops the current error from 28.26% to 5.62% (an 80% reduction) given a 4-year timespan and `r = 10`. The cubic approximation further decreases the error to 0.85% (a 97% reduction). 

The error can be made arbitrarily small, at the expense of increased computational costs for diminishing returns. For example, the quartic approximation drops the error down to 0.11% (a 99.6% reduction). 

# Issue M-9: pools.vy: calc_mint does not account for outstanding fees, allowing attackers to steal fees from LP 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/50 

## Found by 
0x37, Trooper
### Summary

Inside of the [calc_mint](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/pools.vy#L163-L172) the contract calculates how much LP-Tokens should be minted when a provider adds new liquidity. This does not account for outstanding fees. Therefor a new user gets the same LP-Token ratio as older LP providers. **This allows new providers to steal fees.**

### Root Cause

In the [`calc_mint`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/pools.vy#L163-L172) function, LP tokens are calculated based on the [`total_reserves`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/pools.vy#L119-L121) , which reflect the current pool state but do not account for any pending fees. This allows a large token holder to deposit just before a regular user closes their position.

When closing a position, the core contract  calls [`close`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/pools.vy#L258-L276) function, updating the pool reserves to reflect the added tokens paid as fee. As a result, the pool now contains more liquidity.

The attacker can then unstake their LP tokens and, based on the ratio of their LP share relative to the total LP value before the attack, they are able to claim a significant portion of the fees paid by the user.

### Internal pre-conditions

1. Large position will be closed and attacker notices before the tx is settled (i.e. by looking at the mem-pool)

### External pre-conditions

N/A

### Attack Path

1. Mint large LP position
2. wait for closing transaction to settle
3. Burn the LP position

### Impact

The attacker is able to steal fees that should have been paid to the older LP.

### PoC

## Walkthrough

A user opens a large position in the pool:
```vyper
    # user opens positions and closes it after 1 weeks
    tx = open(VEL, STX, True, d(999), 10, price=d(5), sender=long)
    assert not tx.failed

    chain.pending_timestamp += round(datetime.timedelta(weeks=1).total_seconds())    
```

The attacker now mints new LP tokens with a relatively large position vs. the existing LPs. In this case the new LP is ~100x the old LP:
```vyper
    mint(VEL, STX, LP, d(10_000_000), d(50_000_000), price=d(5), sender=lp_provider2)
```

Close tx settles and fees get paid to the pool:
```vyper
    tx = close(VEL, STX, 1, price=d(5), sender=long)
```

The attacker now burns all his LP tokens:
```vyper
    lp_amount_lp1 = LP.balanceOf(lp_provider)
    burn(VEL, STX, LP, lp_amount_lp2, price=d(5), sender=lp_provider2)
```

The original LP only earned 1 of each token:
```vyper
    lp1_inital_value = d(10_000) * 5 + d(50_000)
    lp1_value = lp1_base * 5 + lp1_quote # (as quote tokens)
    lp1_profit = lp1_value - lp1_inital_value # (as quote tokens)
    assert lp1_profit < 10 # lp1_profit is 6: 1 of base and quote
```

The attacker earned most of the fees, ~120 quote tokens:
```vyper
    lp2_inital_value = d(10_000_000) * 5 + d(50_000_000)
    lp2_value = lp2_base * 5 + lp2_quote # (as quote tokens)
    lp2_profit = lp2_value - lp2_inital_value # (as quote tokens)
    assert lp2_profit > 100 # lp2_profit ~ 120 (as quote tokens)
```

## Diff

Update the [`conftest.py`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/tests/conftest.py) to be the same as the currently planed parameters (based on sponsor msg in discord):
```diff
--- a/conftest.py.orig
+++ b/conftest.py
@@ -58,8 +58,8 @@ def LP2(project, core, owner):
 # ----------- Params -----------------

 PARAMS = {
-  'MIN_FEE'               : 1,
-  'MAX_FEE'               : 1,
+  'MIN_FEE'               : 10,
+  'MAX_FEE'               : 100,

   # Fraction of collateral (e.g. 1000).
   'PROTOCOL_FEE'          : 1000,
```

```diff
--- a/test_positions.py.orig
+++ b/test_positions.py
@@ -137,3 +137,52 @@ def test_value(setup, positions, open, VEL, STX, owner, long):
         'borrowing_paid_want'  : 0,
         'remaining'            : 1998000
     }
+
+def test_burn_fees(chain, setup, open, close, VEL, STX, LP, long, mint_token, core, mint, burn, lp_provider, lp_provider2):
+    setup()
+
+    # user opens positions and closes it after 1 weeks
+    tx = open(VEL, STX, True, d(999), 10, price=d(5), sender=long)
+    assert not tx.failed
+
+    chain.pending_timestamp += round(datetime.timedelta(weeks=1).total_seconds())    
+
+    # ============= frontrun part
+    mint_token(VEL, d(10_000_000), lp_provider2)
+    mint_token(STX, d(50_000_000), lp_provider2)
+    assert not VEL.approve(core.address, d(10_000_000), sender=lp_provider2).failed
+    assert not STX.approve(core.address, d(50_000_000), sender=lp_provider2).failed
+    mint(VEL, STX, LP, d(10_000_000), d(50_000_000), price=d(5), sender=lp_provider2)
+    # ============= frontrun part
+
+    # ============= user tx
+    tx = close(VEL, STX, 1, price=d(5), sender=long)
+    assert not tx.failed
+    # ============= user tx
+
+    # ============= backrun part
+    lp_amount_lp2 = LP.balanceOf(lp_provider2)
+    burn(VEL, STX, LP, lp_amount_lp2, price=d(5), sender=lp_provider2)
+    # ============= backrun part
+
+    # ============= original lp unstake
+    lp_amount_lp1 = LP.balanceOf(lp_provider)
+    burn(VEL, STX, LP, lp_amount_lp1, price=d(5), sender=lp_provider)
+    # ============= original lp unstake
+
+    lp1_base = VEL.balanceOf(lp_provider) - d(90_000) # ignore the unstaked balance
+    lp1_quote = STX.balanceOf(lp_provider) - d(50_000) # ignore the unstaked balance
+    lp2_base = VEL.balanceOf(lp_provider2)
+    lp2_quote = STX.balanceOf(lp_provider2)
+
+    # allow for small profit
+    lp1_inital_value = d(10_000) * 5 + d(50_000)
+    lp1_value = lp1_base * 5 + lp1_quote # (as quote tokens)
+    lp1_profit = lp1_value - lp1_inital_value # (as quote tokens)
+    assert lp1_profit < 10 # lp1_profit is 6: 1 of base and quote
+
+    # LP2 made a profit
+    lp2_inital_value = d(10_000_000) * 5 + d(50_000_000)
+    lp2_value = lp2_base * 5 + lp2_quote # (as quote tokens)
+    lp2_profit = lp2_value - lp2_inital_value # (as quote tokens)
+    assert lp2_profit > 100 # lp2_profit ~ 120 (as quote tokens)
```





### Mitigation

The contract `pools.vy` should call the `fees.vy` contract and look up the currently outstanding fees inside of the [`total_reserves`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/pools.vy#L119-L121) function.

# Issue M-10: Fee Precision Loss Disrupts Liquidations and Causes Loss of Funds 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/66 

## Found by 
0xbranded
## Summary
Borrowing and funding fees of both longs/shorts suffer from two distinct sources of precision loss. The level of precision loss is large enough to consistently occur at a significant level, and can even result in total omission of fee payment for periods of time. This error is especially disruptive given the sensitive nature of funding fee calculations both in determining liquidations (a core functionality), as well as payments received by LPs and funding recipients (representing a significant loss). 

## Vulnerability Detail
The first of the aforementioned sources of precision loss is relating to the `DENOM` parameter defined and used in `apply` of [`math.vy`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/math.vy#L163-L172):

```vyper
DENOM: constant(uint256) = 1_000_000_000

def apply(x: uint256, numerator: uint256) -> Fee:
  fee      : uint256 = (x * numerator) / DENOM
...
  return Fee({x: x, fee: fee_, remaining: remaining})
```

This function is in turn referenced (to extract the `fee` parameter in particular) in several locations throughout [`fees.vy`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/fees.vy#L265), namely in determining the funding and borrowing payments made by positions open for a duration of time:

```vyper
  paid_long_term      : uint256 = self.apply(fs.long_collateral, fs.funding_long * new_terms)
...
  paid_short_term     : uint256 = self.apply(fs.short_collateral, fs.funding_short * new_terms)
...
    P_b   : uint256 = self.apply(collateral, period.borrowing_long) if long else (
                      self.apply(collateral, period.borrowing_short) )
    P_f   : uint256 = self.apply(collateral, period.funding_long) if long else (
                      self.apply(collateral, period.funding_short) )
```

The comments for `DENOM` specify that it's a "magic number which depends on the smallest fee one wants to support and the blocktime." In fact, given its current value of $10^{-9}$, the smallest representable fee per block is $10^{-7}$%. Given the average blocktimes of 2.0 sec on the [BOB chain](https://explorer.gobob.xyz/), there are 15_778_800 blocks in a standard calendar year. Combined with the fee per block, this translates to an annual fee of 1.578%.

However, this is also the interval size for annualized fees under the current system. As a result, any fee falling below the next interval will be rounded down. For example, given an annualized funding rate in the neighborhood of 15%, there is potential for a nearly 10% error in the interest rate if rounding occurs just before the next interval. This error is magnified the smaller the funding rates become. An annual fee of 3.1% would round down to 1.578%, representing an error of nearly 50%. And any annualized fees below 1.578% will not be recorded, representing a 100% error.

The second source of precision loss combines with the aforementioned error, to both increase the severity and frequency of error. It's related to how percentages are handled in `params.vy`, particularly when the long/short utilization is calculated to determine funding & borrow rates. The [utilization](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/params.vy#L59-L63) is shown below: 

```vyper
def utilization(reserves: uint256, interest: uint256) -> uint256:
    return 0 if (reserves == 0 or interest == 0) else (interest / (reserves / 100))
```

This function is in turn used to calculate borrowing (and funding rates, following a slightly different approach that similarly combines the use of `utilization` and `scale`), in `[dynamic_fees](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/params.vy#L33-L55)` of `params.vy`:

```vyper
def dynamic_fees(pool: PoolState) -> DynFees:
    long_utilization : uint256 = self.utilization(pool.base_reserves, pool.base_interest)
    short_utilization: uint256 = self.utilization(pool.quote_reserves, pool.quote_interest)
    borrowing_long   : uint256 = self.check_fee(
      self.scale(self.PARAMS.MAX_FEE, long_utilization))
    borrowing_short  : uint256 = self.check_fee(
      self.scale(self.PARAMS.MAX_FEE, short_utilization))
...
def scale(fee: uint256, utilization: uint256) -> uint256:
    return (fee * utilization) / 100
```

Note that `interest` and `reserves` maintain the same precision. Therefore, the output of `utilization` will have just 2 digits of precision, resulting from the division of `reserves` by `100`. However, this approach can similarly lead to fee rates losing a full percentage point in their absolute value. Since the utilization is used by `dynamic_fees` to calculate the funding / borrow rates, when combined with the formerly described source of precision loss the error is greatly amplified.

Consider a scenario when the long open interest is 199_999 * $10^{18}$ and the reserves are 10_000_000 * $10^{18}$. Under the current `utilization` functionality, the result would be a 1.9999% utilization rounded down to 1%.  Further assuming the value of `max_fee = 65` (this represents a 100% annual rate and 0.19% 8-hour rate), the long borrow rate would round down to 0%. Had the 1.9999% utilization rate not been rounded down 1%, the result would have been `r = 1.3`. In turn, the precision loss in `DENOM` would have effectively rounded down to `r = 1`, resulting in a 2.051% borrow rate rounded down to 1.578%. 

In other words, the precision loss in `DENOM` alone would have resulted in a 23% error in this case. But when combined with the precision loss in percentage points represented in `utilization`, a 100% error resulted. While the utilization and resulting interest rates will typically not be low enough to produce such drastic errors, this hopefully illustrates the synergistic combined impact of both sources of precision loss. Even at higher, more representative values for these rates (such as `r = 10`), errors in fee calculations exceeding 10% will consistently occur.

## Impact
All fees in the system will consistently be underpaid by a significant margin, across all pools and positions. Additionally trust/confidence in the system will be eroded as fee application will be unpredictable, with sharp discontinuities in rates even given moderate changes in pool utilization. Finally, positions will be subsidized at the expense of LPs, since the underpayment of fees will make liquidations less likely and take longer to occur. As a result, LPs and funding recipients will have lesser incentive to provide liquidity, as they are consistently being underpaid while taking on a greater counterparty risk.

As an example, consider the scenario where the long open interest is 1_099_999 * $10^{18}$ and the reserves are 10_000_000 * $10^{18}$. Under the current `utilization` functionality, the result would be a 10.9999% utilization rounded down to 10%. Assuming `max_fee = 65` (100% annually, 0.19% 8-hour), the long borrow rate would be `r = 6.5` rounded down to `r = 6`. A 9.5% annual rate results, whereas the accurate result if neither precision loss occurred is `r = 7.15` or 11.3% annually. The resulting error in the borrow rate is 16%.

Assuming a long collateral of 100_000 * $10^{18}$, LPs would earn 9_500 * $10^{18}$, when they should earn 11_300 * $10^{18}$, a shortfall of 1_800 * $10^{18}$ from longs alone. Additional borrow fee shortfalls would occur for shorts, in addition to shortfalls in funding payments received. 

Liquidation from borrow rates along should have taken 106 months based on the expected result of 11.3% per annum. However, under the 9.5% annual rate it would take 127 months to liquidate a position. This represents a 20% delay in liquidation time from borrow rates alone, not including the further delay caused by potential underpaid funding rates.

When PnL is further taken into account, these delays could mark the difference between a period of volatility wiping out a position. As a result, these losing positions could run for far longer than should otherwise occur and could even turn into winners. Not only are LP funds locked for longer as a result, they are at a greater risk of losing capital to their counterparty. On top of this, they are also not paid their rightful share of profits, losing out on funds to take on an unfavorably elevated risk. 

Thus, not only do consistent, material losses (significant fee underpayment) occur but a critical, core functionality malfunctions (liquidations are delayed).

## Code Snippet
In the included PoC, three distinct tests demonstrate the individual sources of precision loss, as well as their combined effect. Similar scenarios were demonstrated as discussed above, for example interest = 199_999 * $10^{18} with reserves = 10_000_000 * $10^{18}$ with a max fee of 65. 

The smart contracts were stripped to isolate the relevant logic, and [foundry](https://github.com/0xKitsune/Foundry-Vyper) was used for testing. To run the test, clone the repo and place `Denom.vy` in vyper_contracts, and place `Denom.t.sol`, `Cheat.sol`, and `IDenom.sol` under src/test.

<details>
<summary>Denom.vy</summary>

```vyper

struct DynFees:
  funding_long   : uint256
  funding_short  : uint256

struct PoolState:
  base_collateral  : uint256
  quote_collateral : uint256

struct FeeState:
  t1                   : uint256
  funding_long         : uint256
  funding_short        : uint256
  long_collateral      : uint256
  short_collateral     : uint256
  funding_long_sum     : uint256
  funding_short_sum    : uint256
  received_long_sum    : uint256
  received_short_sum   : uint256

struct SumFees:
  funding_paid    : uint256
  funding_received: uint256

struct Period:
  funding_long   : uint256
  funding_short  : uint256
  received_long  : uint256
  received_short : uint256

#starting point hardcoded
@external
def __init__():
  self.FEE_STORE = FeeState({
  t1                   : block.number,
  funding_long         : 1,
  funding_short        : 0,
  long_collateral      : 10_000_000_000_000_000_000_000_000,
  short_collateral     : 10_000_000_000_000_000_000_000_000,
  funding_long_sum     : 0,
  funding_short_sum    : 0,
  received_long_sum    : 0,
  received_short_sum   : 0,
  })

  self.FEE_STORE_AT[block.number] = self.FEE_STORE

  self.FEE_STORE2 = FeeState({
  t1                   : block.number,
  funding_long         : 1_999,
  funding_short        : 0,
  long_collateral      : 10_000_000_000_000_000_000_000_000,
  short_collateral     : 10_000_000_000_000_000_000_000_000,
  funding_long_sum     : 0,
  funding_short_sum    : 0,
  received_long_sum    : 0,
  received_short_sum   : 0,
  })
  self.FEE_STORE_AT2[block.number] = self.FEE_STORE2

# hardcoded funding rates for the scenario where funding is positive
@internal
@view
def dynamic_fees() -> DynFees:
    return DynFees({
        funding_long   : 10,
        funding_short  : 0,
    })

# #hardcoded pool to have 1e24 of quote and base collateral
@internal
@view
def lookup() -> PoolState:
  return PoolState({
    base_collateral  : 10_000_000_000_000_000_000_000_000,
    quote_collateral : 10_000_000_000_000_000_000_000_000,
  })


FEE_STORE   : FeeState
FEE_STORE_AT   : HashMap[uint256, FeeState]

FEE_STORE2   : FeeState
FEE_STORE_AT2   : HashMap[uint256, FeeState]

@internal
@view
def lookupFees() -> FeeState:
  return self.FEE_STORE 

@internal
@view
def lookupFees2() -> FeeState:
  return self.FEE_STORE2

@internal
@view
def fees_at_block(height: uint256) -> FeeState:
  return self.FEE_STORE_AT[height]

@internal
@view
def fees_at_block2(height: uint256) -> FeeState:
  return self.FEE_STORE_AT2[height]

@external
def update():
  fs: FeeState = self.current_fees()
  fs2: FeeState = self.current_fees2()

  self.FEE_STORE_AT[block.number] = fs
  self.FEE_STORE = fs

  self.FEE_STORE_AT2[block.number] = fs2
  self.FEE_STORE2 = fs2

#math
ZEROS: constant(uint256) = 1000000000000000000000000000
DENOM: constant(uint256) = 1_000_000_000
DENOM2: constant(uint256) = 1_000_000_000_000

@internal
@pure
def extend(X: uint256, x_m: uint256, m: uint256) -> uint256:
  return X + (m*x_m)

@internal
@pure
def apply(x: uint256, numerator: uint256) -> uint256:
  """
  Fees are represented as numerator only, with the denominator defined
  here. This computes x*fee capped at x.
  """
  fee      : uint256 = (x * numerator) / DENOM
  fee_     : uint256 = fee     if fee <= x else x
  return fee_

@internal
@pure
def apply2(x: uint256, numerator: uint256) -> uint256:
  """
  Fees are represented as numerator only, with the denominator defined
  here. This computes x*fee capped at x.
  """
  fee      : uint256 = (x * numerator) / DENOM2
  fee_     : uint256 = fee     if fee <= x else x
  return fee_

@internal
@pure
def divide(paid: uint256, collateral: uint256) -> uint256:
  if collateral == 0: return 0
  else              : return (paid * ZEROS) / collateral

@internal
@pure
def multiply(ci: uint256, terms: uint256) -> uint256:
  return (ci * terms) / ZEROS

@internal
@pure
def slice(y_i: uint256, y_j: uint256) -> uint256:
  return y_j - y_i

@external
@pure
def utilization(reserves: uint256, interest: uint256) -> uint256:
    """
    Reserve utilization in percent (rounded down). @audit this is actually rounded up...
    """
    return 0 if (reserves == 0 or interest == 0) else (interest / (reserves / 100))

@external
@pure
def utilization2(reserves: uint256, interest: uint256) -> uint256:
    """
    Reserve utilization in percent (rounded down). @audit this is actually rounded up...
    """
    return 0 if (reserves == 0 or interest == 0) else (interest / (reserves / 100_000))

@external
@pure
def scale(fee: uint256, utilization: uint256) -> uint256:
    return (fee * utilization) / 100

@external
@pure
def scale2(fee: uint256, utilization: uint256) -> uint256:
    return (fee * utilization) / 100_000

@internal
@view
def current_fees() -> FeeState:
  """
  Update incremental fee state, called whenever the pool state changes.
  """
  # prev/last updated state
  fs       : FeeState  = self.lookupFees()
  # current state
  ps       : PoolState = self.lookup()
  new_fees : DynFees   = self.dynamic_fees()
  # number of blocks elapsed
  new_terms: uint256   = block.number - fs.t1

  funding_long_sum    : uint256 = self.extend(fs.funding_long_sum,    fs.funding_long,    new_terms)
  funding_short_sum   : uint256 = self.extend(fs.funding_short_sum,   fs.funding_short,   new_terms)

  paid_long_term      : uint256 = self.apply(fs.long_collateral, fs.funding_long * new_terms)
  received_short_term : uint256 = self.divide(paid_long_term,    fs.short_collateral)

  paid_short_term     : uint256 = self.apply(fs.short_collateral, fs.funding_short * new_terms)
  received_long_term  : uint256 = self.divide(paid_short_term,    fs.long_collateral)

  received_long_sum   : uint256 = self.extend(fs.received_long_sum,  received_long_term,  1)
  received_short_sum  : uint256 = self.extend(fs.received_short_sum, received_short_term, 1)

  if new_terms == 0:
    return FeeState({
    t1                   : fs.t1,
    funding_long         : new_fees.funding_long,
    funding_short        : new_fees.funding_short,
    long_collateral      : ps.quote_collateral,
    short_collateral     : ps.base_collateral,
    funding_long_sum     : fs.funding_long_sum,
    funding_short_sum    : fs.funding_short_sum,
    received_long_sum    : fs.received_long_sum,
    received_short_sum   : fs.received_short_sum,
    })
  else:
    return FeeState({
    t1                   : block.number,
    funding_long         : new_fees.funding_long,
    funding_short        : new_fees.funding_short,
    long_collateral      : ps.quote_collateral,
    short_collateral     : ps.base_collateral,
    funding_long_sum     : funding_long_sum,
    funding_short_sum    : funding_short_sum,
    received_long_sum    : received_long_sum,
    received_short_sum   : received_short_sum,
    })

@internal
@view
def current_fees2() -> FeeState:
  """
  Update incremental fee state, called whenever the pool state changes.
  """
  # prev/last updated state
  fs       : FeeState  = self.lookupFees2()
  # current state
  ps       : PoolState = self.lookup()
  new_fees : DynFees   = self.dynamic_fees()
  # number of blocks elapsed
  new_terms: uint256   = block.number - fs.t1

  funding_long_sum    : uint256 = self.extend(fs.funding_long_sum,    fs.funding_long,    new_terms)
  funding_short_sum   : uint256 = self.extend(fs.funding_short_sum,   fs.funding_short,   new_terms)

  paid_long_term      : uint256 = self.apply2(fs.long_collateral, fs.funding_long * new_terms)
  received_short_term : uint256 = self.divide(paid_long_term,    fs.short_collateral)

  paid_short_term     : uint256 = self.apply2(fs.short_collateral, fs.funding_short * new_terms)
  received_long_term  : uint256 = self.divide(paid_short_term,    fs.long_collateral)

  received_long_sum   : uint256 = self.extend(fs.received_long_sum,  received_long_term,  1)
  received_short_sum  : uint256 = self.extend(fs.received_short_sum, received_short_term, 1)

  if new_terms == 0:
    return FeeState({
    t1                   : fs.t1,
    funding_long         : new_fees.funding_long,
    funding_short        : new_fees.funding_short,
    long_collateral      : ps.quote_collateral,
    short_collateral     : ps.base_collateral,
    funding_long_sum     : fs.funding_long_sum,
    funding_short_sum    : fs.funding_short_sum,
    received_long_sum    : fs.received_long_sum,
    received_short_sum   : fs.received_short_sum,
    })
  else:
    return FeeState({
    t1                   : block.number,
    funding_long         : new_fees.funding_long,
    funding_short        : new_fees.funding_short,
    long_collateral      : ps.quote_collateral,
    short_collateral     : ps.base_collateral,
    funding_long_sum     : funding_long_sum,
    funding_short_sum    : funding_short_sum,
    received_long_sum    : received_long_sum,
    received_short_sum   : received_short_sum,
    })

@internal
@view
def query(opened_at: uint256) -> Period:
  """
  Return the total fees due from block `opened_at` to the current block.
  """
  fees_i : FeeState = self.fees_at_block(opened_at)
  fees_j : FeeState = self.current_fees()
  return Period({
    funding_long    : self.slice(fees_i.funding_long_sum,    fees_j.funding_long_sum),
    funding_short   : self.slice(fees_i.funding_short_sum,   fees_j.funding_short_sum),
    received_long   : self.slice(fees_i.received_long_sum,   fees_j.received_long_sum),
    received_short  : self.slice(fees_i.received_short_sum,  fees_j.received_short_sum),
  })

@external
@view
def calc(long: bool, collateral: uint256, opened_at: uint256) -> SumFees:
    period: Period  = self.query(opened_at)
    P_f   : uint256 = self.apply(collateral, period.funding_long) if long else (
                      self.apply(collateral, period.funding_short) )
    R_f   : uint256 = self.multiply(collateral, period.received_long) if long else (
                      self.multiply(collateral, period.received_short) )

    return SumFees({funding_paid: P_f, funding_received: R_f})

@internal
@view
def query2(opened_at: uint256) -> Period:
  """
  Return the total fees due from block `opened_at` to the current block.
  """
  fees_i : FeeState = self.fees_at_block2(opened_at)
  fees_j : FeeState = self.current_fees2()
  return Period({
    funding_long    : self.slice(fees_i.funding_long_sum,    fees_j.funding_long_sum),
    funding_short   : self.slice(fees_i.funding_short_sum,   fees_j.funding_short_sum),
    received_long   : self.slice(fees_i.received_long_sum,   fees_j.received_long_sum),
    received_short  : self.slice(fees_i.received_short_sum,  fees_j.received_short_sum),
  })

@external
@view
def calc2(long: bool, collateral: uint256, opened_at: uint256) -> SumFees:
    period: Period  = self.query2(opened_at)
    P_f   : uint256 = self.apply2(collateral, period.funding_long) if long else (
                      self.apply2(collateral, period.funding_short) )
    R_f   : uint256 = self.multiply(collateral, period.received_long) if long else (
                      self.multiply(collateral, period.received_short) )

    return SumFees({funding_paid: P_f, funding_received: R_f})
```

</details>

<details>
<summary>Denom.t.sol</summary>

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.13;

import {CheatCodes} from "./Cheat.sol";

import "../../lib/ds-test/test.sol";
import "../../lib/utils/Console.sol";
import "../../lib/utils/VyperDeployer.sol";

import "../IDenom.sol";

contract DenomTest is DSTest {
    ///@notice create a new instance of VyperDeployer
    VyperDeployer vyperDeployer = new VyperDeployer();
    CheatCodes vm = CheatCodes(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    IDenom denom;
    uint256 constant YEAR = (60*60*24*(365) + 60*60*24 / 4); //includes leap year

    function setUp() public {
        vm.roll(1);
        ///@notice deploy a new instance of ISimplestore by passing in the address of the deployed Vyper contract
        denom = IDenom(vyperDeployer.deployContract("Denom"));
    }

    function testDenom() public {
        uint256 blocksInYr = (YEAR) / 2;

        vm.roll(blocksInYr);

        denom.update();

        // pools were initialized at block 0
        denom.calc(true, 1e25, 0);
        denom.calc2(true, 1e25, 0);
    }   

        function testRounding() public {
        uint max_fee = 100; // set max 8-hour rate to 0.288% (157.8% annually)

        uint256 reserves = 10_000_000 ether;
        uint256 interest1 = 1_000_000 ether;
        uint256 interest2 = 1_099_999 ether;

        uint256 util1 = denom.utilization(reserves, interest1);
        uint256 util2 = denom.utilization(reserves, interest2);

        assertEq(util1, util2); // current calculation yields same utilization for both interests

        // borrow rate
        uint fee1 = denom.scale(max_fee, util1); 
        uint fee2 = denom.scale(max_fee, util2);

        assertEq(fee1, fee2); // results in the same fee also. fee2 should be ~1% higher
    }

    function testCombined() public {
        // now let's see what would happen if we raised the precision of both fees and percents
        uint max_fee = 65;
        uint max_fee2 = 65_000; // 3 extra digits of precision lowers error by 3 orders of magnitude

        uint256 reserves = 10_000_000 ether;
        uint256 interest = 199_999 ether; // interest & reserves same in both, only differ in precision.

        uint256 util1 = denom.utilization(reserves, interest); 
        uint256 util2 = denom.utilization2(reserves, interest); // 3 extra digits of precision here also
        
        // borrow rate
        uint fee1 = denom.scale(max_fee, util1); 
        uint fee2 = denom.scale2(max_fee2, util2);

        assertEq(fee1 * 1_000, fee2 - 999); // fee 1 is 1.000, fee 2 is 1.999 (~50% error)
    }
}

```

</details>

<details>
<summary>Cheat.sol</summary>
```solidity
interface CheatCodes {
    // This allows us to getRecordedLogs()
    struct Log {
        bytes32[] topics;
        bytes data;
    }

    // Possible caller modes for readCallers()
    enum CallerMode {
        None,
        Broadcast,
        RecurrentBroadcast,
        Prank,
        RecurrentPrank
    }

    enum AccountAccessKind {
        Call,
        DelegateCall,
        CallCode,
        StaticCall,
        Create,
        SelfDestruct,
        Resume
    }

    struct Wallet {
        address addr;
        uint256 publicKeyX;
        uint256 publicKeyY;
        uint256 privateKey;
    }

    struct ChainInfo {
        uint256 forkId;
        uint256 chainId;
    }

    struct AccountAccess {
        ChainInfo chainInfo;
        AccountAccessKind kind;
        address account;
        address accessor;
        bool initialized;
        uint256 oldBalance;
        uint256 newBalance;
        bytes deployedCode;
        uint256 value;
        bytes data;
        bool reverted;
        StorageAccess[] storageAccesses;
    }

    struct StorageAccess {
        address account;
        bytes32 slot;
        bool isWrite;
        bytes32 previousValue;
        bytes32 newValue;
        bool reverted;
    }

    // Derives a private key from the name, labels the account with that name, and returns the wallet
    function createWallet(string calldata) external returns (Wallet memory);

    // Generates a wallet from the private key and returns the wallet
    function createWallet(uint256) external returns (Wallet memory);

    // Generates a wallet from the private key, labels the account with that name, and returns the wallet
    function createWallet(uint256, string calldata) external returns (Wallet memory);

    // Signs data, (Wallet, digest) => (v, r, s)
    function sign(Wallet calldata, bytes32) external returns (uint8, bytes32, bytes32);

    // Get nonce for a Wallet
    function getNonce(Wallet calldata) external returns (uint64);

    // Set block.timestamp
    function warp(uint256) external;

    // Set block.number
    function roll(uint256) external;

    // Set block.basefee
    function fee(uint256) external;

    // Set block.difficulty
    // Does not work from the Paris hard fork and onwards, and will revert instead.
    function difficulty(uint256) external;
    
    // Set block.prevrandao
    // Does not work before the Paris hard fork, and will revert instead.
    function prevrandao(bytes32) external;

    // Set block.chainid
    function chainId(uint256) external;

    // Loads a storage slot from an address
    function load(address account, bytes32 slot) external returns (bytes32);

    // Stores a value to an address' storage slot
    function store(address account, bytes32 slot, bytes32 value) external;

    // Signs data
    function sign(uint256 privateKey, bytes32 digest)
        external
        returns (uint8 v, bytes32 r, bytes32 s);

    // Computes address for a given private key
    function addr(uint256 privateKey) external returns (address);

    // Derive a private key from a provided mnemonic string,
    // or mnemonic file path, at the derivation path m/44'/60'/0'/0/{index}.
    function deriveKey(string calldata, uint32) external returns (uint256);
    // Derive a private key from a provided mnemonic string, or mnemonic file path,
    // at the derivation path {path}{index}
    function deriveKey(string calldata, string calldata, uint32) external returns (uint256);

    // Gets the nonce of an account
    function getNonce(address account) external returns (uint64);

    // Sets the nonce of an account
    // The new nonce must be higher than the current nonce of the account
    function setNonce(address account, uint64 nonce) external;

    // Performs a foreign function call via terminal
    function ffi(string[] calldata) external returns (bytes memory);

    // Set environment variables, (name, value)
    function setEnv(string calldata, string calldata) external;

    // Read environment variables, (name) => (value)
    function envBool(string calldata) external returns (bool);
    function envUint(string calldata) external returns (uint256);
    function envInt(string calldata) external returns (int256);
    function envAddress(string calldata) external returns (address);
    function envBytes32(string calldata) external returns (bytes32);
    function envString(string calldata) external returns (string memory);
    function envBytes(string calldata) external returns (bytes memory);

    // Read environment variables as arrays, (name, delim) => (value[])
    function envBool(string calldata, string calldata)
        external
        returns (bool[] memory);
    function envUint(string calldata, string calldata)
        external
        returns (uint256[] memory);
    function envInt(string calldata, string calldata)
        external
        returns (int256[] memory);
    function envAddress(string calldata, string calldata)
        external
        returns (address[] memory);
    function envBytes32(string calldata, string calldata)
        external
        returns (bytes32[] memory);
    function envString(string calldata, string calldata)
        external
        returns (string[] memory);
    function envBytes(string calldata, string calldata)
        external
        returns (bytes[] memory);

    // Read environment variables with default value, (name, value) => (value)
    function envOr(string calldata, bool) external returns (bool);
    function envOr(string calldata, uint256) external returns (uint256);
    function envOr(string calldata, int256) external returns (int256);
    function envOr(string calldata, address) external returns (address);
    function envOr(string calldata, bytes32) external returns (bytes32);
    function envOr(string calldata, string calldata) external returns (string memory);
    function envOr(string calldata, bytes calldata) external returns (bytes memory);
    
    // Read environment variables as arrays with default value, (name, value[]) => (value[])
    function envOr(string calldata, string calldata, bool[] calldata) external returns (bool[] memory);
    function envOr(string calldata, string calldata, uint256[] calldata) external returns (uint256[] memory);
    function envOr(string calldata, string calldata, int256[] calldata) external returns (int256[] memory);
    function envOr(string calldata, string calldata, address[] calldata) external returns (address[] memory);
    function envOr(string calldata, string calldata, bytes32[] calldata) external returns (bytes32[] memory);
    function envOr(string calldata, string calldata, string[] calldata) external returns (string[] memory);
    function envOr(string calldata, string calldata, bytes[] calldata) external returns (bytes[] memory);

    // Convert Solidity types to strings
    function toString(address) external returns(string memory);
    function toString(bytes calldata) external returns(string memory);
    function toString(bytes32) external returns(string memory);
    function toString(bool) external returns(string memory);
    function toString(uint256) external returns(string memory);
    function toString(int256) external returns(string memory);

    // Sets the *next* call's msg.sender to be the input address
    function prank(address) external;

    // Sets all subsequent calls' msg.sender to be the input address
    // until `stopPrank` is called
    function startPrank(address) external;

    // Sets the *next* call's msg.sender to be the input address,
    // and the tx.origin to be the second input
    function prank(address, address) external;

    // Sets all subsequent calls' msg.sender to be the input address until
    // `stopPrank` is called, and the tx.origin to be the second input
    function startPrank(address, address) external;

    // Resets subsequent calls' msg.sender to be `address(this)`
    function stopPrank() external;

    // Reads the current `msg.sender` and `tx.origin` from state and reports if there is any active caller modification
    function readCallers() external returns (CallerMode callerMode, address msgSender, address txOrigin);

    // Sets an address' balance
    function deal(address who, uint256 newBalance) external;
    
    // Sets an address' code
    function etch(address who, bytes calldata code) external;

    // Marks a test as skipped. Must be called at the top of the test.
    function skip(bool skip) external;

    // Expects an error on next call
    function expectRevert() external;
    function expectRevert(bytes calldata) external;
    function expectRevert(bytes4) external;

    // Record all storage reads and writes
    function record() external;

    // Gets all accessed reads and write slot from a recording session,
    // for a given address
    function accesses(address)
        external
        returns (bytes32[] memory reads, bytes32[] memory writes);
    
    // Record all account accesses as part of CREATE, CALL or SELFDESTRUCT opcodes in order,
    // along with the context of the calls.
    function startStateDiffRecording() external;

    // Returns an ordered array of all account accesses from a `startStateDiffRecording` session.
    function stopAndReturnStateDiff() external returns (AccountAccess[] memory accesses);

    // Record all the transaction logs
    function recordLogs() external;

    // Gets all the recorded logs
    function getRecordedLogs() external returns (Log[] memory);

    // Prepare an expected log with the signature:
    //   (bool checkTopic1, bool checkTopic2, bool checkTopic3, bool checkData).
    //
    // Call this function, then emit an event, then call a function.
    // Internally after the call, we check if logs were emitted in the expected order
    // with the expected topics and data (as specified by the booleans)
    //
    // The second form also checks supplied address against emitting contract.
    function expectEmit(bool, bool, bool, bool) external;
    function expectEmit(bool, bool, bool, bool, address) external;

    // Mocks a call to an address, returning specified data.
    //
    // Calldata can either be strict or a partial match, e.g. if you only
    // pass a Solidity selector to the expected calldata, then the entire Solidity
    // function will be mocked.
    function mockCall(address, bytes calldata, bytes calldata) external;

    // Reverts a call to an address, returning the specified error
    //
    // Calldata can either be strict or a partial match, e.g. if you only
    // pass a Solidity selector to the expected calldata, then the entire Solidity
    // function will be mocked.
    function mockCallRevert(address where, bytes calldata data, bytes calldata retdata) external;

    // Clears all mocked and reverted mocked calls
    function clearMockedCalls() external;

    // Expect a call to an address with the specified calldata.
    // Calldata can either be strict or a partial match
    function expectCall(address callee, bytes calldata data) external;
    // Expect a call to an address with the specified
    // calldata and message value.
    // Calldata can either be strict or a partial match
    function expectCall(address callee, uint256, bytes calldata data) external;

    // Gets the _creation_ bytecode from an artifact file. Takes in the relative path to the json file
    function getCode(string calldata) external returns (bytes memory);
    // Gets the _deployed_ bytecode from an artifact file. Takes in the relative path to the json file
    function getDeployedCode(string calldata) external returns (bytes memory);

    // Label an address in test traces
    function label(address addr, string calldata label) external;
    
    // Retrieve the label of an address
    function getLabel(address addr) external returns (string memory);

    // When fuzzing, generate new inputs if conditional not met
    function assume(bool) external;

    // Set block.coinbase (who)
    function coinbase(address) external;

    // Using the address that calls the test contract or the address provided
    // as the sender, has the next call (at this call depth only) create a
    // transaction that can later be signed and sent onchain
    function broadcast() external;
    function broadcast(address) external;

    // Using the address that calls the test contract or the address provided
    // as the sender, has all subsequent calls (at this call depth only) create
    // transactions that can later be signed and sent onchain
    function startBroadcast() external;
    function startBroadcast(address) external;
    function startBroadcast(uint256 privateKey) external;

    // Stops collecting onchain transactions
    function stopBroadcast() external;

    // Reads the entire content of file to string, (path) => (data)
    function readFile(string calldata) external returns (string memory);
    // Get the path of the current project root
    function projectRoot() external returns (string memory);
    // Reads next line of file to string, (path) => (line)
    function readLine(string calldata) external returns (string memory);
    // Writes data to file, creating a file if it does not exist, and entirely replacing its contents if it does.
    // (path, data) => ()
    function writeFile(string calldata, string calldata) external;
    // Writes line to file, creating a file if it does not exist.
    // (path, data) => ()
    function writeLine(string calldata, string calldata) external;
    // Closes file for reading, resetting the offset and allowing to read it from beginning with readLine.
    // (path) => ()
    function closeFile(string calldata) external;
    // Removes file. This cheatcode will revert in the following situations, but is not limited to just these cases:
    // - Path points to a directory.
    // - The file doesn't exist.
    // - The user lacks permissions to remove the file.
    // (path) => ()
    function removeFile(string calldata) external;
    // Returns true if the given path points to an existing entity, else returns false
    // (path) => (bool)
    function exists(string calldata) external returns (bool);
    // Returns true if the path exists on disk and is pointing at a regular file, else returns false
    // (path) => (bool)
    function isFile(string calldata) external returns (bool);
    // Returns true if the path exists on disk and is pointing at a directory, else returns false
    // (path) => (bool)
    function isDir(string calldata) external returns (bool);
    
    // Return the value(s) that correspond to 'key'
    function parseJson(string memory json, string memory key) external returns (bytes memory);
    // Return the entire json file
    function parseJson(string memory json) external returns (bytes memory);
    // Check if a key exists in a json string
    function keyExists(string memory json, string memory key) external returns (bytes memory);
    // Get list of keys in a json string
    function parseJsonKeys(string memory json, string memory key) external returns (string[] memory);

    // Snapshot the current state of the evm.
    // Returns the id of the snapshot that was created.
    // To revert a snapshot use `revertTo`
    function snapshot() external returns (uint256);
    // Revert the state of the evm to a previous snapshot
    // Takes the snapshot id to revert to.
    // This deletes the snapshot and all snapshots taken after the given snapshot id.
    function revertTo(uint256) external returns (bool);

    // Creates a new fork with the given endpoint and block,
    // and returns the identifier of the fork
    function createFork(string calldata, uint256) external returns (uint256);
    // Creates a new fork with the given endpoint and the _latest_ block,
    // and returns the identifier of the fork
    function createFork(string calldata) external returns (uint256);

    // Creates _and_ also selects a new fork with the given endpoint and block,
    // and returns the identifier of the fork
    function createSelectFork(string calldata, uint256)
        external
        returns (uint256);
    // Creates _and_ also selects a new fork with the given endpoint and the
    // latest block and returns the identifier of the fork
    function createSelectFork(string calldata) external returns (uint256);

    // Takes a fork identifier created by `createFork` and
    // sets the corresponding forked state as active.
    function selectFork(uint256) external;

    // Returns the currently active fork
    // Reverts if no fork is currently active
    function activeFork() external returns (uint256);

    // Updates the currently active fork to given block number
    // This is similar to `roll` but for the currently active fork
    function rollFork(uint256) external;
    // Updates the given fork to given block number
    function rollFork(uint256 forkId, uint256 blockNumber) external;

    // Fetches the given transaction from the active fork and executes it on the current state
    function transact(bytes32) external;
    // Fetches the given transaction from the given fork and executes it on the current state
    function transact(uint256, bytes32) external;

    // Marks that the account(s) should use persistent storage across
    // fork swaps in a multifork setup, meaning, changes made to the state
    // of this account will be kept when switching forks
    function makePersistent(address) external;
    function makePersistent(address, address) external;
    function makePersistent(address, address, address) external;
    function makePersistent(address[] calldata) external;
    // Revokes persistent status from the address, previously added via `makePersistent`
    function revokePersistent(address) external;
    function revokePersistent(address[] calldata) external;
    // Returns true if the account is marked as persistent
    function isPersistent(address) external returns (bool);

    /// Returns the RPC url for the given alias
    function rpcUrl(string calldata) external returns (string memory);
    /// Returns all rpc urls and their aliases `[alias, url][]`
    function rpcUrls() external returns (string[2][] memory);
}
```

</details>

<details>
<summary>IDenom.sol</summary>

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.13;

interface IDenom {
    function update() external;
    function calc(bool, uint256, uint256) external returns(SumFees memory);
    function calc2(bool, uint256, uint256) external returns(SumFees memory);

    function utilization(uint256, uint256) external returns(uint256);
    function utilization2(uint256, uint256) external returns(uint256);
    function scale(uint256, uint256) external returns(uint256);
    function scale2(uint256, uint256) external returns(uint256);
  
    struct SumFees{
        uint256 funding_paid;
        uint256 funding_received;
    }
}
```

</details>

## Tool used

Manual Review

## Recommendation
Consider increasing the precision of `DENOM` by atleast 3 digits, i.e. `DENOM: constant(uint256) = 1_000_000_000_000` instead of `1_000_000_000`. Consider increasing the precision of percentages by 3 digits, i.e. divide / multiply by 100_000 instead of 100.

Each added digit of precision decreases the precision loss by an order of magnitude. In other words the 1% and 1.5% absolute errors in precision would shrink to 0.01% and 0.015% when using three extra digits of precision.

Consult `Denom.vy` for further guidance on necessary adjustments to make to the various functions to account for these updated values.

# Issue M-11: Inequitable Fee Application Penalizes Lower Leverage Positions and LPs 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/68 

## Found by 
0xbranded
## Summary
Funding rates are [typically applied](https://www.investopedia.com/what-are-perpetual-futures-7494870) to the [notional value](https://www.investopedia.com/terms/n/notionalvalue.asp) of a perpetual futures contract. However, the application of all fees in the protocol only takes into account the collateral value of the position. This is despite the `interest` of a pool determining both locked `reserves` and the values of dynamic rates. 

Positions with high leverage not only lock more `reserves`, but also increase the funding/borrowing rates more than positions with low leverage. These increased rates apply equally to all positions, penalizing low leverage positions which have to pay disproportionately more fees relative to their `interest` contribution, and face elevated liquidation risk as a result.

The protocol, and LPs are also penalized by these higher leverage positions, since they will earn less fees while locking the same amount of `reserves`. While the risk of liquidation is higher for these positions, the lower notional fees establish added perverse incentives for taking on high leverage than would otherwise be the case. As a result, positions with low leverage will pay far greater fees and LPs (as well as the protocol) earn less fees than they otherwise would for locking up the same amount of capital.

## Vulnerability Detail
When applying borrowing and funding fees to a position, the `calc` function of [`fees.vy`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/fees.vy#L265-L270) is utilized:

```vyper
def calc(id: uint256, long: bool, collateral: uint256, opened_at: uint256) -> SumFees:
    period: Period  = self.query(id, opened_at)
    P_b   : uint256 = self.apply(collateral, period.borrowing_long) if long else (
                      self.apply(collateral, period.borrowing_short) )
    P_f   : uint256 = self.apply(collateral, period.funding_long) if long else (
                      self.apply(collateral, period.funding_short) )
...
```

which queries the globally accrued interest during the time the position was active, and applies it to the `collateral` value using the `apply` function of [`math.vy`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/math.vy#L167):

```vyper
def apply(x: uint256, numerator: uint256) -> Fee:
  fee      : uint256 = (x * numerator) / DENOM
...
```

Finally, when opening a position for the first time (in [`core.vy`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/core.vy#L244)) a static fee is also applied directly to the collateral value (from [`params.vy`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/params.vy#L93):

```vyper
def open(
...
  cf         : Fee       = self.PARAMS.static_fees(collateral0)
  collateral : uint256   = cf.remaining
...

def static_fees(collateral: uint256) -> Fee:
  fee      : uint256 = collateral / self.PARAMS.PROTOCOL_FEE
  remaining: uint256 = collateral - fee
  return Fee({x: collateral, fee: fee, remaining: remaining})
```
 
In effect, all fees are applied directly to the collateral value of positions and ignore the value of the leverage, or corresponding open-interest. As such, a position with higher `collateral` will always pay more fees than one with less `collateral`, even if the former has a lower `interest`. 

Positions which take on a higher `leverage` and corresponding`interest` value contribute disproportionately to the [funding and borrowing rates for their side](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/params.vy#L33-L55), by pushing up the `utilization`:

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
...

def utilization(reserves: uint256, interest: uint256) -> uint256:
    return 0 if (reserves == 0 or interest == 0) else (interest / (reserves / 100))
    })
```

Note that the fee calculations are also utilized in determining whether a given position is liquidatable in [`positions.vy`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/positions.vy#L352):

```vyper
def is_liquidatable(id: uint256, ctx: Ctx) -> bool:
  v: PositionValue = Positions(self).value(id, ctx)
  return self.PARAMS.is_liquidatable(v.position, v.pnl)

def value(id: uint256, ctx: Ctx) -> PositionValue:
  pos   : PositionState = Positions(self).lookup(id)
  fees  : FeesPaid      = Positions(self).calc_fees(id)
  pnl   : PnL           = Positions(self).calc_pnl(id, ctx, fees.remaining) # collateral less fees used here
...
  return PositionValue({position: pos, fees: fees, pnl: pnl, deltas: deltas})

def is_liquidatable(position: PositionState, pnl: PnL) -> bool:
    percent : uint256 = self.PARAMS.LIQUIDATION_THRESHOLD * position.leverage
    required: uint256 = (position.collateral * percent) / 100
    return not (pnl.remaining > required)
```

where the collateral + PnL - (dynamic) fees is compared with some fraction of the original collateral balance. All positions on the same side of a pool face the same dynamic rates, regardless of their level of leverage.

## Impact
Positions with higher than average leverage pay less fees as a fraction of their notional value. Since the same global rates are assessed on all positions of the same side of a pool, high leverage positions are effectively subsidized by lower leverage ones. High leverage positions will also take significantly longer to liquidate than they otherwise would if their contribution to their pool's `interest` was taken into account. 

They also drive up the dynamic rates more, and lock a greater quantity of global reserves than those having less leverage. Since they pay less notional fees than positions with lower leverage, perverse incentives further encourage taking out greater leverage than normal.

As a result, lower leverage positions will pay more fees than they otherwise would. They pay a far greater share of the global funding and borrowing fees relative to the amount of `interest` that LPs will potentially need to pay out for their winning positions. They also face increased risk of liquidation since the elevated fees increases the likelihood of a wipeout, as well as reducing the amount of time until absolute fee liquidation.

The high leverage positions on one side of a pool will liquidate from fees at the same rate as lower leverage positions, despite providing far less collateral. If the leverage were taken into account, these positions would liquidate multiple times faster due to fees alone. These positions have high open-interest and contribute disproportionately to the locked reserves. As a result, LPs face greater counterparty risk, especially during trending market conditions where PnL liquidations are less likely. Additionally, they receive less fees which further reduces the risk-reward of providing liquidity. 

As a demonstration, consider the following pool with `base_reserves = quote_reserves = 1e7 * 1e18`. It's assumed to have `quote_interest = 4e5 * 1e18` and `base_collateral = 2e5 * 1e18`. For simplicity, it has only two open long positions with the same collateral (but differing leverage):
1. `quote_collateral = 1e5 * 1e18`, but `base_interest = 1e6 * 1e18` (10x leverage)
2. `quote_collateral = 1e5 * 1e18`, but `base_interest = 2e5 * 1e18` (2x leverage)

Further, assume [`PARAMS.MAX_FEE = 300`](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/params.vy#L43). Both positions were opened in the same block, and both closed exactly 1 calendar year later. Pool conditions are assumed to have remained the same. 

The combined `quote_collateral = 2e5 * 1e18`, and `base_interest = 12e5 * 1e8`. Using the reserves from earlier, this results in a long utilization of 12%, which corresponds to a borrowing rate of `r = 36`, using the `PARAMS.MAX_FEE = 300` from earlier. The short utilization is calculated to be 4%, thus the imbalance in funding rates is 8% for longs, resulting in a funding rate of `r = 2` using the same `PARAMS.MAX_FEE = 300`.

Given the [2 second blocktime](https://explorer.gobob.xyz/) on BOB chain, these positions were closed after 15_768_000 blocks, in which time they each accrued an 56.76% borrow fee and 3.15% funding fee - a total fee of 59.9%. Since both positions had `quote_collateral = 1e5 * 1e18`, their quote collateral was discounted by the same amount before calculating PnL: `0.599e5 * 1e18`.

Note that both positions paid the same percentage and nominal fee rates. However the first position took up 10% of the base reserves, while the second took up only 2% **yet they paid the exact same fees.**

 To further emphasize this point, let's look at two scenarios where each position has the same leverage, and the total `base_interest` is the same.
- Keep position 1. For position 2, `quote_collateral = 2e4 * 1e18` and `base_interest = 2e5 * 1e18`
- Keep position 2. For position 1, `quote_collateral = 5e5 * 1e18` and `base_interest = 1e6 * 1e18`

The same borrow / funding rates from before apply since the overall `reserves` and `interest` didn't change. Position 2 now pays a nominal fee of just `0.1198e5 * 1e18`, which is a fifth of that paid before. Position 1 now pays a nominal fee of `2.995e5 * 1e18`, which is five times what was paid before.

In either case, the same amount of reserves were used. However, when the total pool leverage is 10x, the total fee subtracted from longs was `0.7189e5 * 1e18` tokens, and when it was 2x, the total fee was `3.594e5 * 1e18` tokens. **Five times more fee tokens were paid when the total pool leverage was 5x higher, despite the same level of reserves (counterparty risk) in either case.**

Significant loss of funds occurs due to inflated fees by lower-leveraged positions, and decreased fee receipts from the protocol and LPs. It will also disrupt the normal liquidation process, as lower-leveraged positions will liquidate at a faster clip than they otherwise would. LP funds are locked for a longer duration than they would be if the fee was assessed fairly on the notional value of these high leverage positions.

## Code Snippet
For the PoC, `r = 10`, `long_collateral = short_collateral = 10^7 * 10^18` and `n = 6.3 * 10^7` blocks (4 years), as outlined above.

The smart contracts were stripped to isolate the relevant logic, and [foundry](https://github.com/0xKitsune/Foundry-Vyper) was used for testing. To run the test, clone the repo and place `Leverage.vy` in `vyper_contracts`, and place `Leverage.t.sol`, `Cheat.sol`, and `ILeverage.sol` under `src/test`.
<details>
<summary>Leverage.vy</summary>

```vyper

struct PositionState:
  collateral : uint256
  interest   : uint256

struct DynFees:
  borrowing_long : uint256
  borrowing_short: uint256
  funding_long   : uint256
  funding_short  : uint256

struct PoolState:
  base_reserves    : uint256
  quote_reserves   : uint256
  base_interest    : uint256
  quote_interest   : uint256
  base_collateral  : uint256
  quote_collateral : uint256

# need to edit all old stuff returning ps
# struct PoolState:
#   base_collateral  : uint256
#   quote_collateral : uint256

#added borrowing long & borrowing short, update it elsewhere
struct FeeState:
  t1                   : uint256
  funding_long         : uint256
  borrowing_long       : uint256
  funding_short        : uint256
  borrowing_short      : uint256
  long_collateral      : uint256
  short_collateral     : uint256
  borrowing_long_sum   : uint256
  borrowing_short_sum  : uint256
  funding_long_sum     : uint256
  funding_short_sum    : uint256
  received_long_sum    : uint256
  received_short_sum   : uint256

struct SumFees:
  total: uint256
  funding_paid    : uint256
  funding_received: uint256
  borrowing_paid: uint256

struct Period:
  borrowing_long : uint256
  borrowing_short: uint256
  funding_long   : uint256
  funding_short  : uint256
  received_long  : uint256
  received_short : uint256

MAX_FEE: uint256
MIN_FEE: uint256

FEE_STORE: FeeState
FEE_STORE_AT: HashMap[uint256, FeeState]

POOL_STORE: PoolState

POSITION_STORE: PositionState
POSITION_STORE2: PositionState

#starting point hardcoded
@external
def __init__(_qc: uint256, _bi: uint256, _qc2: uint256, _bi2: uint256):
  self.MAX_FEE = 0
  self.MAX_FEE = 300

  self.POOL_STORE = PoolState({
  base_reserves    : 10_000_000_000_000_000_000_000_000,
  quote_reserves   : 10_000_000_000_000_000_000_000_000,
  base_interest    : _bi + _bi2,
  quote_interest   : 400_000_000_000_000_000_000_000,
  base_collateral  : 200_000_000_000_000_000_000_000,
  quote_collateral : _qc + _qc2,
  })

  starting_fees: DynFees = self.dynamic_fees()

  self.FEE_STORE = FeeState({
  t1                   : 1,
  funding_long         : starting_fees.funding_long,
  borrowing_long       : starting_fees.borrowing_long,
  funding_short        : starting_fees.funding_short,
  borrowing_short      : starting_fees.borrowing_short,
  long_collateral      : _qc + _qc2,
  short_collateral     : 200_000_000_000_000_000_000_000,
  borrowing_long_sum   : 0,
  borrowing_short_sum  : 0,
  funding_long_sum     : 0,
  funding_short_sum    : 0,
  received_long_sum    : 0,
  received_short_sum   : 0,
  })

  self.FEE_STORE_AT[1] = self.FEE_STORE

  self.POSITION_STORE = PositionState({
  collateral: _qc,
  interest: _bi,
  })

  self.POSITION_STORE2 = PositionState({
  collateral: _qc2,
  interest: _bi2,
  })

@internal
@view
def dynamic_fees() -> DynFees:
    pool: PoolState = self.POOL_STORE

    long_utilization : uint256 = self.utilization(pool.base_reserves, pool.base_interest)
    short_utilization: uint256 = self.utilization(pool.quote_reserves, pool.quote_interest)
    borrowing_long   : uint256 = self.check_fee(
      self.scale(self.MAX_FEE, long_utilization))
    borrowing_short  : uint256 = self.check_fee(
      self.scale(self.MAX_FEE, short_utilization))
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

@internal
@pure
def utilization(reserves: uint256, interest: uint256) -> uint256:
    return 0 if (reserves == 0 or interest == 0) else (interest / (reserves / 100))

@internal
@pure
def scale(fee: uint256, utilization: uint256) -> uint256:
    return (fee * utilization) / 100

@internal
@view
def check_fee(fee: uint256) -> uint256:
    if self.MIN_FEE <= fee and fee <= self.MAX_FEE: return fee
    elif fee < self.MIN_FEE                       : return self.MIN_FEE
    else                                          : return self.MAX_FEE

@internal
@pure
def imbalance(n: uint256, m: uint256) -> uint256:
    return n - m if n >= m else 0

@internal
@view
def funding_fee(base_fee: uint256, col1: uint256, col2: uint256) -> uint256:
  imb: uint256 = self.imbalance(col1, col2)
  if imb == 0: return 0
  else       : return self.check_fee(self.scale(base_fee, imb))

# #hardcoded pool to have 1e24 of quote and base collateral
@internal
@view
def lookup() -> PoolState:
  return self.POOL_STORE

@internal
@view
def lookupFees() -> FeeState:
  return self.FEE_STORE 

@internal
@view
def fees_at_block(height: uint256) -> FeeState:
  return self.FEE_STORE_AT[height]

@external
def update():
  fs: FeeState = self.current_fees()

  self.FEE_STORE = fs


#math
ZEROS: constant(uint256) = 1000000000000000000000000000
DENOM: constant(uint256) = 1_000_000_000

@internal
@pure
def extend(X: uint256, x_m: uint256, m: uint256) -> uint256:
  return X + (m*x_m)

@internal
@pure
def apply(x: uint256, numerator: uint256) -> uint256:
  """
  Fees are represented as numerator only, with the denominator defined
  here. This computes x*fee capped at x.
  """
  fee      : uint256 = (x * numerator) / DENOM
  fee_     : uint256 = fee     if fee <= x else x
  return fee_

@internal
@pure
def divide(paid: uint256, collateral: uint256) -> uint256:
  if collateral == 0: return 0
  else              : return (paid * ZEROS) / collateral

@internal
@pure
def multiply(ci: uint256, terms: uint256) -> uint256:
  return (ci * terms) / ZEROS

@internal
@pure
def slice(y_i: uint256, y_j: uint256) -> uint256:
  return y_j - y_i

@internal
@view
def current_fees() -> FeeState:
  """
  Update incremental fee state, called whenever the pool state changes.
  """
  # prev/last updated state
  fs       : FeeState  = self.lookupFees()
  # current state
  ps       : PoolState = self.lookup()
  new_fees : DynFees   = self.dynamic_fees()
  # number of blocks elapsed
  new_terms: uint256   = block.number - fs.t1

  borrowing_long_sum  : uint256 = self.extend(fs.borrowing_long_sum,  fs.borrowing_long,  new_terms)
  borrowing_short_sum : uint256 = self.extend(fs.borrowing_short_sum, fs.borrowing_short, new_terms)
  funding_long_sum    : uint256 = self.extend(fs.funding_long_sum,    fs.funding_long,    new_terms)
  funding_short_sum   : uint256 = self.extend(fs.funding_short_sum,   fs.funding_short,   new_terms)

  paid_long_term      : uint256 = self.apply(fs.long_collateral, fs.funding_long * new_terms)
  received_short_term : uint256 = self.divide(paid_long_term,    fs.short_collateral)

  paid_short_term     : uint256 = self.apply(fs.short_collateral, fs.funding_short * new_terms)
  received_long_term  : uint256 = self.divide(paid_short_term,    fs.long_collateral)

  received_long_sum   : uint256 = self.extend(fs.received_long_sum,  received_long_term,  1)
  received_short_sum  : uint256 = self.extend(fs.received_short_sum, received_short_term, 1)

  if new_terms == 0:
    return FeeState({
    t1                   : fs.t1,
    funding_long         : new_fees.funding_long,
    borrowing_long       : new_fees.borrowing_long,
    funding_short        : new_fees.funding_short,
    borrowing_short      : new_fees.borrowing_short,
    long_collateral      : ps.quote_collateral,
    short_collateral     : ps.base_collateral,
    borrowing_long_sum   : fs.borrowing_long_sum,
    borrowing_short_sum  : fs.borrowing_short_sum,
    funding_long_sum     : fs.funding_long_sum,
    funding_short_sum    : fs.funding_short_sum,
    received_long_sum    : fs.received_long_sum,
    received_short_sum   : fs.received_short_sum,
    })
  else:
    return FeeState({
    t1                   : block.number,
    funding_long         : new_fees.funding_long,
    borrowing_long       : new_fees.borrowing_long,
    funding_short        : new_fees.funding_short,
    borrowing_short      : new_fees.borrowing_short,
    long_collateral      : ps.quote_collateral,
    short_collateral     : ps.base_collateral,
    borrowing_long_sum   : borrowing_long_sum,
    borrowing_short_sum  : borrowing_short_sum,
    funding_long_sum     : funding_long_sum,
    funding_short_sum    : funding_short_sum,
    received_long_sum    : received_long_sum,
    received_short_sum   : received_short_sum,
    })

@internal
@view
def query(opened_at: uint256) -> Period:
  """
  Return the total fees due from block `opened_at` to the current block.
  """
  fees_i : FeeState = self.fees_at_block(opened_at)
  fees_j : FeeState = self.current_fees()
  return Period({
    borrowing_long    : self.slice(fees_i.borrowing_long_sum,    fees_j.borrowing_long_sum),
    borrowing_short    : self.slice(fees_i.borrowing_short_sum,    fees_j.borrowing_short_sum),
    funding_long    : self.slice(fees_i.funding_long_sum,    fees_j.funding_long_sum),
    funding_short   : self.slice(fees_i.funding_short_sum,   fees_j.funding_short_sum),
    received_long   : self.slice(fees_i.received_long_sum,   fees_j.received_long_sum),
    received_short  : self.slice(fees_i.received_short_sum,  fees_j.received_short_sum),
  })

@external
@view
def calc() -> SumFees:
    long: bool = True
    collateral: uint256 = self.POSITION_STORE.collateral
    opened_at: uint256  = 1

    period: Period  = self.query(opened_at)
    P_b   : uint256 = self.apply(collateral, period.borrowing_long) if long else (
                      self.apply(collateral, period.borrowing_short) )
    P_f   : uint256 = self.apply(collateral, period.funding_long) if long else (
                      self.apply(collateral, period.funding_short) )
    R_f   : uint256 = self.multiply(collateral, period.received_long) if long else (
                      self.multiply(collateral, period.received_short) )

    return SumFees({total: P_f + P_b - R_f, funding_paid: P_f, funding_received: R_f, borrowing_paid: P_b})


@external
@view
def calc2() -> SumFees:
    long: bool = True
    collateral: uint256 = self.POSITION_STORE2.collateral
    opened_at: uint256  = 1

    period: Period  = self.query(opened_at)
    P_b   : uint256 = self.apply(collateral, period.borrowing_long) if long else (
                      self.apply(collateral, period.borrowing_short) )
    P_f   : uint256 = self.apply(collateral, period.funding_long) if long else (
                      self.apply(collateral, period.funding_short) )
    R_f   : uint256 = self.multiply(collateral, period.received_long) if long else (
                      self.multiply(collateral, period.received_short) )

    return SumFees({total: P_f + P_b - R_f, funding_paid: P_f, funding_received: R_f, borrowing_paid: P_b})

```

</details>

<details>
<summary>Leverage.t.sol</summary>

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.13;

import {CheatCodes} from "./Cheat.sol";

import "../../lib/ds-test/test.sol";
import "../../lib/utils/Console.sol";
import "../../lib/utils/VyperDeployer.sol";

import "../ILeverage.sol";

contract LeverageTest is DSTest {
    ///@notice create a new instance of VyperDeployer
    VyperDeployer vyperDeployer = new VyperDeployer();
    CheatCodes vm = CheatCodes(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    ILeverage lev;
    uint256 constant YEAR = 60 * 60 * 24 * 365;
    uint256 blocksInYr = (YEAR) / 2;

    function setUp() public {
        vm.roll(1);
    }

    function testDiffLev() public {
        // quote collateral & base interest of positions as laid out in scenario 1
        uint256 qc = 100_000 ether;
        uint256 bi = 1_000_000 ether;
        uint256 qc2 = 100_000 ether;
        uint256 bi2 = 200_000 ether;

        lev = ILeverage(vyperDeployer.deployContract("Leverage", 
                abi.encode(qc, bi, qc2, bi2)));

        vm.roll(blocksInYr);

        lev.update();

        // pools were initialized at block 0
        lev.calc();
        lev.calc2();
    }   

    function testBoth10x() public {
        // quote collateral & base interest of positions as laid out in scenario 1
        uint256 qc = 100_000 ether;
        uint256 bi = 1_000_000 ether;
        uint256 qc2 = 20_000 ether;
        uint256 bi2 = 200_000 ether;

        lev = ILeverage(vyperDeployer.deployContract("Leverage", 
                abi.encode(qc, bi, qc2, bi2)));

        vm.roll(blocksInYr);

        lev.update();

        // pools were initialized at block 0
        lev.calc();
        lev.calc2();
    }   

    function testBoth2x() public {
        // quote collateral & base interest of positions as laid out in scenario 1
        uint256 qc = 500_000 ether;
        uint256 bi = 1_000_000 ether;
        uint256 qc2 = 100_000 ether;
        uint256 bi2 = 200_000 ether;

        lev = ILeverage(vyperDeployer.deployContract("Leverage", 
                abi.encode(qc, bi, qc2, bi2)));

        vm.roll(blocksInYr);

        lev.update();

        // pools were initialized at block 0
        lev.calc();
        lev.calc2();
    }   
}

```

</details>

<details>
<summary>Cheat.sol</summary>

```solidity
interface CheatCodes {
    // This allows us to getRecordedLogs()
    struct Log {
        bytes32[] topics;
        bytes data;
    }

    // Possible caller modes for readCallers()
    enum CallerMode {
        None,
        Broadcast,
        RecurrentBroadcast,
        Prank,
        RecurrentPrank
    }

    enum AccountAccessKind {
        Call,
        DelegateCall,
        CallCode,
        StaticCall,
        Create,
        SelfDestruct,
        Resume
    }

    struct Wallet {
        address addr;
        uint256 publicKeyX;
        uint256 publicKeyY;
        uint256 privateKey;
    }

    struct ChainInfo {
        uint256 forkId;
        uint256 chainId;
    }

    struct AccountAccess {
        ChainInfo chainInfo;
        AccountAccessKind kind;
        address account;
        address accessor;
        bool initialized;
        uint256 oldBalance;
        uint256 newBalance;
        bytes deployedCode;
        uint256 value;
        bytes data;
        bool reverted;
        StorageAccess[] storageAccesses;
    }

    struct StorageAccess {
        address account;
        bytes32 slot;
        bool isWrite;
        bytes32 previousValue;
        bytes32 newValue;
        bool reverted;
    }

    // Derives a private key from the name, labels the account with that name, and returns the wallet
    function createWallet(string calldata) external returns (Wallet memory);

    // Generates a wallet from the private key and returns the wallet
    function createWallet(uint256) external returns (Wallet memory);

    // Generates a wallet from the private key, labels the account with that name, and returns the wallet
    function createWallet(uint256, string calldata) external returns (Wallet memory);

    // Signs data, (Wallet, digest) => (v, r, s)
    function sign(Wallet calldata, bytes32) external returns (uint8, bytes32, bytes32);

    // Get nonce for a Wallet
    function getNonce(Wallet calldata) external returns (uint64);

    // Set block.timestamp
    function warp(uint256) external;

    // Set block.number
    function roll(uint256) external;

    // Set block.basefee
    function fee(uint256) external;

    // Set block.difficulty
    // Does not work from the Paris hard fork and onwards, and will revert instead.
    function difficulty(uint256) external;
    
    // Set block.prevrandao
    // Does not work before the Paris hard fork, and will revert instead.
    function prevrandao(bytes32) external;

    // Set block.chainid
    function chainId(uint256) external;

    // Loads a storage slot from an address
    function load(address account, bytes32 slot) external returns (bytes32);

    // Stores a value to an address' storage slot
    function store(address account, bytes32 slot, bytes32 value) external;

    // Signs data
    function sign(uint256 privateKey, bytes32 digest)
        external
        returns (uint8 v, bytes32 r, bytes32 s);

    // Computes address for a given private key
    function addr(uint256 privateKey) external returns (address);

    // Derive a private key from a provided mnemonic string,
    // or mnemonic file path, at the derivation path m/44'/60'/0'/0/{index}.
    function deriveKey(string calldata, uint32) external returns (uint256);
    // Derive a private key from a provided mnemonic string, or mnemonic file path,
    // at the derivation path {path}{index}
    function deriveKey(string calldata, string calldata, uint32) external returns (uint256);

    // Gets the nonce of an account
    function getNonce(address account) external returns (uint64);

    // Sets the nonce of an account
    // The new nonce must be higher than the current nonce of the account
    function setNonce(address account, uint64 nonce) external;

    // Performs a foreign function call via terminal
    function ffi(string[] calldata) external returns (bytes memory);

    // Set environment variables, (name, value)
    function setEnv(string calldata, string calldata) external;

    // Read environment variables, (name) => (value)
    function envBool(string calldata) external returns (bool);
    function envUint(string calldata) external returns (uint256);
    function envInt(string calldata) external returns (int256);
    function envAddress(string calldata) external returns (address);
    function envBytes32(string calldata) external returns (bytes32);
    function envString(string calldata) external returns (string memory);
    function envBytes(string calldata) external returns (bytes memory);

    // Read environment variables as arrays, (name, delim) => (value[])
    function envBool(string calldata, string calldata)
        external
        returns (bool[] memory);
    function envUint(string calldata, string calldata)
        external
        returns (uint256[] memory);
    function envInt(string calldata, string calldata)
        external
        returns (int256[] memory);
    function envAddress(string calldata, string calldata)
        external
        returns (address[] memory);
    function envBytes32(string calldata, string calldata)
        external
        returns (bytes32[] memory);
    function envString(string calldata, string calldata)
        external
        returns (string[] memory);
    function envBytes(string calldata, string calldata)
        external
        returns (bytes[] memory);

    // Read environment variables with default value, (name, value) => (value)
    function envOr(string calldata, bool) external returns (bool);
    function envOr(string calldata, uint256) external returns (uint256);
    function envOr(string calldata, int256) external returns (int256);
    function envOr(string calldata, address) external returns (address);
    function envOr(string calldata, bytes32) external returns (bytes32);
    function envOr(string calldata, string calldata) external returns (string memory);
    function envOr(string calldata, bytes calldata) external returns (bytes memory);
    
    // Read environment variables as arrays with default value, (name, value[]) => (value[])
    function envOr(string calldata, string calldata, bool[] calldata) external returns (bool[] memory);
    function envOr(string calldata, string calldata, uint256[] calldata) external returns (uint256[] memory);
    function envOr(string calldata, string calldata, int256[] calldata) external returns (int256[] memory);
    function envOr(string calldata, string calldata, address[] calldata) external returns (address[] memory);
    function envOr(string calldata, string calldata, bytes32[] calldata) external returns (bytes32[] memory);
    function envOr(string calldata, string calldata, string[] calldata) external returns (string[] memory);
    function envOr(string calldata, string calldata, bytes[] calldata) external returns (bytes[] memory);

    // Convert Solidity types to strings
    function toString(address) external returns(string memory);
    function toString(bytes calldata) external returns(string memory);
    function toString(bytes32) external returns(string memory);
    function toString(bool) external returns(string memory);
    function toString(uint256) external returns(string memory);
    function toString(int256) external returns(string memory);

    // Sets the *next* call's msg.sender to be the input address
    function prank(address) external;

    // Sets all subsequent calls' msg.sender to be the input address
    // until `stopPrank` is called
    function startPrank(address) external;

    // Sets the *next* call's msg.sender to be the input address,
    // and the tx.origin to be the second input
    function prank(address, address) external;

    // Sets all subsequent calls' msg.sender to be the input address until
    // `stopPrank` is called, and the tx.origin to be the second input
    function startPrank(address, address) external;

    // Resets subsequent calls' msg.sender to be `address(this)`
    function stopPrank() external;

    // Reads the current `msg.sender` and `tx.origin` from state and reports if there is any active caller modification
    function readCallers() external returns (CallerMode callerMode, address msgSender, address txOrigin);

    // Sets an address' balance
    function deal(address who, uint256 newBalance) external;
    
    // Sets an address' code
    function etch(address who, bytes calldata code) external;

    // Marks a test as skipped. Must be called at the top of the test.
    function skip(bool skip) external;

    // Expects an error on next call
    function expectRevert() external;
    function expectRevert(bytes calldata) external;
    function expectRevert(bytes4) external;

    // Record all storage reads and writes
    function record() external;

    // Gets all accessed reads and write slot from a recording session,
    // for a given address
    function accesses(address)
        external
        returns (bytes32[] memory reads, bytes32[] memory writes);
    
    // Record all account accesses as part of CREATE, CALL or SELFDESTRUCT opcodes in order,
    // along with the context of the calls.
    function startStateDiffRecording() external;

    // Returns an ordered array of all account accesses from a `startStateDiffRecording` session.
    function stopAndReturnStateDiff() external returns (AccountAccess[] memory accesses);

    // Record all the transaction logs
    function recordLogs() external;

    // Gets all the recorded logs
    function getRecordedLogs() external returns (Log[] memory);

    // Prepare an expected log with the signature:
    //   (bool checkTopic1, bool checkTopic2, bool checkTopic3, bool checkData).
    //
    // Call this function, then emit an event, then call a function.
    // Internally after the call, we check if logs were emitted in the expected order
    // with the expected topics and data (as specified by the booleans)
    //
    // The second form also checks supplied address against emitting contract.
    function expectEmit(bool, bool, bool, bool) external;
    function expectEmit(bool, bool, bool, bool, address) external;

    // Mocks a call to an address, returning specified data.
    //
    // Calldata can either be strict or a partial match, e.g. if you only
    // pass a Solidity selector to the expected calldata, then the entire Solidity
    // function will be mocked.
    function mockCall(address, bytes calldata, bytes calldata) external;

    // Reverts a call to an address, returning the specified error
    //
    // Calldata can either be strict or a partial match, e.g. if you only
    // pass a Solidity selector to the expected calldata, then the entire Solidity
    // function will be mocked.
    function mockCallRevert(address where, bytes calldata data, bytes calldata retdata) external;

    // Clears all mocked and reverted mocked calls
    function clearMockedCalls() external;

    // Expect a call to an address with the specified calldata.
    // Calldata can either be strict or a partial match
    function expectCall(address callee, bytes calldata data) external;
    // Expect a call to an address with the specified
    // calldata and message value.
    // Calldata can either be strict or a partial match
    function expectCall(address callee, uint256, bytes calldata data) external;

    // Gets the _creation_ bytecode from an artifact file. Takes in the relative path to the json file
    function getCode(string calldata) external returns (bytes memory);
    // Gets the _deployed_ bytecode from an artifact file. Takes in the relative path to the json file
    function getDeployedCode(string calldata) external returns (bytes memory);

    // Label an address in test traces
    function label(address addr, string calldata label) external;
    
    // Retrieve the label of an address
    function getLabel(address addr) external returns (string memory);

    // When fuzzing, generate new inputs if conditional not met
    function assume(bool) external;

    // Set block.coinbase (who)
    function coinbase(address) external;

    // Using the address that calls the test contract or the address provided
    // as the sender, has the next call (at this call depth only) create a
    // transaction that can later be signed and sent onchain
    function broadcast() external;
    function broadcast(address) external;

    // Using the address that calls the test contract or the address provided
    // as the sender, has all subsequent calls (at this call depth only) create
    // transactions that can later be signed and sent onchain
    function startBroadcast() external;
    function startBroadcast(address) external;
    function startBroadcast(uint256 privateKey) external;

    // Stops collecting onchain transactions
    function stopBroadcast() external;

    // Reads the entire content of file to string, (path) => (data)
    function readFile(string calldata) external returns (string memory);
    // Get the path of the current project root
    function projectRoot() external returns (string memory);
    // Reads next line of file to string, (path) => (line)
    function readLine(string calldata) external returns (string memory);
    // Writes data to file, creating a file if it does not exist, and entirely replacing its contents if it does.
    // (path, data) => ()
    function writeFile(string calldata, string calldata) external;
    // Writes line to file, creating a file if it does not exist.
    // (path, data) => ()
    function writeLine(string calldata, string calldata) external;
    // Closes file for reading, resetting the offset and allowing to read it from beginning with readLine.
    // (path) => ()
    function closeFile(string calldata) external;
    // Removes file. This cheatcode will revert in the following situations, but is not limited to just these cases:
    // - Path points to a directory.
    // - The file doesn't exist.
    // - The user lacks permissions to remove the file.
    // (path) => ()
    function removeFile(string calldata) external;
    // Returns true if the given path points to an existing entity, else returns false
    // (path) => (bool)
    function exists(string calldata) external returns (bool);
    // Returns true if the path exists on disk and is pointing at a regular file, else returns false
    // (path) => (bool)
    function isFile(string calldata) external returns (bool);
    // Returns true if the path exists on disk and is pointing at a directory, else returns false
    // (path) => (bool)
    function isDir(string calldata) external returns (bool);
    
    // Return the value(s) that correspond to 'key'
    function parseJson(string memory json, string memory key) external returns (bytes memory);
    // Return the entire json file
    function parseJson(string memory json) external returns (bytes memory);
    // Check if a key exists in a json string
    function keyExists(string memory json, string memory key) external returns (bytes memory);
    // Get list of keys in a json string
    function parseJsonKeys(string memory json, string memory key) external returns (string[] memory);

    // Snapshot the current state of the evm.
    // Returns the id of the snapshot that was created.
    // To revert a snapshot use `revertTo`
    function snapshot() external returns (uint256);
    // Revert the state of the evm to a previous snapshot
    // Takes the snapshot id to revert to.
    // This deletes the snapshot and all snapshots taken after the given snapshot id.
    function revertTo(uint256) external returns (bool);

    // Creates a new fork with the given endpoint and block,
    // and returns the identifier of the fork
    function createFork(string calldata, uint256) external returns (uint256);
    // Creates a new fork with the given endpoint and the _latest_ block,
    // and returns the identifier of the fork
    function createFork(string calldata) external returns (uint256);

    // Creates _and_ also selects a new fork with the given endpoint and block,
    // and returns the identifier of the fork
    function createSelectFork(string calldata, uint256)
        external
        returns (uint256);
    // Creates _and_ also selects a new fork with the given endpoint and the
    // latest block and returns the identifier of the fork
    function createSelectFork(string calldata) external returns (uint256);

    // Takes a fork identifier created by `createFork` and
    // sets the corresponding forked state as active.
    function selectFork(uint256) external;

    // Returns the currently active fork
    // Reverts if no fork is currently active
    function activeFork() external returns (uint256);

    // Updates the currently active fork to given block number
    // This is similar to `roll` but for the currently active fork
    function rollFork(uint256) external;
    // Updates the given fork to given block number
    function rollFork(uint256 forkId, uint256 blockNumber) external;

    // Fetches the given transaction from the active fork and executes it on the current state
    function transact(bytes32) external;
    // Fetches the given transaction from the given fork and executes it on the current state
    function transact(uint256, bytes32) external;

    // Marks that the account(s) should use persistent storage across
    // fork swaps in a multifork setup, meaning, changes made to the state
    // of this account will be kept when switching forks
    function makePersistent(address) external;
    function makePersistent(address, address) external;
    function makePersistent(address, address, address) external;
    function makePersistent(address[] calldata) external;
    // Revokes persistent status from the address, previously added via `makePersistent`
    function revokePersistent(address) external;
    function revokePersistent(address[] calldata) external;
    // Returns true if the account is marked as persistent
    function isPersistent(address) external returns (bool);

    /// Returns the RPC url for the given alias
    function rpcUrl(string calldata) external returns (string memory);
    /// Returns all rpc urls and their aliases `[alias, url][]`
    function rpcUrls() external returns (string[2][] memory);
}

```

</details>

<details>
<summary>ILeverage.sol</summary>

```solidity
// SPDX-License-Identifier: MIT
pragma solidity >=0.8.13;

interface ILeverage {
    function update() external;
    function calc() external returns(SumFees memory);
    function calc2() external returns(SumFees memory);
  
    struct SumFees{
        uint256 total;
        uint256 funding_paid;
        uint256 funding_received;
        uint256 borrowing_paid;
    }

    struct FeeState{
        uint256 t1;
        uint256 funding_long;
        uint256 borrowing_long;
        uint256 funding_short;
        uint256 borrowing_short;
        uint256 long_collateral;
        uint256 short_collateral;
        uint256 borrowing_long_sum;
        uint256 borrowing_short_sum;
        uint256 funding_long_sum;
        uint256 funding_short_sum;
        uint256 received_long_sum;
        uint256 received_short_sum;
    }
}
```

</details>

## Tool used

Manual Review

## Recommendation
Consider applying all static and dynamic fees on `collateral * leverage`. The accounting for each fee should be consistently updated to use the notional value if this change is implemented.

# Issue M-12: Usage of `tx.origin` to determine the user is prone to attacks 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/82 

## Found by 
Bauer, Greed, Japy69, KupiaSec, Waydou, bughuntoor, ctf\_sec, y4y
## Summary
Usage of `tx.origin` to determine the user is prone to attacks

## Vulnerability Detail
Within `core.vy` to user on whose behalf it is called is fetched by using `tx.origin`.
```vyper
  self._INTERNAL()

  user        : address   = tx.origin
```

This is dangerous, as any time a user calls/ interacts with an unverified contract, or a contract which can change implementation, they're put under risk, as the contract can make a call to `api.vy` and act on user's behalf.

Usage of `tx.origin` would also break compatibility with Account Abstract wallets.

## Impact
Any time a user calls any contract on the BOB chain, they risk getting their funds lost.
Incompatible with AA wallets.

## Code Snippet
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/core.vy#L166

## Tool used

Manual Review

## Recommendation
Instead of using `tx.origin` in `core.vy`, simply pass `msg.sender` as a parameter from `api.vy`

# Issue M-13: Funding Paid != Funding Received 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/83 

## Found by 
0xbranded
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

# Issue M-14: First depositor could DoS the pool 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/85 

## Found by 
bughuntoor
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

# Issue M-15: Liquidity providers can remove liquidity to force positions into high fees 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/88 

## Found by 
4gontuk, bughuntoor
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

# Issue M-16: Whale LP providers can open positions on both sides to force users into high fees. 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/89 

## Found by 
bughuntoor
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

# Issue M-17: Loss of Funds From Profitable Positions Running Out of Collateral 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/90 

## Found by 
0xbranded, Yashar
## Summary
When profitable positions run out of collateral, they receive no payout, even if they had a positive PnL. This is not only disadvantageous to users, but it critically removes all liquidation incentive. These zero'd out positions will continue to underpay fees until someone liquidates the position for no fee, losing money to gas in the process.

## Vulnerability Detail
When calculating the pnl of either a long or short position that is to be closed, if the collateral drops to zero due to fee obligations then they [do not receive a payout](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/positions.vy#L295): 

```vyper
# remaining first calculating in `calc_fees`
  c0              : uint256       = pos.collateral
  c1              : Val           = self.deduct(c0,           fees.funding_paid)
  c2              : Val           = self.deduct(c1.remaining, fees.borrowing_paid)
  # Funding fees prioritized over borrowing fees.
  funding_paid    : uint256       = c1.deducted
  borrowing_paid  : uint256       = c2.deducted
  remaining       : uint256       = c2.remaining

...
# later passed to `calc_pnl`
  final  : uint256       = 0 if remaining == 0 else (
...
# longs
  payout : uint256       = self.MATH.quote_to_base(final, ctx)
...
# shorts
  payout   : uint256 = final
```

However, it's possible for a position to run out of collateral yet still have a positive PnL. In these cases, no payout is received. This [payout is what's sent](https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/positions.vy#L195) to the user **or liquidator** when a position is closed:

```vyper
# longs
    base_transfer   : [self.MATH.PLUS(pnl.payout),
# shorts
    quote_transfer  : [self.MATH.PLUS(pnl.payout),
```

In these cases neither the user closing his position, nor the liquidator receives any payment. 

## Impact
While it may be intended design to penalize users for letting a position run out of collateral, this is a dangerous design choice. It's possible to end up in a situation where a position has run negative due to the funding fees and now has no incentive for liquidation. This will be the case even if it could have been profitable to liquidate this position due to the PnL of the position. 

This scenario is dependent on liquidation bots malfunctioning since the liquidatability of a position does not factor in profit (only losses). However, it is acknowledged as a possibility that this scenario may occur throughout the codebase as safeguards are introduced to protect against this scenario elsewhere. In this particular scenario, no particular safeguard exists.

These positions will continue to decay causing further damage to the system until someone is willing to liquidate the position for no payment. It is unlikely that a liquidation bot would be willing to lose money to do so and would likely require admin intervention. By the time admin intervenes, it's most likely that further losses would have already resulted from the decay of the position. 

## Code Snippet

## Tool used

Manual Review

## Recommendation
During liquidations, provide the liquidator with the remaining PnL even if the position has run negative due to fees. This will maintain the current design of penalizing negative positions while mitigating the possibility of positions with no liquidation incentive.

Alternatively, include a user's PnL in his payout even if the collateral runs out. This may not be feasible due to particular design choices to ensure the user doesn't let his position run negative.

# Issue M-18: `base_to_quote` wrongly assume quote always has less decimals 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/91 

## Found by 
bareli, bughuntoor
## Summary
`base_to_quote` wrongly assume quote always has less decimals

## Vulnerability Detail
Let's look at the code of `base_to_quote`

```vyper
def base_to_quote(tokens: uint256, ctx: Ctx) -> uint256:                                # price is in quote decimals 
  lifted : Tokens  = self.lift(Tokens({base: tokens, quote: ctx.price}), ctx)           # get scaled to whichever has more decimals 
  amt0   : uint256 = self.to_amount(lifted.quote, lifted.base, self.one(ctx))           # amount gets calculated in whichever has more decimals 
  lowered: Tokens  = self.lower(Tokens({base: 0, quote: amt0}), ctx)                    # amount gets refactored to whichever has less decimals -> will be wrong if that's base
  return lowered.quote
```

In the input params, `tokens` is in base decimals and the price is in `quote` decimals.
As we can see, the first line scales to whichever has more decimals.
Then the amount is calculated, once again scaled in whichever has more decimals.
Then it is lowered to whichever has lower decimals.

It basically makes an assumption that the quote always has less decimals, which is not the case. If the pair is `WBTC/DAI` for example, it would be completely broken and allow for draining all assets.

## Impact
Loss of funds.

## Code Snippet
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/math.vy#L73

## Tool used

Manual Review

## Recommendation
Do proper decimals scaling 

# Issue M-19: User can sandwich their own position close to get back all of their position fees 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/94 

## Found by 
bughuntoor
## Summary
User can sandwich their own position close to get back all of their position fees

## Vulnerability Detail
Within the protocol, borrowing fees are only distributed to LP providers when the position is closed. Up until then, they remain within the position.
The problem is that in this way, fees are distributed evenly to LP providers, without taking into account the longevity of their LP provision.

This allows a user to avoid paying fees in the following way:
1. Flashloan a large sum and add it as liquidity
2. Close their position and let the fees be distributed (with most going back to them as they've got majority in the pool)
3. WIthdraw their LP tokens 
4. Pay back the flashloan

## Impact
Users can avoid paying borrowing fees.

## Code Snippet
https://github.com/sherlock-audit/2024-08-velar-artha/blob/main/gl-sherlock/contracts/positions.vy#L156

## Tool used

Manual Review

## Recommendation
Implement a system where fees are gradually distributed to LP providers.

# Issue M-20: User could have impossible to close position if funding fees grow too big. 

Source: https://github.com/sherlock-audit/2024-08-velar-artha-judging/issues/96 

## Found by 
0xbranded, bughuntoor
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

