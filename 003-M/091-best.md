Kind Banana Sloth

High

# `base_to_quote` wrongly assume quote always has less decimals

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