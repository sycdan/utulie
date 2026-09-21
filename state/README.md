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
