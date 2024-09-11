Hot Purple Buffalo

High

# Loss of Funds and Delayed Liquidations Due to Inaccurate Fee Accrual

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