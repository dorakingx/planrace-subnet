# Testnet TAO Request

Post the following in the official Bittensor Discord **Requests for Testnet
TAO** channel. This contains public addresses only.

> Hi — I am building PlanRace for the Bittensor Global Subnet Hackathon. Please
> allocate 1.260001 test TAO on the canonical Finney testnet to this dedicated,
> testnet-only coldkey:
> `5Ehsb7JthQxuaXwgLJrzGksA6CSHDxC39QotGKaBMHGkfftJ`
>
> Purpose: create one testnet subnet, register 3 validator and 10 miner hotkeys,
> run the signed miner-validator/scoring flow, and submit/read back weights.
> Public repository: https://github.com/dorakingx/planrace-subnet
> Hackathon: https://www.hackquest.io/hackathons/Bittensor-Global-Subnet-Hackathon
> Current testnet balance: 0. No mainnet wallet or real TAO will be used.

The requested 1.260001 test TAO is a staged initial allocation: the pre-signing
creation-price review cap is 1.25 test TAO and the SDK estimated-fee policy cap
is 0.01 test TAO. At the read-only snapshot on 2026-09-07, subnet creation cost
1 test TAO and netuid 1 hotkey registration cost 0.0005 test TAO; both are volatile.
Runtime v454 has no subnet-creation price-limit argument, so a fresh plan and
explicit dynamic-cost acknowledgement are required before signing. Receipt of
test TAO does not authorize mainnet activity or spending beyond this testnet
project. Any later allocation remains within the separate 5 test TAO total
project budget.
