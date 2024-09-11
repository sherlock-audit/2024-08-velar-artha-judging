Hot Purple Buffalo

High

# Inequitable Fee Application Penalizes Lower Leverage Positions and LPs

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