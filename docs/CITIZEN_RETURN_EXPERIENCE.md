# BinSight Citizen Return Experience

Document status: prototype experience brief, 29 August 2026.

## Purpose

BinSight gives an eligible beverage container a recoverable value. Under the proposed regional scheme, every shop selling an eligible drink adds a separate **RM0.20 refundable deposit**. The person who later returns the marked container receives that RM0.20, even if someone else bought or discarded it.

This is a deposit-return loop, not a tax and not an unrestricted recycling reward:

`Drink RM1.90 + refundable deposit RM0.20 = RM2.10`

`Eligible container returned = RM0.20 refunded`

The prototype uses a simulated deposit and payout. A real regional scheme would require the policy authority, common container mark, retailer participation and clearing arrangement described in the [return-deposit assessment](RETURN_DEPOSIT_POLICY.md).

## Citizen Promise

> Return an eligible marked beverage container and receive RM0.20. You may return containers you purchased or eligible containers left behind by someone else.

The citizen does not select the material or tell the station what was inserted. The station checks the container and reports the result. This keeps the task simple: bring a container, insert it and recover its deposit.

## The Reward Loop

1. A shop collects RM0.20 with each eligible drink and records it separately from the drink price.
2. The deposit enters the regional clearing pool rather than becoming shop revenue.
3. A citizen presents any eligible marked container at a BinSight return station.
4. An accepted station decision adds RM0.20 to that citizen's active session.
5. BinSight combines all accepted items and sends one refund when the citizen finishes.
6. The retained containers enter the recycling stream, and the operator reconciles deposits, refunds and returned material.

This model does not require the person who paid the deposit to be the person who receives it. If a container is discarded, its unclaimed value gives another resident, cleaner, school or community group a reason to collect and return it.

## Experience Flow

### 1. Sign in once

The citizen signs in with National ID and a mock one-time code. Their session remains available on that personal device, so a routine return does not begin with repeated account setup. National ID identifies the citizen's account and payout destination; it does not prove who bought a container or who owns its refund.

**Why:** persistent sign-in reduces friction while keeping return history and saved payout methods attached to one demonstration account.

### 2. Start at the return station

In the planned flow, the citizen scans the QR code printed on the station. The link opens BinSight and binds the new return session to that station. The current mock uses a **Start return** button until QR scanning is implemented.

**Why:** the QR identifies the station and starts the correct session without exposing a camera feed or asking the citizen to enter a station number.

### 3. Insert one container

The citizen places one empty container into the station. The screen shows that inspection is in progress. The station, relay and server determine whether the container is eligible; the citizen does not categorise it.

**Why:** one-at-a-time inspection gives each physical container one decision and prevents confusion about which item earned a refund.

### 4. See an immediate result

An accepted container adds **RM0.20** to the session total. A rejected container adds **RM0.00**, gives a short reason and asks the citizen to remove it. In both cases, **Add another item** remains available. A recoverable read problem may offer one retry.

**Why:** immediate item-level feedback makes the balance understandable, avoids silently rejecting a container and lets the citizen continue after a mistake.

### 5. Build the refund total

The active session keeps the number of accepted and rejected items visible together with the current refund. The amount changes only after an accepted station decision.

**Why:** a running total makes the incentive tangible and lets the citizen verify the expected payout before finishing.

### 6. Finish and choose payout

After at least one accepted container, the citizen presses **Finish return**. BinSight shows the final item count, RM0.20-per-item calculation, zero citizen fees and the total. The citizen selects a saved **Bank Transfer** or **E-Wallet** method, with options to add or remove methods. The prototype then makes one simulated payment for the whole session.

**Why:** one combined payment is easier to understand and avoids the cost and noise of a separate transfer for every 20-sen refund.

### 7. Confirm completion

The completion screen shows the amount, masked destination, session reference, transaction reference and time. The primary message is:

> Payment complete. Thank you for helping keep your community clean.

The session is saved in return history so the citizen can check it later.

**Why:** a specific receipt confirms where the refund went, while the closing message connects the individual action to a cleaner shared environment without sounding promotional.

## Why the Loop Works

- **The value is easy to understand.** Every eligible container has the same RM0.20 deposit in the prototype.
- **The refund follows the container.** No purchase receipt is needed. A person who picks up an eligible discarded container can redeem it, transferring value from litter to cleanup effort.
- **The citizen has one simple job.** They insert the item and respond to the station result; they do not need recycling expertise or access to the station camera.
- **Progress is visible.** Every accepted item and the exact session total appear before payout.
- **Rejection is recoverable.** One unsuitable item does not end the session or erase accepted deposits.
- **Payout is deliberate.** Saved methods reduce repeat effort, while final confirmation prevents an accidental or unclear finish.

## Benefits

### Citizens

- recover deposits paid on their own drinks;
- earn the deposit attached to eligible containers discarded by other people;
- use Bank Transfer or E-Wallet without paying a citizen fee;
- see an item-by-item record and final receipt;
- participate without manually identifying container material.

### Community and municipality

- gives residents a direct reason to remove beverage containers from public spaces;
- moves marked containers into a controlled return stream rather than mixed waste;
- provides session-level evidence for evaluating returns, rejections and payout reliability;
- supports community collection or fundraising because the refund is attached to the returned container, not the original buyer.

### Scheme operator and retailers

- uses one visible deposit amount across participating sellers;
- separates the beverage price from money held for refund;
- combines item credits into one session payout;
- creates an auditable chain from station decision to session credit and simulated payment.

## Interface Priority

The reward loop is the primary citizen demonstration. Its essential screens are:

1. National ID and mock OTP sign-in;
2. return landing and station-session start;
3. active session with inspection results and running total;
4. payout selection;
5. payment confirmation and return history.

Issue reporting, disposal guidance, locations, FAQ, chat and contact details remain useful supporting services, but they should not interrupt or compete with this sequence during the return demonstration.

## Prototype Boundaries

- RM0.20 is a simulated proposed deposit, not an adopted Malaysian beverage-deposit rate.
- Bank Transfer and E-Wallet payments are simulated; no money moves.
- The current website uses a button instead of a live QR scanner.
- The browser does not view, transmit or store station images.
- A future physical station must verify a registered deposit mark or container identifier. Recognising plastic, metal or glass alone does not prove that the deposit was paid.
