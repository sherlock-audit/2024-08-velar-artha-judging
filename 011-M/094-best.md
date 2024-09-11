Kind Banana Sloth

High

# User can sandwich their own position close to get back all of their position fees

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