# state

Reads and writes a utulie state repo. The state repo is the durable artifact —
the app is replaceable, this is what you own.

```
kb/<id>.md                 identity, KINGSMetaL frontmatter
.utulie/<name>/            a container; holds `.container` naming its id
.utulie/<name>/<name>      an item placement; names its id, and its quantity
                           when the item is fungible
```

**The tree records home. `meta.position` records where the thing actually was
last seen.** Those two disagreeing is what "checked out" means, so don't
collapse them.

Names are ids until somebody renames them, which makes KINGSMetaL's
(kind, name) uniqueness hold by construction. A rename edits the kb `name`
field and moves the tree entry in one commit; it is the only place uniqueness
needs enforcing. A fresh repo is therefore all hex, and gets readable as you
name the things you care about.

`.container` is not decoration. Git does not track empty directories, so
without it an empty bin has no existence at all — create one and it is absent
from the commit; empty one by checking out its last item and it disappears
along with its home. Which bins are empty is exactly what you need to know when
deciding where to put something.

## Integrity

Every placement names its id, so integrity is greppable and needs no index:

```
$ grep -rn <id> .utulie
```

| placements | meaning |
| --- | --- |
| 0 | not placed — this is what checked out looks like |
| 1 | placed, the normal case |
| >1 | legal only if the kb doc says `meta.fungible: true` |

`StateRepo.check()` applies that rule and also reports placements whose kb doc
is missing, quantities on non-fungible items, non-positive quantities, and a
tree entry whose name has drifted from its kb doc.

A placement with no kb doc is never dropped: the physical label exists in the
world, so it is surfaced as an orphan to be minted.

## Fungible items

`meta.fungible: true` on an *item* — not a kind, because a fungible thing is
still an item and mutating `kind` would collide with correcting a mistap.
Quantity lives on the placement, not the doc, so the same screw type holds
different counts in different bins.

Quantity **sets** the count in a container, it never adds to it. The PWA
queues actions offline and replays them on reconnect, and a replayed "add 6"
silently doubles your screw count where a replayed "set 12" is harmless.
Adding six means reading the count and writing the sum.

Quantity zero is never written; the placement is removed instead. Absent and
zero must not be two spellings of one state.

Check-out does not mean anything for fungible stock. Take 3 of 20 screws and
nothing is checked out — the count is 17 and there is no record of where 3
went. That is the right trade for screws, and it is a stated non-goal rather
than a gap.

## Ids

`uuid.uuid7()` from the standard library, which is byte-for-byte the format
`nosedive mint` emits — version 7, leading 48 bits the minting millisecond,
monotonic so ids sort by age. A test pins that.

Deliberately *not* shelling out to `npx -y nosedive mint`. That would put an
npm resolution on the path of every mint, and minting is the first step of the
put-away flow, which happens in a garage on marginal wifi. It would also mean
utulie cannot ship without nosedive — the product's runtime depending on the
dev bridge. The format is what matters, not the binary that produces it.

## Positions

`meta.position` is `{lat, lon, at}` — where the thing was last seen, not where
it belongs. The tree says where it belongs.

`at` is stored rather than recovered from git: staleness decides how much to
trust a position, and a `git blame` per item on every scan is not something to
build a lookup on. Coordinates round to 6 places, about 0.1 m; more is false
precision from a phone.

**Position is inherited from the nearest container that has one.** You geotag
the bin, not every screw in it. `position_of()` returns the position *and the
doc it came from*, so a caller can say "Office, 65 m" rather than implying it
tracked the screw.

Distance is haversine. At household range the error against a proper geodesic
is centimetres, well under any phone's GPS error.

Whether a phone can actually tell the garage from the shed is a separate
question, and belongs to the geolocation spike, not here.

## One verb for putting things somewhere

`place()` only. It creates a placement, or moves an existing one, or updates a
fungible count, depending on where the thing already is. A separate `move()`
existed briefly and was removed: the only thing distinguishing it was the
starting state, which is an implementation detail rather than something a
caller should have to know. Worse, `place()` on an already-placed container
made a second directory instead of moving it, which `check()` then reported as
placed-twice.

| thing is | result |
| --- | --- |
| nowhere | placed |
| already there | nothing, no commit |
| elsewhere, not fungible | moved, contents and all |
| elsewhere, fungible | a second placement — being in two bins is the point |

## Undo

`undo()` reverts the last action as a new commit rather than resetting. The
repo may already be pushed, and losing the record of a mistake loses the
evidence of what actually happened to the physical thing. Undoing an undo is
a redo.

## Checking out a container

Refused while it still holds anything. Checked out means "has no placement",
and a checked-out container cannot also hold things — its contents would have
nowhere to live — so taking it would delete their placements as collateral.
Empty it, or move the contents somewhere, first.

If you really are carrying a full bin out of the house, the honest move is to
*move* it into a container that represents where it went, not to check it out.

## Writes

One commit per action. The log is the audit trail, diffs stay legible, and
conflicts land per action. Moving anything — an item, or a container with all
its contents — is a pure rename with no content churn.

## Not here yet

Pushing to a remote. Git runs server-side and the phone never holds a repo, so
an offline action cannot reach the server at all; the PWA is expected to queue
locally and replay, each replayed action still its own commit.
