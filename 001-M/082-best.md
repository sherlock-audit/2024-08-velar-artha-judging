Kind Banana Sloth

High

# Usage of `tx.origin` to determine the user is prone to attacks

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