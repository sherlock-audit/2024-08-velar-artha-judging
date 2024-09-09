Amateur Nylon Canary

High

# Traders may decrease their trading loss via mint/burn

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
